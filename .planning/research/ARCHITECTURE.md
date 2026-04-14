# Architecture Research

**Domain:** Real-time user event tracking and heatmap visualization system
**Researched:** 2026-04-14
**Confidence:** HIGH (core pipeline verified against official ClickHouse docs and multiple production case studies)

---

## Standard Architecture

### System Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                        BROWSER LAYER                               │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  JS Tracking Snippet (pageX/Y → normalized x_pct/y_pct)     │  │
│  │  + RudderStack SDK (buffers, enriches, delivers events)      │  │
│  └─────────────────────────┬────────────────────────────────────┘  │
└────────────────────────────│───────────────────────────────────────┘
                             │ HTTPS POST (JSON batch)
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│                     INGESTION LAYER                                │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  RudderStack (self-hosted or cloud)                          │  │
│  │  — validates, enriches with session/device context           │  │
│  │  — routes track("click") events → Kafka destination          │  │
│  └─────────────────────────┬────────────────────────────────────┘  │
└────────────────────────────│───────────────────────────────────────┘
                             │ JSON messages
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│                      STREAMING LAYER                               │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Kafka / Redpanda                                            │  │
│  │  Topic: user-click-events                                    │  │
│  │  (Redpanda preferred for local dev — no ZooKeeper)           │  │
│  └─────────────────────────┬────────────────────────────────────┘  │
└────────────────────────────│───────────────────────────────────────┘
                             │ Kafka Engine pull (ClickHouse consumer)
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│                       STORAGE LAYER                                │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  ClickHouse                                                  │  │
│  │  [kafka_queue table]  →  [Materialized View]  →  [MergeTree] │  │
│  │  click_events_queue       mv_click_events        click_events │  │
│  └─────────────────────────┬────────────────────────────────────┘  │
└────────────────────────────│───────────────────────────────────────┘
                             │ SQL query (clickhouse-connect)
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│                     COMPUTATION LAYER                              │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Heatmap Aggregator (Python service or ClickHouse query)     │  │
│  │  — grid-based binning at 5% resolution                       │  │
│  │  — filters by page_path, device_type, date range             │  │
│  └─────────────────────────┬────────────────────────────────────┘  │
└────────────────────────────│───────────────────────────────────────┘
                             │ 2D grid array + screenshot URL
                             ▼
┌────────────────────────────────────────────────────────────────────┐
│                   VISUALIZATION LAYER                              │
│  ┌──────────────┐  ┌──────────────────────────────────────────┐   │
│  │  Screenshot  │  │  Streamlit Dashboard                     │   │
│  │  Capture     │  │  — loads screenshot as background        │   │
│  │  Service     │  │  — overlays heatmap grid (Plotly/PIL)    │   │
│  │  (Playwright)│  │  — filters by page / device / date       │   │
│  └──────────────┘  └──────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| JS Tracking Snippet | Capture click/scroll events with coordinates; normalize to percentages; deliver via RudderStack SDK | Vanilla JS, ~50 lines, loaded async |
| RudderStack | Buffer events in browser, enrich with session/page context, deliver to Kafka destination | Self-hosted `rudder-server` or RudderStack Cloud |
| Kafka / Redpanda | Durable ordered event stream; decouples producers from ClickHouse consumer | Redpanda (single binary, Kafka-API-compatible) for local dev |
| ClickHouse Kafka Queue Table | Kafka Engine table acts as consumer; reads message batches from topic | `ENGINE = Kafka(...)` DDL — NOT for direct query |
| ClickHouse Materialized View | Triggered on each batch from Kafka queue; transforms and inserts into MergeTree | `CREATE MATERIALIZED VIEW ... TO click_events AS SELECT ...` |
| ClickHouse MergeTree Table | Persistent columnar storage; partitioned and ordered for fast aggregation queries | `ENGINE = MergeTree() PARTITION BY toYYYYMM(event_time)` |
| Heatmap Aggregator | Query ClickHouse with spatial binning SQL; return 2D grid of counts | Python function or ClickHouse query layer |
| Screenshot Capture Service | Load target URL in headless browser; capture full-page PNG at fixed viewport width | Playwright Python (`page.screenshot(full_page=True)`) |
| Streamlit Dashboard | Load screenshot; overlay heatmap using Plotly or PIL; expose page/date/device filters | `clickhouse-connect` + `streamlit` + `plotly` |

---

## Data Flow: Browser Click to Heatmap Pixel

This is the critical flow to understand before writing any code.

```
Step 1: USER CLICKS ELEMENT IN BROWSER
  event.pageX  = 847  (pixels from document left, includes scroll)
  event.pageY  = 1203 (pixels from document top, includes scroll)
  document.body.scrollWidth  = 1440
  document.body.scrollHeight = 3200

Step 2: JS SNIPPET NORMALIZES (runs in browser before sending)
  x_pct = (event.pageX / document.body.scrollWidth)  * 100  → 58.8
  y_pct = (event.pageY / document.body.scrollHeight) * 100  → 37.6
  NOTE: Use pageX/pageY (document-relative), NOT clientX/clientY (viewport-relative)
  NOTE: Capture scrollWidth/scrollHeight at event time, not on load

Step 3: RUDDERSTACK WRAPS AND SHIPS
  rudderanalytics.track("click", {
    x_pct: 58.8,
    y_pct: 37.6,
    page_path: "/pricing",
    element_id: "cta-button",
    device_type: "desktop",
    viewport_width: 1440,
    viewport_height: 900
  })
  → JSON POST to RudderStack data plane

Step 4: RUDDERSTACK ROUTES TO KAFKA
  Topic: "user-click-events"
  Message key: session_id (ensures ordering per session)
  Format: JSON

Step 5: CLICKHOUSE CONSUMES FROM KAFKA
  kafka_queue table reads batch
  Materialized View fires immediately
  Inserts into click_events (MergeTree)

Step 6: HEATMAP AGGREGATION QUERY
  SELECT
    round(x_pct / 5) * 5 AS x_bucket,   -- 20 columns (0,5,10...95)
    round(y_pct / 5) * 5 AS y_bucket,   -- 20 rows (0,5,10...95)
    count()               AS heat
  FROM click_events
  WHERE page_path = '/pricing'
    AND device_type = 'desktop'
    AND event_time >= now() - INTERVAL 7 DAY
  GROUP BY x_bucket, y_bucket
  ORDER BY x_bucket, y_bucket

Step 7: STREAMLIT OVERLAY
  - Load screenshot PNG (1440px wide)
  - Scale heatmap grid to image dimensions
  - Render colored overlay using Plotly imshow or PIL draw
  - Blend with transparency (alpha=0.6)
```

---

## Coordinate Normalization Strategy

**Use document-relative normalized percentages (0–100). This is the correct approach.**

### Why Not Absolute Pixels

A click at pixel (847, 1203) on a 1440px-wide desktop is meaningless on a 390px-wide iPhone. Storing absolute pixels means you cannot compare across devices, and heatmaps would be misaligned with screenshots taken at a different viewport.

### Why Not Viewport Coordinates (clientX/clientY)

`clientX`/`clientY` are relative to the visible viewport, not the document. A user scrolled 500px down clicking an element at viewport Y=200 is actually at document Y=700. If stored as `clientY=200`, the heatmap point plots 500px too high on the page screenshot.

### Correct Approach: Document Percentage

```javascript
// In the JS tracking snippet
document.addEventListener('click', function(event) {
  const docWidth  = Math.max(
    document.body.scrollWidth,
    document.documentElement.scrollWidth
  );
  const docHeight = Math.max(
    document.body.scrollHeight,
    document.documentElement.scrollHeight
  );

  const x_pct = (event.pageX / docWidth)  * 100;
  const y_pct = (event.pageY / docHeight) * 100;

  rudderanalytics.track("click", {
    x_pct:         parseFloat(x_pct.toFixed(2)),
    y_pct:         parseFloat(y_pct.toFixed(2)),
    page_path:     window.location.pathname,
    element_id:    event.target.id || event.target.tagName,
    device_type:   window.innerWidth <= 768 ? 'mobile' : 'desktop',
    viewport_w:    window.innerWidth,
    doc_height:    docHeight
  });
});
```

### Device Pixel Ratio

Do NOT use `devicePixelRatio` for coordinate normalization. It applies to CSS pixels vs physical pixels — `pageX`/`pageY` are already in CSS pixels. Only relevant if you are capturing screenshots at 2x DPR and need to scale overlay coordinates to match.

### Screenshot Alignment Rule

The screenshot capture service MUST take screenshots at the same fixed viewport width used as the denominator in normalization. Recommended: **1440px wide for desktop, 390px wide for mobile**. Capture the full-page height so Y coordinates align with document-relative percentages.

---

## Heatmap Computation: Binning vs KDE

**Recommendation: Grid-based binning for this stack. KDE is overkill and harder to implement in ClickHouse SQL.**

### Binning (Recommended)

Divide the page into a fixed grid. Count events per cell. Fast, deterministic, maps directly to SQL GROUP BY.

```sql
-- 5% buckets = 20x20 grid (400 cells per page)
SELECT
  round(x_pct / 5) * 5 AS x_bucket,
  round(y_pct / 5) * 5 AS y_bucket,
  count()               AS heat
FROM click_events
WHERE page_path = {page_path:String}
  AND device_type = {device_type:String}
GROUP BY x_bucket, y_bucket
```

**Grid resolution options:**
- 5% buckets → 20×20 grid (400 cells) — good for general overview
- 2% buckets → 50×50 grid (2500 cells) — more precise, still fast
- 1% buckets → 100×100 grid (10000 cells) — only useful with 100k+ events per page

### KDE (When Justified)

Kernel Density Estimation produces a smooth continuous surface that looks better visually. Use it only if:
- You need publication-quality visuals
- You have >10k clicks per page view (smoothing is visually meaningful)
- You are willing to run KDE post-query in Python (scipy.stats.gaussian_kde)

KDE cannot be done natively in a single ClickHouse SQL query. The pattern would be: run binning query → pass grid to Python → apply Gaussian smoothing → render.

**For MVP: use binning.** You can add Gaussian smoothing as a post-processing step in Python later without changing the data model.

---

## ClickHouse Schema Design

```sql
-- 1. Kafka Engine Table (consumer — do not query directly)
CREATE TABLE click_events_queue
(
    event_time  DateTime,
    session_id  String,
    user_id     String,
    page_path   String,
    x_pct       Float32,
    y_pct       Float32,
    element_id  String,
    device_type String,
    viewport_w  UInt16,
    doc_height  UInt32
)
ENGINE = Kafka(
    'redpanda:9092',       -- broker
    'user-click-events',   -- topic
    'clickhouse-group',    -- consumer group
    'JSONEachRow'          -- format
);

-- 2. Target MergeTree Table (persistent storage — query this)
CREATE TABLE click_events
(
    event_time  DateTime,
    session_id  String,
    user_id     String,
    page_path   LowCardinality(String),
    x_pct       Float32,
    y_pct       Float32,
    element_id  String,
    device_type LowCardinality(String),
    viewport_w  UInt16,
    doc_height  UInt32
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_time)
ORDER BY (page_path, device_type, event_time);
-- ORDER BY puts most common filter columns first for skip index efficiency

-- 3. Materialized View (bridge — fires on every Kafka batch)
CREATE MATERIALIZED VIEW mv_click_events TO click_events AS
SELECT * FROM click_events_queue;
```

**Why LowCardinality:** `page_path` and `device_type` have few distinct values. LowCardinality encoding halves storage and doubles aggregation speed for these columns.

**Why this ORDER BY:** Heatmap queries always filter by `page_path` and `device_type` first. ClickHouse sparse primary index is most effective when filter columns match the leading ORDER BY columns.

---

## Screenshot Capture Service Architecture

### Approach: On-Demand Playwright Worker

For this scale (Streamlit dashboard, human-driven analysis), screenshot capture does not need to be a real-time streaming service. Use a pull-on-demand pattern:

```
Streamlit user selects page → Python calls screenshot_service.capture(url, viewport_w)
  → check local cache (screenshots/<hash>.png exists?)
    YES → return path directly
    NO  → launch Playwright, navigate, screenshot, save, return path
```

### Implementation Pattern

```python
import asyncio
from playwright.async_api import async_playwright
import hashlib, os

SCREENSHOT_DIR = "/data/screenshots"

async def capture_screenshot(url: str, viewport_width: int = 1440) -> str:
    cache_key = hashlib.md5(f"{url}:{viewport_width}".encode()).hexdigest()
    cache_path = f"{SCREENSHOT_DIR}/{cache_key}.png"

    if os.path.exists(cache_path):
        return cache_path

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": viewport_width, "height": 900})
        await page.goto(url, wait_until="networkidle")
        await page.screenshot(path=cache_path, full_page=True)
        await browser.close()

    return cache_path
```

### Viewport Width Rule

- Desktop heatmaps: capture at **1440px** (most common desktop breakpoint)
- Mobile heatmaps: capture at **390px** (iPhone 14 viewport)
- Store width alongside screenshot so dashboard can use the correct one

### Why Playwright over Puppeteer

Playwright is the current default for new projects (2026). It supports Chromium, Firefox, and WebKit from a single API, has built-in `networkidle` wait, and has a first-class Python library (`playwright`). Puppeteer is Node.js only and Chrome-only.

---

## Recommended Project Structure

```
/
├── snippet/                    # Browser-side
│   └── tracker.js              # JS snippet: normalize + rudderstack.track()
│
├── rudderstack/                # RudderStack config
│   └── config/                 # Destination: Kafka broker address + topic
│
├── pipeline/                   # ClickHouse schema + migration
│   ├── migrations/
│   │   ├── 001_create_queue.sql
│   │   ├── 002_create_target.sql
│   │   └── 003_create_mv.sql
│   └── queries/
│       └── heatmap.sql         # Parameterized binning query
│
├── screenshot/                 # Screenshot capture service
│   ├── capture.py              # Playwright async capture function
│   └── cache/                  # Persistent PNG cache (mounted volume)
│
├── heatmap/                    # Aggregation logic
│   ├── aggregator.py           # Query ClickHouse, return 2D grid
│   └── renderer.py             # Apply grid to screenshot image
│
├── dashboard/                  # Streamlit app
│   ├── app.py                  # Main Streamlit entry point
│   ├── components/
│   │   ├── heatmap_view.py     # Page selector + heatmap overlay widget
│   │   └── filters.py          # Date range, device type, page path controls
│   └── db.py                   # clickhouse-connect client singleton
│
├── docker-compose.yml          # Full local stack
└── .env                        # CLICKHOUSE_HOST, RUDDERSTACK_WRITE_KEY, etc.
```

### Structure Rationale

- **snippet/ separate from dashboard/:** The tracker runs in users' browsers; the dashboard runs on your server. They should never share code or imports.
- **pipeline/migrations/:** Treat ClickHouse schema as code, versioned and reproducible. `clickhouse-migrations` or plain ordered SQL files.
- **heatmap/ separate from dashboard/:** Computation logic (aggregator.py) can be tested independently of Streamlit rendering.
- **screenshot/cache/ as a volume:** Screenshots are expensive to regenerate; persisting them as a bind-mounted volume survives container restarts.

---

## Docker Compose Structure (Local Dev)

```yaml
# docker-compose.yml
version: "3.9"

services:
  # Kafka-compatible broker (no ZooKeeper, single binary)
  redpanda:
    image: redpandadata/redpanda:latest
    command:
      - redpanda
      - start
      - --overprovisioned
      - --smp 1
      - --memory 512M
      - --reserve-memory 0M
      - --node-id 0
      - --check=false
    ports:
      - "9092:9092"
      - "9644:9644"   # Admin API

  # Redpanda Console (topic browser)
  redpanda-console:
    image: redpandadata/console:latest
    ports:
      - "8080:8080"
    environment:
      KAFKA_BROKERS: redpanda:9092
    depends_on: [redpanda]

  # ClickHouse columnar store
  clickhouse:
    image: clickhouse/clickhouse-server:latest
    ports:
      - "8123:8123"   # HTTP interface
      - "9000:9000"   # Native TCP (clickhouse-connect uses this)
    volumes:
      - clickhouse-data:/var/lib/clickhouse
      - ./pipeline/migrations:/docker-entrypoint-initdb.d   # Auto-run on first start
    ulimits:
      nofile: { soft: 262144, hard: 262144 }

  # Screenshot capture worker (runs on demand)
  screenshot:
    build: ./screenshot
    volumes:
      - screenshot-cache:/app/cache
    # No ports — called as a Python module from dashboard

  # Streamlit dashboard
  dashboard:
    build: ./dashboard
    ports:
      - "8501:8501"
    environment:
      CLICKHOUSE_HOST: clickhouse
      CLICKHOUSE_PORT: 9000
      SCREENSHOT_CACHE_DIR: /app/screenshots
    volumes:
      - screenshot-cache:/app/screenshots
    depends_on: [clickhouse]

volumes:
  clickhouse-data:
  screenshot-cache:
```

**Notes:**
- RudderStack is not in this compose. Use RudderStack Cloud free tier for local dev (avoids running their full self-hosted stack). Configure it to point Kafka destination at `localhost:9092`.
- Migrations in `/docker-entrypoint-initdb.d` run automatically on first ClickHouse startup — the three SQL files (queue table, target table, materialized view) execute in filename order.
- `screenshot` and `dashboard` share the `screenshot-cache` volume so Playwright writes to the same directory Streamlit reads from.

---

## Architectural Patterns

### Pattern 1: Three-Table Kafka Ingestion (ClickHouse)

**What:** Never query the Kafka Engine table directly. It consumes and moves the cursor. Use queue table → materialized view → MergeTree target.

**When to use:** Always, for any Kafka → ClickHouse ingestion.

**Trade-offs:** The three-table setup adds initial complexity, but it is the only supported pattern that provides persistent storage. Querying the Kafka Engine table directly consumes offsets with no persistence.

**Example:**
```sql
-- Correct pattern
CREATE TABLE raw_queue ENGINE = Kafka(...);       -- reads from Kafka
CREATE TABLE events ENGINE = MergeTree() ...;    -- stores data
CREATE MATERIALIZED VIEW mv TO events AS
  SELECT * FROM raw_queue;                        -- bridges them
```

### Pattern 2: Coordinate Normalization at Source (Browser)

**What:** Normalize coordinates to 0–100 percentage values in the JS snippet before sending to RudderStack. Never store raw pixels.

**When to use:** Always. This is not optional.

**Trade-offs:** You lose the ability to reconstruct absolute pixel positions from stored data alone (you would need stored `doc_height` + `viewport_w` to reconstruct). Store those fields alongside percentages.

### Pattern 3: Cache Screenshots by URL + Viewport Hash

**What:** Hash the (url, viewport_width) tuple, store result as `{hash}.png`. Never regenerate if cache exists.

**When to use:** Screenshots are slow (2–5 seconds per page). Any dashboard interaction that requires a screenshot should hit cache first.

**Trade-offs:** Stale screenshots if the page changes. Mitigation: add a "Refresh Screenshot" button in the dashboard that deletes the cached file and recaptures.

---

## Anti-Patterns

### Anti-Pattern 1: Storing clientX/clientY Instead of pageX/pageY

**What people do:** Attach the click listener and store `event.clientX`, `event.clientY` directly.

**Why it's wrong:** clientX/clientY are viewport-relative. When the user has scrolled 400px, a click at viewport Y=200 is actually at document Y=600. The heatmap point will be plotted 400px too high relative to the page screenshot.

**Do this instead:** Always use `event.pageX`, `event.pageY`, then divide by `document.body.scrollHeight` to get document-relative percentages.

### Anti-Pattern 2: Querying the Kafka Engine Table Directly

**What people do:** Run `SELECT * FROM click_events_queue LIMIT 100` to inspect incoming events.

**Why it's wrong:** This consumes Kafka offsets. Events you preview are not written to the MergeTree table; they are silently dropped.

**Do this instead:** For debugging, use Redpanda Console (port 8080) to browse topic messages without consuming. Only the Materialized View should read from the queue table.

### Anti-Pattern 3: Running Playwright in the Streamlit Process

**What people do:** Call `asyncio.run(capture_screenshot(...))` inside a Streamlit callback.

**Why it's wrong:** Streamlit reruns the entire script on each interaction. Multiple concurrent reruns can spawn multiple Playwright instances simultaneously, causing port conflicts and OOM errors.

**Do this instead:** Run screenshot capture as a separate Python process or use `st.cache_data` with a TTL. At minimum, gate the capture behind a manual "Capture Screenshot" button rather than triggering it automatically on page load.

### Anti-Pattern 4: Storing Screenshots in ClickHouse

**What people do:** Attempt to store screenshot binary data as a ClickHouse column.

**Why it's wrong:** ClickHouse is optimized for columnar numeric aggregation. Large binary blobs defeat the compression and query model. Screenshots are typically 100KB–2MB each.

**Do this instead:** Store screenshots as files on disk (or in object storage like MinIO for production). Store only the file path or URL in ClickHouse if needed.

---

## Build Order (What Must Exist Before What)

The dependency chain is strict. Build in this order:

```
Phase 1: STREAMING BACKBONE
  Redpanda (Kafka-compatible) running in Docker
  → Topic: user-click-events created
  → Verify: can produce/consume test message via rpk CLI
  (Nothing else can be built without the topic existing)

Phase 2: STORAGE LAYER
  ClickHouse running in Docker
  → Three-table pattern deployed (queue + mv + target)
  → Verify: manually insert a JSON row into queue table, confirm it appears in click_events
  (Heatmap computation requires stored events)

Phase 3: INGESTION (JS Snippet + RudderStack)
  RudderStack configured with Kafka destination (pointing at Redpanda:9092)
  → JS snippet built, normalization logic tested in isolation
  → Track("click") calls flow: browser → RudderStack → Kafka → ClickHouse
  → Verify: click on test page, see row appear in click_events within 5 seconds
  (Dashboard requires real data to visualize)

Phase 4: SCREENSHOT CAPTURE SERVICE
  Playwright service built
  → Can capture full-page PNG at 1440px width
  → Caching by URL hash working
  → Verify: capture a known page, inspect PNG dimensions match expected doc height
  (Heatmap overlay requires a screenshot baseline)

Phase 5: HEATMAP COMPUTATION + DASHBOARD
  ClickHouse binning query working (returns 2D grid)
  → Streamlit app loads screenshot
  → Overlays heatmap grid using Plotly or PIL
  → Filters by page_path, device_type, date range
  (This is the user-facing product)
```

**Critical dependency:** Steps 1 and 2 are independent of each other but both must be complete before Step 3. Steps 3 and 4 can be built in parallel. Step 5 requires all of the above.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| RudderStack | Configure Kafka destination in RudderStack dashboard; point to Redpanda broker | JSON format; default topic or per-event-type routing |
| Redpanda (Kafka API) | ClickHouse Kafka Engine uses Kafka protocol; Redpanda is compatible | No ZooKeeper; admin API on port 9644 |
| Playwright | Python `playwright` library; launched in-process or via subprocess | Install with `playwright install chromium` |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| JS Snippet → RudderStack | `rudderanalytics.track()` call in browser | SDK handles batching, retry, session enrichment |
| RudderStack → Redpanda | Kafka producer (RudderStack built-in destination) | Configure broker address + topic name in RS dashboard |
| Redpanda → ClickHouse | ClickHouse Kafka Engine pull (ClickHouse is consumer) | ClickHouse pulls; Redpanda does not push |
| ClickHouse → Heatmap Aggregator | `clickhouse-connect` Python client; `query_df()` returns DataFrame | Connection: `host=clickhouse, port=9000` |
| Heatmap Aggregator → Streamlit | Python function call (same process) | Returns numpy array or dict; rendered by Plotly |
| Screenshot Service → Streamlit | File path on shared volume | Dashboard reads PNG; no network call needed |

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0–10k events/day | Single Redpanda broker, single ClickHouse node, all in docker-compose — no changes needed |
| 10k–1M events/day | Add `kafka_num_consumers = 2` in ClickHouse Kafka table; consider `ReplicatedMergeTree` for HA |
| 1M–100M events/day | Redpanda cluster (3 brokers); ClickHouse cluster (shard by `page_path`); separate ingest and query nodes |
| 100M+ events/day | Pre-aggregate with ClickHouse `AggregatingMergeTree` + pre-computed heatmap snapshots; query aggregated tables, not raw events |

### Scaling Priorities

1. **First bottleneck:** ClickHouse write throughput. Fix by increasing `kafka_num_consumers` and `kafka_max_block_size`. Both are config changes, no schema migration.
2. **Second bottleneck:** ClickHouse query latency on `click_events`. Fix by adding a materialized view that pre-aggregates into a summary table keyed by `(page_path, device_type, date, x_bucket, y_bucket)`. Dashboard queries the summary, not raw events.

---

## Sources

- [How to Build a User Behavior Heatmap with ClickHouse](https://oneuptime.com/blog/post/2026-03-31-clickhouse-user-behavior-heatmap/view) — HIGH confidence (March 2026, exact schema DDL and binning queries verified)
- [ClickHouse Kafka Table Engine Official Docs](https://clickhouse.com/docs/integrations/kafka/kafka-table-engine) — HIGH confidence (official ClickHouse documentation, three-table pattern, consumer configuration)
- [Clickstream Heatmap with Quix/Kafka](https://quix.io/blog/clickstream-analytics-creating-a-heat-map-for-an-ecommerce-website) — HIGH confidence (full pipeline from browser to heatmap, 50x50 grid binning, relative coordinate normalization)
- [In-game Analytics Pipeline: Redpanda + ClickHouse + Streamlit](https://tributarydata.substack.com/p/in-game-analytics-pipeline-with-redpanda) — HIGH confidence (exact Redpanda↔ClickHouse config, Streamlit integration pattern)
- [ClickHouse Python Dashboard with Streamlit](https://clickhouse.com/resources/engineering/python-dashboard-streamlit) — HIGH confidence (official ClickHouse resource, `clickhouse-connect` library)
- [RudderStack Apache Kafka Destination Docs](https://www.rudderstack.com/docs/destinations/streaming-destinations/kafka/) — MEDIUM confidence (official docs confirm topic routing, JSON/Avro format support)
- [Playwright vs Puppeteer 2026](https://www.browserstack.com/guide/playwright-vs-puppeteer) — MEDIUM confidence (current comparison; Playwright recommended for new projects)
- [MDN: MouseEvent.pageX](https://developer.mozilla.org/en-US/docs/Web/API/MouseEvent/pageX) — HIGH confidence (authoritative web spec reference)
- [Docker Compose: ClickHouse + Kafka/Redpanda example](https://github.com/s0rg/clickhouse-kafka-compose) — MEDIUM confidence (community reference, structure verified against official docs)

---
*Architecture research for: Real-time user event tracking and heatmap visualization*
*Researched: 2026-04-14*
