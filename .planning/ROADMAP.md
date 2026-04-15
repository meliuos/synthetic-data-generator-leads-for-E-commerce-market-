# Roadmap: Lead Intelligence Platform — Event Tracking & Heatmap

## Overview

Five phases build from infrastructure upward: the streaming and storage backbone must exist before any data flows; the JS tracker validates the full pipeline end-to-end; the screenshot service provides the visual canvas; the core dashboard assembles the product; and the analytics features complete the demonstration. Each phase delivers a coherent, independently verifiable capability and gates the next.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Streaming and Storage Backbone** - Redpanda + ClickHouse running locally, 3-table schema locked, ORDER BY finalized
- [ ] **Phase 2: JS Tracker and Event Ingestion Pipeline** - Browser snippet captures events, RudderStack routes them, rows appear in ClickHouse within seconds
- [ ] **Phase 3: Screenshot Capture Service** - Playwright service captures full-page screenshots at desktop and mobile viewports, stored on disk
- [ ] **Phase 4: Heatmap Computation and Core Dashboard** - Streamlit dashboard renders click/scroll/hover heatmaps as Plotly overlays on screenshots with URL filter and type switcher
- [ ] **Phase 5: Analytics Features** - Live event feed, click ranking, page flow Sankey, and session stats complete the dashboard

## Phase Details

### Phase 1: Streaming and Storage Backbone
**Goal**: The full storage infrastructure is running locally and can accept events — pipeline decisions that cannot be changed after data flows are locked permanently.
**Depends on**: Nothing (first phase)
**Requirements**: PIPE-01, PIPE-02, PIPE-03, PIPE-04, PIPE-05
**Success Criteria** (what must be TRUE):
  1. `docker compose up` starts Redpanda, ClickHouse, RudderStack data plane, and Streamlit with no errors
  2. A JSON message manually produced to the Redpanda topic appears as a row in the `click_events` MergeTree table within 5 seconds
  3. The MergeTree ORDER BY is `(page_url, event_type, toDate(event_time))` and the schema stores `x_pct`, `y_pct`, `element_selector`, `device_type`, `session_id`, `anonymous_user_id` (hashed) — no raw PII columns exist
  4. ClickHouse async_insert is configured so the Kafka engine does not hammer with per-row inserts
**Plans**: 4 plans in 4 waves

Plans:
- [x] 01-01: Docker Compose stack (Redpanda + ClickHouse + RudderStack data plane)
- [x] 01-02: ClickHouse 3-table schema (Kafka queue + Materialized View + MergeTree target)
- [x] 01-03: End-to-end smoke test (manual produce → row in MergeTree)

### Phase 2: JS Tracker and Event Ingestion Pipeline
**Goal**: A JavaScript snippet embedded in any page captures all required event types with correct document-relative coordinates and GDPR consent gating, and delivers them into ClickHouse through RudderStack and Redpanda.
**Depends on**: Phase 1
**Requirements**: TRACK-01, TRACK-02, TRACK-03, TRACK-04, TRACK-05, TRACK-06, TRACK-07
**Success Criteria** (what must be TRUE):
  1. Clicking anywhere on a test page after scrolling 500 px stores a row with `x_pct`/`y_pct` values that match the document-relative position (not viewport-relative), visible in ClickHouse within 5 seconds
  2. Scrolling to 75% of a test page stores a scroll_depth event with `scroll_pct = 75` for that session and URL
  3. Mouse movement events arrive throttled — no more than 10 events per second per session appear in ClickHouse
  4. Navigating between SPA routes triggers a new page_view event for each route change without a full page reload
  5. No events appear in ClickHouse until the cookie consent banner has been accepted by the user
**Plans**: 4 plans in 2 waves

Plans:
- [ ] 02-01: JS tracker with click, scroll, mousemove, page_view capture and document-relative coordinate normalization
- [ ] 02-02: RudderStack SDK integration and Kafka destination verification against Redpanda (resolves blocker)
- [ ] 02-03: Cookie consent gate with vanilla-cookieconsent v3.1.0 (GDPR compliance)
- [ ] 02-04: End-to-end browser validation (click/scroll/navigate → ClickHouse row verification)

### Phase 3: Screenshot Capture Service
**Goal**: A standalone Playwright service captures full-page screenshots at desktop and mobile viewports for any registered URL, stores them on disk, and makes them refreshable from the dashboard.
**Depends on**: Phase 1 (shared Docker volume and Compose stack)
**Requirements**: SHOT-01, SHOT-02
**Success Criteria** (what must be TRUE):
  1. Calling the screenshot service for a given URL produces two PNG files — one at 1440px viewport width and one at 390px — stored at a predictable path derived from the URL and viewport
  2. The captured screenshot's full document height matches `document.body.scrollHeight` reported by the JS snippet for the same page (within 5%)
  3. Screenshots can be refreshed on demand from the dashboard without restarting the service
**Plans**: 2 plans in 2 waves

Plans:
- [ ] 03-01: Playwright async screenshot service (1440px + 390px, URL+viewport hash caching, Docker container)
- [ ] 03-02: Dashboard refresh trigger and shared volume wiring

### Phase 4: Heatmap Computation and Core Dashboard
**Goal**: A Streamlit dashboard loads a page screenshot and overlays a Plotly heatmap computed entirely in ClickHouse, with controls to switch heatmap type and filter by URL.
**Depends on**: Phase 2 (events in ClickHouse), Phase 3 (screenshots on disk)
**Requirements**: HEAT-01, HEAT-02, HEAT-03, DASH-01, DASH-02
**Success Criteria** (what must be TRUE):
  1. Selecting a page URL in the dashboard renders a click heatmap as a Plotly color intensity overlay on the correct page screenshot, with brighter regions where more clicks occurred
  2. Switching to scroll depth view renders horizontal gradient bands on the same screenshot reflecting the distribution of max scroll depth across sessions
  3. Switching to hover/movement view renders a heatmap from throttled mousemove events on the same screenshot
  4. Entering a URL pattern with a wildcard (e.g. `/product/*`) aggregates events from all matching pages into a single heatmap
  5. All heatmap data is aggregated in ClickHouse using 5% grid binning before reaching Python — no raw event rows are fetched to the dashboard process
**Plans**: 4 plans in 4 waves

Plans:
- [ ] 04-01: ClickHouse binning queries (5% buckets, 20x20 grid, parameterized by URL, event type, viewport)
- [ ] 04-02: Streamlit app scaffold + screenshot loader + Plotly heatmap overlay
- [ ] 04-03: URL filter with wildcard support + heatmap type switcher
- [ ] 04-04: Scroll depth heatmap and hover heatmap views

### Phase 5: Analytics Features
**Goal**: The dashboard surfaces a live event feed, click ranking, page flow visualization, and session statistics — completing the full demonstration capability.
**Depends on**: Phase 4
**Requirements**: DASH-03, DASH-04, DASH-05, DASH-06
**Success Criteria** (what must be TRUE):
  1. The live event feed panel updates every 60 seconds and displays the most recent incoming events (type, page URL, timestamp) confirming the pipeline is live
  2. The click ranking panel shows the top 10 most-clicked CSS element selectors for the currently selected page
  3. The page flow panel renders a Sankey diagram showing which pages users visit in sequence across sessions
  4. The session stats panel displays total sessions, average scroll depth, bounce rate, and total events for the selected page
**Plans**: TBD

Plans:
- [ ] 05-01: Live event feed panel (polling query, 60s refresh)
- [ ] 05-02: Click ranking panel (top 10 element selectors)
- [ ] 05-03: Page flow Sankey diagram (session sequence query + Plotly Sankey)
- [ ] 05-04: Session stats panel (sessions, avg scroll depth, bounce rate, total events)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Streaming and Storage Backbone | 3/3 | Complete | 01-01, 01-02, 01-03 |
| 2. JS Tracker and Event Ingestion Pipeline | 0/4 | Planned | 02-01, 02-02, 02-03, 02-04 |
| 3. Screenshot Capture Service | 2/2 | Implemented (checkpoint pending) | 03-01, 03-02 |
| 4. Heatmap Computation and Core Dashboard | 0/4 | Not started | - |
| 5. Analytics Features | 0/4 | Not started | - |
