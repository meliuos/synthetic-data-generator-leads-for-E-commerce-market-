# Project Research Summary

**Project:** Real-time Web Event Tracking and Heatmap Visualization Platform
**Domain:** Web analytics / heatmap visualization for e-commerce
**Researched:** 2026-04-14
**Confidence:** HIGH (stack and architecture verified against official docs; features cross-referenced against 3 competitors; pitfalls confirmed against ClickHouse/Kafka official sources)

---

## Executive Summary

This project is a self-hosted, GDPR-compliant web analytics platform that captures user interaction events (clicks, scrolls, mouse movement) via a lightweight JavaScript snippet, routes them through a streaming pipeline (RudderStack → Redpanda/Kafka → ClickHouse), and surfaces heatmap visualizations in a Streamlit dashboard. The recommended architecture is a strict 5-layer pipeline: browser capture → event ingestion → streaming buffer → columnar storage → visualization. Every major competitor (Microsoft Clarity, PostHog, Hotjar) confirms the same core feature set: click heatmaps, scroll maps, rage click detection, and device/date/URL filtering. The architecture is well-documented with production case studies for the exact Redpanda + ClickHouse + Streamlit combination.

The single most important technical decision is coordinate normalization: all click coordinates must be converted to document-relative percentages (pageX/pageY divided by scrollWidth/scrollHeight) in the browser before transmission. This cannot be retrofitted — wrong coordinates stored at ingestion time are unrecoverable without raw event replay. The second most important decision is the ClickHouse MergeTree ORDER BY key, which must lead with low-cardinality filter columns (page_url, device_type) rather than timestamp or event ID. Both decisions must be locked before any data flows.

The principal risks are: (1) coordinate system confusion between clientX (viewport-relative) and pageX (document-relative) causing silent heatmap misalignment; (2) ClickHouse insert hammering from per-event inserts causing "Too many parts" errors; (3) GDPR non-compliance from pre-consent tracking or raw IP storage. All three are preventable at the schema/tracker design stage. Mouse movement heatmaps, session replay, and AI summaries should be explicitly deferred — they create disproportionate infrastructure cost relative to their analytical value at this stage.

---

## Key Findings

### Recommended Stack

The stack is well-defined and constraint-driven. RudderStack (self-hosted, `rudderlabs/rudder-server`) is mandatory for event ingestion and provides a Kafka destination out of the box. For the streaming layer, Redpanda is preferred over standard Kafka for greenfield projects: it is Kafka-API compatible (no client changes), runs as a single binary without ZooKeeper, and has lower operational complexity. ClickHouse is the designated columnar store; its native Kafka table engine pulls directly from Redpanda topics with no additional connector infrastructure required. The dashboard is Streamlit (Python 3.12) with Plotly overlays for heatmap rendering on top of Playwright-captured page screenshots.

**Core technologies:**
- `@rudderstack/analytics-js` v3.31.0: browser SDK — buffers, enriches, and delivers events to the self-hosted data plane
- Redpanda v26.1.4: Kafka-API-compatible event broker — simpler than Kafka, no ZooKeeper, lower tail latency
- ClickHouse v26.2: columnar store — MergeTree with native Kafka engine for zero-connector ingestion
- `clickhouse-connect` 0.15.1 (Python): ClickHouse to Python bridge — returns Pandas DataFrames natively
- Playwright 1.59.1: headless browser screenshot service — captures full-page PNGs at fixed viewport widths
- Streamlit 1.56.0 + Plotly: dashboard and heatmap overlay rendering — mandatory per project context
- `vanilla-cookieconsent` v3.1.0: GDPR consent gate — blocks tracker initialization until explicit opt-in

**Critical version constraints:** Python 3.12 (minimum 3.10); ClickHouse v23+; Node.js 20/22/24 for Playwright.

### Expected Features

Competitor analysis (Microsoft Clarity, PostHog, Hotjar, Crazy Egg) confirms a tight set of table-stakes features that every user will expect. The click heatmap overlay on a page screenshot is the core deliverable; without it, the product has no identity. Scroll depth maps and rage click detection are low-cost, high-value additions that every major competitor includes. Filtering by date range, device type, and URL is non-negotiable — without these, a single heatmap over all devices is misleading and useless for e-commerce analysis.

**Must have (table stakes):**
- Click heatmap overlay on page screenshot — core value proposition; every competitor has it
- Scroll depth map — shows fold position; Clarity, PostHog, Hotjar all include it
- Rage click detection — signals UX frustration; 3+ clicks within ~1 second on same element
- Filter by date range, device type, URL/page — required denominators for all heatmap interpretation
- URL wildcard grouping (/product/*) — essential for e-commerce with many dynamic product pages
- Page view and session count display — required heatmap intensity denominator

**Should have (competitive):**
- Dead click detection — clicks on non-interactive elements; Clarity and PostHog both surface this
- Mouse movement heatmap — P2, must implement with 10 Hz throttling to avoid storage explosion
- Segment by traffic source/referrer — lets e-commerce teams compare paid vs organic behavior
- Multiple heatmap types switchable on same screenshot — reuses screenshot; swaps aggregation query
- Page-level summary panel — rage click %, avg scroll depth, total sessions at a glance
- PNG/CSV export — for stakeholder reporting; Clarity supports it

**Defer (v2+):**
- Real-time streaming heatmap — unique differentiator given Kafka pipeline, but requires materialized view tuning and WebSocket infrastructure
- Heatmap comparison mode (date-over-date) — requires stable screenshot versioning
- Conversion map (click to purchase) — requires ecommerce purchase event integration
- Session recording/replay — separate infrastructure; massive storage cost; GDPR complexity
- Funnel analysis — requires session stitching across page boundaries
- AI/LLM heatmap summaries — Phase 4+ per platform roadmap

### Architecture Approach

The architecture follows a strict unidirectional pipeline: Browser → RudderStack → Redpanda → ClickHouse (Kafka Engine → Materialized View → MergeTree) → Python Aggregator → Streamlit. The three-table ClickHouse ingestion pattern (kafka queue table, materialized view bridge, MergeTree target) is non-negotiable — querying the Kafka Engine table directly consumes offsets and loses data. Screenshots are captured on-demand by a Playwright service, cached by URL+viewport hash, and shared via a Docker volume with the Streamlit dashboard. Heatmap computation uses grid-based binning (5% buckets = 20x20 grid) computed entirely in ClickHouse SQL before results reach Python, preventing Python OOM errors.

**Major components:**
1. JS Tracking Snippet — captures click/scroll events, normalizes coordinates to document percentages, delivers via RudderStack SDK
2. RudderStack Data Plane (self-hosted) — validates, enriches with session/device context, routes to Redpanda Kafka destination
3. Redpanda — durable ordered event stream; decouples producers from ClickHouse consumer
4. ClickHouse (3-table pattern) — Kafka queue + materialized view + MergeTree persistent storage partitioned by month
5. Heatmap Aggregator — parameterized ClickHouse binning query; returns 2D grid, never raw events
6. Screenshot Capture Service (Playwright) — on-demand capture at 1440px/390px viewport, cached by URL hash
7. Streamlit Dashboard — loads screenshot, overlays Plotly heatmap grid, exposes page/date/device filters

### Critical Pitfalls

1. **clientX/clientY vs pageX/pageY coordinate confusion** — storing viewport-relative coordinates causes all heatmap points to drift upward by scroll distance; always use `pageX`/`pageY` and validate by clicking after scrolling 500px; corrupted coordinates cannot be retroactively corrected.

2. **ClickHouse per-event insert hammering** — inserting one row per Kafka message creates thousands of small parts, triggering "Too many parts" errors; use ClickHouse async inserts (`async_insert=1, wait_for_async_insert=1`) or micro-batch 1,000+ rows per INSERT; must be resolved before heatmap computation is built on top.

3. **Wrong ClickHouse MergeTree ORDER BY** — using `ORDER BY (event_time)` or a UUID as the leading key forces full table scans for every heatmap query; ORDER BY must be `(page_url, device_type, event_time)` to match query access patterns; changing this after data ingestion requires dropping and recreating the table.

4. **Unthrottled mousemove capture** — raw `mousemove` fires at 60Hz; a single 30-minute session generates 108,000 events; throttle to maximum 10 Hz (100ms) in the JS tracker before any data flows.

5. **Pre-consent tracking and raw IP storage** — initializing the tracker before the consent callback fires is a GDPR violation; IP addresses must not be stored as-is; anonymize by stripping the last octet or storing a salted hash.

---

## Implications for Roadmap

Based on architecture dependencies and pitfall priorities, a 5-phase build order is recommended. The dependency chain is strict: streaming infrastructure must exist before storage can be configured; storage must contain real events before heatmap computation is valid; screenshots must be available before the dashboard overlay is meaningful.

### Phase 1: Streaming and Storage Backbone

**Rationale:** All other components depend on Redpanda and ClickHouse being operational. The ORDER BY key decision (Pitfall 6) must be locked here — it cannot be changed without a full table rebuild. This phase has zero user-visible output but gates everything.

**Delivers:** Docker Compose with Redpanda + ClickHouse running; 3-table schema deployed (kafka queue + materialized view + MergeTree target); manual test confirming a JSON message inserted into the queue appears in click_events within seconds.

**Addresses:** Click/scroll/movement event storage prerequisites (schema for all heatmap features)

**Avoids:** Wrong ORDER BY (unrecoverable after data ingestion); ClickHouse insert hammering (configure async_insert at schema design time)

**Research flag:** Standard patterns — ClickHouse Kafka integration docs are comprehensive; no additional research needed.

---

### Phase 2: JS Tracker and Event Ingestion Pipeline

**Rationale:** The tracker is the highest-risk component because coordinate errors are unrecoverable. Building and validating it against real Redpanda/ClickHouse infrastructure immediately confirms the full pipeline. Consent gating must be implemented here, not retrofitted.

**Delivers:** Vanilla JS snippet with pageX/pageY normalization, 10Hz mousemove throttle, SPA route change detection, consent gate; RudderStack configured with Kafka destination; verification: click on test page → row in click_events within 5 seconds with correct coordinates.

**Addresses:** Click events, scroll depth events, rage click raw data collection, GDPR consent gating, IP anonymization

**Avoids:** clientX/clientY confusion (Pitfall 1); devicePixelRatio double-scaling (Pitfall 2); mousemove flood (Pitfall 4); SPA navigation blindness (Pitfall 5); pre-consent tracking (Pitfall 7)

**Research flag:** Needs validation — verify RudderStack self-hosted Kafka destination config against Redpanda broker; integration details need hands-on confirmation.

---

### Phase 3: Screenshot Capture Service

**Rationale:** The heatmap overlay is meaningless without a page screenshot as background. Independent of the data pipeline, this can be built in parallel with Phase 2.

**Delivers:** Playwright async capture at 1440px/390px viewport; URL+viewport hash caching; Docker container with shared volume; verified screenshot doc_height matches JS snippet's document.body.scrollHeight for same page.

**Addresses:** Heatmap overlay visualization prerequisite; screenshot alignment rule enforcement

**Avoids:** Running Playwright inside the Streamlit process (spawn OOM errors); storing screenshots as ClickHouse blobs

**Research flag:** Standard patterns — Playwright Python API is well-documented; no additional research needed.

---

### Phase 4: Heatmap Computation and Core Dashboard

**Rationale:** With data flowing and screenshots available, this phase assembles the user-facing product. All P1 features land here. Computation must happen in ClickHouse (5% bucket binning), not Python, to prevent memory issues.

**Delivers:** Parameterized ClickHouse binning query (5% buckets, 20x20 grid); Streamlit app with click heatmap overlay on screenshot; filters for date range, device type, URL; rage click detection visualization; scroll depth map; page view and session counts; URL wildcard grouping for /product/* patterns; @st.cache_data with TTL on all ClickHouse queries.

**Addresses:** All P1 features — click heatmap, scroll depth map, rage click detection, all filters, URL wildcard grouping, session/view counts

**Avoids:** Fetching raw events to Python (aggregate in ClickHouse; pull 400-cell grid not 50k rows); Streamlit recompute on every filter change; merging click data from different viewport widths

**Research flag:** Standard patterns — ClickHouse binning queries and Plotly overlay have multiple production case studies.

---

### Phase 5: P2 Feature Enrichment

**Rationale:** Once P1 heatmap pipeline is validated against real usage, add differentiating features. Mouse movement heatmap is only enabled after storage capacity is confirmed by load test.

**Delivers:** Dead click detection overlay; mouse movement heatmap (storage confirmed first); segment by UTM/referrer; switchable heatmap types (click/scroll/movement) on same screenshot; page-level summary panel; PNG/CSV export.

**Addresses:** All P2 features from FEATURES.md prioritization matrix

**Avoids:** Enabling raw mouse movement capture without confirmed storage budget; implementing real-time streaming (P3) before P1/P2 are validated

**Research flag:** Mouse movement storage budget needs load test before implementation — project ClickHouse growth at 10Hz throttle on actual target pages.

---

### Phase Ordering Rationale

- Phases 1 and 2 have an integration dependency but Phase 1 infra setup and Phase 2 tracker development can proceed in parallel; integration happens at Phase 2 verification.
- Phase 3 (screenshots) is independent of Phase 2 (tracker) and can be built concurrently.
- Phase 4 has a hard dependency on both Phase 1 (data in ClickHouse) and Phase 3 (screenshots available).
- Phase 5 must not begin until Phase 4 P1 features are confirmed accurate against real data.
- Session replay, funnel analysis, real-time streaming, and AI summaries are explicitly out of scope for this roadmap.

### Research Flags

**Needs deeper research during planning:**
- **Phase 2:** RudderStack self-hosted Kafka destination integration against Redpanda — recommend a spike task before building the full tracker around it.
- **Phase 5:** Mouse movement storage projection — benchmark at 10Hz throttle on specific target pages before enabling; 1 user × 30 min × 10 Hz = 18,000 events; project monthly ClickHouse growth.

**Standard patterns (skip research-phase):**
- **Phase 1:** ClickHouse 3-table Kafka ingestion documented with exact DDL; Redpanda Docker trivial.
- **Phase 3:** Playwright Python screenshot API fully documented with async pattern needed.
- **Phase 4:** ClickHouse binning queries and Plotly imshow overlay have production case studies.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core technologies verified against official docs and current package registries; Redpanda/Kafka choice is well-supported for greenfield |
| Features | HIGH | Cross-referenced against Microsoft Clarity, PostHog, Hotjar official docs; competitor feature boundaries are clear |
| Architecture | HIGH | 3-table Kafka ingestion in official ClickHouse docs; full Redpanda+ClickHouse+Streamlit pipeline confirmed in March 2026 production case study; coordinate normalization verified against MDN spec |
| Pitfalls | HIGH (technical) / MEDIUM (GDPR) | Coordinate, insert, and sorting key pitfalls verified against official docs; GDPR specifics depend on deployment jurisdiction |

**Overall confidence:** HIGH

### Gaps to Address

- **RudderStack self-hosted Kafka destination config against Redpanda:** Integration confirmed in docs but exact destination configuration fields need hands-on verification in Phase 2 spike.
- **Screenshot TTL / stale screenshot management:** Caching-by-hash is correct but no defined policy for layout changes on tracked pages; a scheduled refresh strategy for production should be defined during Phase 3 planning.
- **ClickHouse async_insert tuning under RudderStack batch load:** The async insert recommendation is correct; interaction between RudderStack batch sizes and ClickHouse async buffer parameters (`async_insert_max_data_size`, `async_insert_busy_timeout_ms`) needs benchmarking during Phase 1/2 integration.
- **Consent UX for academic demo context:** GDPR is not legally enforceable in a controlled GL4 demo, but demonstrating consent gating during the thesis defense is a differentiator; implementation depth should be decided during Phase 2 planning.

---

## Sources

### Primary (HIGH confidence)
- ClickHouse Kafka Table Engine official docs — 3-table ingestion pattern and Kafka table DDL
- ClickHouse MergeTree official docs — partition, ORDER BY, TTL patterns
- ClickHouse insert strategy official docs — async_insert configuration
- ClickHouse schema design for observability — column types, LowCardinality, Nullable anti-pattern
- ClickHouse AI-generated schema mistakes blog — sorting key and type pitfalls
- `clickhouse-connect` PyPI — version 0.15.1, Python compatibility
- `streamlit` PyPI — version 1.56.0
- Redpanda release notes — v26.1.4 stable (Apr 2026)
- `playwright` npm — version 1.59.1
- `@rudderstack/analytics-js` GitHub — version 3.31.0 (Mar 2026)
- MDN MouseEvent.pageX — coordinate space authoritative reference
- Mozilla Bugzilla MouseEvent coordinate space — coordinate system verification
- Microsoft Clarity official docs — heatmaps overview and click maps (updated 2025-12-05)
- PostHog official docs — heatmaps feature reference
- How to Build a User Behavior Heatmap with ClickHouse (Mar 2026) — full schema and binning queries
- In-game Analytics Pipeline: Redpanda + ClickHouse + Streamlit — exact integration pattern
- ClickHouse Python Dashboard with Streamlit (official ClickHouse resource)

### Secondary (MEDIUM confidence)
- RudderStack Kafka destination docs — integration confirmed, full config rendering not verified
- RudderStack Docker self-hosted setup docs
- Quix: Redpanda vs Kafka comparison — greenfield recommendation
- Clickstream heatmap with Quix/Kafka — coordinate normalization and 50x50 grid binning
- PostHog vs Hotjar blog — feature comparison
- Luniq: Hotjar vs Clarity vs FullStory 2026 — competitor feature matrix
- GDPR analytics compliance guide 2026 — IP address treatment
- CookieYes: IP address as personal data under GDPR
- SkyMonitor: why hash does not anonymize IPv4
- FullSession: SPA heatmaps route change pitfalls
- Kafka consumer rebalance storms guide
- Playwright vs Puppeteer 2026 comparison
- `orestbida/cookieconsent` v3.1.0 GitHub
- heatmap.js (pa7) — confirmed stale, avoid
- visual-heatmap Snyk npm advisor — confirmed INACTIVE, avoid

### Tertiary (LOW confidence)
- Docker Compose ClickHouse + Kafka community example — structure verified against official docs but not authoritative

---

*Research completed: 2026-04-14*
*Ready for roadmap: yes*
