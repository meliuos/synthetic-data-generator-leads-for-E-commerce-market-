# Stack Research

**Domain:** Real-time web event tracking and heatmap visualization platform
**Researched:** 2026-04-14
**Confidence:** MEDIUM-HIGH (mandatory components verified against official docs; heatmap rendering lib is LOW confidence due to ecosystem fragmentation)

---

## Recommended Stack

### Layer 1 — JS Tracking Snippet (Browser)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `@rudderstack/analytics-js` | 3.31.0 (Mar 2026) | Ingest and route browser events to data plane | Mandatory per constraints. SDK v3 is the current major version; ~25 KB, ITP-compliant via server-side cookies. NPM package is browser-only — install once, export as singleton. |
| `cookieconsent` (orestbida) | 3.1.0 (Feb 2025) | GDPR/ePrivacy cookie consent banner | 5.4 K stars, actively maintained, vanilla JS, zero deps. Blocks analytics scripts until explicit opt-in, which is the correct GDPR interpretation for non-essential tracking under ePrivacy Directive. |
| Native browser APIs | — | `mousemove`, `click`, `scroll` event listeners | No library needed. Use `addEventListener` with passive listeners and `requestAnimationFrame` throttling for mouse-move sampling. |

**Snippet delivery pattern:** Async CDN loader (matches Rudderstack quickstart pattern) injected into `<head>`. NPM package acceptable if host app uses a bundler.

**Custom event taxonomy to track:**
- `page_view` — on `DOMContentLoaded`
- `click` — `{x, y, target_selector, page_url, viewport_width, viewport_height}`
- `scroll_depth` — at 25 / 50 / 75 / 90 % thresholds
- `mouse_move` — sampled at max 10 Hz via `requestAnimationFrame`
- `rage_click` — 3+ clicks within 500 ms on same element

---

### Layer 2 — Event Streaming (Mandatory)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| RudderStack Data Plane (self-hosted) | Latest OSS (`rudderlabs/rudder-server`) | Receives events from JS SDK, routes to Kafka topic | Mandatory. Self-hosted via Docker gives full data sovereignty for GDPR. Control Plane Lite removes the cloud dependency. |
| Apache Kafka (via Confluent KRaft image) | 3.x (KRaft mode) | Durable event bus between RudderStack and ClickHouse | Mandatory per constraints. KRaft removes ZooKeeper; `confluentinc/cp-kafka` Docker image is the standard dev setup. Use this for production reliability and ecosystem maturity. |
| **OR** Redpanda | v26.1.4 (stable, Apr 2026) | Drop-in Kafka API replacement | Kafka-compatible (no client changes). C++ / Seastar = lower latency, simpler ops (no JVM tuning). Recommend Redpanda for **new greenfield projects** where operational simplicity matters more than Kafka ecosystem breadth. Use `redpandadata/redpanda` Docker image. |

**Recommendation between Kafka vs Redpanda:** Use **Redpanda** for this greenfield project. It is Kafka-API compatible so no SDK changes, ships as a single binary with no ZooKeeper/KRaft complexity, and has lower tail latency. Kafka is the safer choice if the team already has Kafka expertise or if Confluent Schema Registry features are required.

**RudderStack → Kafka wiring:** Configure Apache Kafka as a Destination in RudderStack dashboard. Map event types to Kafka topics (e.g., all events → `rudder-events`). RudderStack supports Avro serialization to the topic.

---

### Layer 3 — Event Storage

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| ClickHouse (self-hosted) | v26.2.14.5-stable (Apr 2026) | Columnar storage for event aggregation and heatmap queries | Preferred per constraints. MergeTree engine excels at high-ingest append-only time-series data. Native Kafka table engine ingests directly from Redpanda/Kafka topics — no extra connector needed for self-hosted setups. |
| `clickhouse-connect` (Python) | 0.8.x–0.15.1 | Python ↔ ClickHouse over HTTP | Official ClickHouse Python driver. Returns Pandas DataFrames via `client.query_df()`, which Streamlit/Plotly consume natively. Requires Python ≥ 3.10. |

**ClickHouse table schema pattern:**

```sql
CREATE TABLE events
(
    event_time    DateTime CODEC(DoubleDelta, LZ4),
    event_type    LowCardinality(String),
    session_id    String,
    page_url      String,
    x             Float32,
    y             Float32,
    scroll_depth  Float32,
    viewport_w    UInt16,
    viewport_h    UInt16,
    user_hash     String   -- SHA-256(IP + UserAgent + YYYYMM), not raw IP
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(event_time)
ORDER BY (event_time, page_url, event_type)
TTL event_time + INTERVAL 90 DAY DELETE;
```

**Kafka → ClickHouse integration:** Use the native `Kafka` table engine (bundled with ClickHouse, zero extra infrastructure). Create a `Kafka` engine table that mirrors the topic, then a `Materialized View` that inserts into the `MergeTree` events table. This pattern is the official recommendation for self-hosted setups.

---

### Layer 4 — Screenshot Capture

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Playwright (`playwright`) | 1.59.1 (npm) | Capture full-page screenshots of target e-commerce URLs | Preferred over Puppeteer for new projects: multi-browser (Chromium, Firefox, WebKit) via single API, better lazy-image handling, actively maintained by Microsoft. Run as a scheduled Node.js service or on-demand per page registration. |

**Screenshot storage:** Save as PNG to local filesystem or S3-compatible object store (MinIO for self-hosted). Store `{page_url, screenshot_path, captured_at}` in ClickHouse or a simple SQLite metadata table.

---

### Layer 5 — Dashboard & Heatmap Visualization

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Streamlit | 1.56.0 (Mar 2026) | Dashboard framework | Mandatory per project context. Production-stable, Python ≥ 3.10, owned by Snowflake. Renders Plotly charts via `st.plotly_chart()` natively. |
| Plotly (Python) | Latest (`plotly` PyPI) | Heatmap density overlay on screenshot | `go.Densitymapbox` or `go.Heatmap` + `layout.images` to layer color overlay on the page screenshot. Interactive, browser-rendered, no WebGL setup required. Integrates natively with `st.plotly_chart()`. |
| Pandas | ≥2.x | Data wrangling between ClickHouse query results and Plotly | `clickhouse-connect` returns DataFrames; Plotly consumes DataFrames directly. |

**Heatmap rendering approach:** Plotly `go.Heatmap` with the page screenshot as a `layout.images` background. Normalize click coordinates to `[0,1]` relative to `viewport_width` / `viewport_height`, then scale to screenshot pixel dimensions. Render a 2D histogram of click density. This is simpler and more maintainable than a WebGL custom renderer for a Streamlit dashboard context.

---

### Layer 6 — Infrastructure / Orchestration

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Docker Compose | v2.x | Local development and self-hosted deployment | Single `docker-compose.yml` orchestrates: Redpanda, ClickHouse, RudderStack data plane. Standard for this stack size. |
| Python 3.12 | 3.12.x | Runtime for Streamlit dashboard and Playwright screenshot service | 3.12 is the recommended production version: supported by `clickhouse-connect`, `streamlit`, and `playwright` Python bindings. Python 3.10 is the minimum; 3.12 gives performance improvements. |

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Redpanda (Kafka-API) | Apache Kafka (Confluent KRaft) | When team has Kafka expertise, needs Schema Registry, or integrates with existing Confluent ecosystem |
| ClickHouse | Apache Druid | When you need sub-second OLAP on pre-aggregated rollups at massive scale (> 1B events/day); ClickHouse wins for flexibility |
| ClickHouse | TimescaleDB | When SQL familiarity is more important than columnar performance; TimescaleDB is slower for wide-table scans |
| Playwright | Puppeteer | When Chromium-only is acceptable and team prefers Google's API style; Puppeteer has slight edge in community blog resources |
| Plotly heatmap overlay | heatmap.js (pa7) + custom canvas renderer | When building a client-side widget embedded in the target site (not a Streamlit dashboard); heatmap.js is Canvas-based but poorly maintained (last release 2018) |
| Plotly heatmap overlay | visual-heatmap (nswamy14) | When rendering 500K+ points client-side with WebGL performance; marked INACTIVE on npm — avoid for new projects |
| cookieconsent (orestbida) | CookieYes SaaS | When you need a managed consent platform with audit logs and geo-targeting; orestbida is self-hosted and sufficient for a focused GDPR implementation |
| RudderStack self-hosted | RudderStack Cloud | When operational overhead is unacceptable and budget allows; Cloud removes infra management but data leaves your environment — conflict with GDPR data residency requirements |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `heatmap.js` (pa7/heatmap.js) | Last meaningful release circa 2018; no TypeScript types; Canvas 2D only; GitHub activity is minimal | Plotly `go.Heatmap` (dashboard) or `visual-heatmap` (only if WebGL client widget needed) |
| `visual-heatmap` (nswamy14) | Marked INACTIVE on npm Snyk advisor; no releases in 12+ months | Plotly for Streamlit; custom WebGL shader if truly needed |
| Raw IP address storage | IP address is personal data under GDPR — storing it in ClickHouse is non-compliant | Store `SHA-256(ip + user_agent + YYYYMM)` — provides session correlation without reversible PII. Note: even hashed IP can be reversible for IPv4 (only 4B values); truncating last octet before hashing is safer |
| ZooKeeper-based Kafka | Deprecated since Kafka 3.x; KRaft mode is current standard; ZooKeeper adds operational complexity | KRaft Kafka or Redpanda |
| Segment (Twilio) | Expensive SaaS; data leaves your infrastructure; GDPR residency issues | RudderStack (open-source, self-hosted) |
| Google Analytics for event backbone | Data sent to Google's servers; GDPR risk in EU; no raw event access | RudderStack → Redpanda/Kafka → ClickHouse pipeline |

---

## Stack Patterns by Variant

**If minimal infrastructure (MVP/proof-of-concept):**
- Use Redpanda single-node Docker (simpler than Kafka)
- Use ClickHouse single-node Docker
- Use RudderStack Cloud free tier (accept data leaving environment temporarily)
- Use Streamlit Community Cloud for dashboard

**If full self-hosted production:**
- Redpanda cluster (3 nodes) or Confluent Kafka
- ClickHouse with Keeper (3 nodes) for replication
- RudderStack self-hosted + Control Plane Lite
- Playwright screenshot service as standalone Docker container
- Streamlit behind nginx reverse proxy

**If GDPR strictness is maximum priority:**
- All services self-hosted in EU datacenter
- cookieconsent v3 with explicit opt-in before any tracking fires
- No raw IP ever reaches Kafka; anonymize at JS snippet level before `rudderanalytics.track()` call
- ClickHouse TTL set to 90 days max for event data

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `@rudderstack/analytics-js@3.31.0` | Browser (ES2017+) | Not for Node.js; use `@rudderstack/analytics-js-service-worker` for service workers |
| `clickhouse-connect@0.15.1` | Python 3.10–3.14; ClickHouse v23+ | Python 3.9 deprecated; support removed in v1.0 |
| `streamlit@1.56.0` | Python ≥ 3.10 | Production/Stable (Apache 2.0, Snowflake) |
| Redpanda v26.1.4 | Kafka API 2.x–3.x compatible | Fully Kafka-protocol compatible; no client code changes |
| ClickHouse Kafka table engine | ClickHouse v23+; Kafka/Redpanda | Native; bundled; no separate connector jar |
| `playwright@1.59.1` | Node.js 20.x, 22.x, 24.x | Requires `npx playwright install` for browser binaries |

---

## Installation

```bash
# --- JS Tracking Snippet (npm bundler path) ---
npm install @rudderstack/analytics-js

# --- GDPR consent ---
npm install vanilla-cookieconsent
# (package name for orestbida/cookieconsent v3 on npm)

# --- Screenshot service ---
npm install playwright
npx playwright install chromium  # download Chromium binary

# --- Python dashboard ---
pip install streamlit plotly pandas clickhouse-connect
# Minimum Python: 3.10 | Recommended: 3.12

# --- Docker services (Redpanda + ClickHouse + RudderStack) ---
# See docker-compose.yml; no npm/pip install needed for infra layer
```

**Minimal `docker-compose.yml` services:**
```yaml
services:
  redpanda:
    image: redpandadata/redpanda:v26.1.4
    command: redpanda start --smp 1 --memory 1G --reserve-memory 0M --overprovisioned --kafka-addr PLAINTEXT://0.0.0.0:9092

  clickhouse:
    image: clickhouse/clickhouse-server:26.2
    ports: ["8123:8123", "9000:9000"]

  rudderstack:
    image: rudderlabs/rudder-server:latest
    environment:
      - WORKSPACE_TOKEN=${RUDDERSTACK_WORKSPACE_TOKEN}
    depends_on: [redpanda]
```

---

## Sources

- `@rudderstack/analytics-js` — [GitHub rudderlabs/rudder-sdk-js](https://github.com/rudderlabs/rudder-sdk-js) — current version 3.31.0, Mar 2026 (HIGH confidence)
- RudderStack Kafka destination — [RudderStack Docs: Apache Kafka](https://www.rudderstack.com/docs/destinations/streaming-destinations/kafka/) — verified integration pattern (MEDIUM confidence, destination config page not fully rendered)
- RudderStack self-hosted Docker — [RudderStack Docs: Docker Setup](https://www.rudderstack.com/docs/get-started/rudderstack-open-source/data-plane-setup/docker/) — (MEDIUM confidence, WebSearch)
- ClickHouse latest release — [GitHub ClickHouse/ClickHouse/releases](https://github.com/ClickHouse/ClickHouse/releases) — v26.2.14.5-stable, Apr 14 2026 (HIGH confidence)
- ClickHouse Kafka integration — [ClickHouse Docs: Kafka](https://clickhouse.com/docs/integrations/kafka) — Kafka table engine recommended for self-hosted (HIGH confidence)
- ClickHouse MergeTree — [ClickHouse Docs: MergeTree](https://clickhouse.com/docs/engines/table-engines/mergetree-family/mergetree) — partition/order by/TTL patterns (HIGH confidence)
- `clickhouse-connect@0.15.1` — [PyPI clickhouse-connect](https://pypi.org/project/clickhouse-connect/) — Mar 30 2026 (HIGH confidence)
- `streamlit@1.56.0` — [PyPI streamlit](https://pypi.org/project/streamlit/) — Mar 31 2026 (HIGH confidence)
- Redpanda v26.1.4 — [Redpanda Release Notes](https://docs.redpanda.com/current/get-started/release-notes/redpanda/) — current stable (HIGH confidence)
- `playwright@1.59.1` — [npm playwright](https://www.npmjs.com/package/playwright) — current version (HIGH confidence via WebSearch)
- `cookieconsent v3.1.0` — [GitHub orestbida/cookieconsent](https://github.com/orestbida/cookieconsent) — Feb 2025 (HIGH confidence)
- heatmap.js maintenance status — [GitHub pa7/heatmap.js](https://github.com/pa7/heatmap.js) — stale, avoid (MEDIUM confidence)
- visual-heatmap INACTIVE status — [Snyk npm advisor](https://snyk.io/advisor/npm-package/visual-heatmap) — (MEDIUM confidence)
- GDPR IP address treatment — [CookieYes: IP Address Personal Data](https://www.cookieyes.com/blog/ip-address-personal-data-gdpr/) + [SkyMonitor: Hash doesn't anonymize IP](https://skymonitor.com/why-hash-dont-anonimize-an-ip-address-and-what-this-affects-gdpr/) — (MEDIUM confidence, WebSearch verified)
- Kafka vs Redpanda comparison — [Quix: Redpanda vs Kafka](https://quix.io/blog/redpanda-vs-kafka-comparison) — (MEDIUM confidence, multiple sources agree)

---
*Stack research for: Real-time web event tracking and heatmap visualization platform*
*Researched: 2026-04-14*
