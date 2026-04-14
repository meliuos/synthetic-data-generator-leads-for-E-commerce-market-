# Requirements: Lead Intelligence Platform — Event Tracking & Heatmap

**Defined:** 2026-04-15
**Core Value:** Show exactly where users click, scroll, and engage on any page — as a live heatmap overlay backed by a scalable real-time event pipeline.

## v1 Requirements

### Event Capture (JS Tracker)

- [ ] **TRACK-01**: JS snippet captures page view events (URL, timestamp, referrer, screen dimensions, device type)
- [ ] **TRACK-02**: JS snippet captures click events with document-relative coordinates (x_pct, y_pct as % of full document dimensions), CSS element selector, and tag name
- [ ] **TRACK-03**: JS snippet captures scroll depth — max percentage of page scrolled per session per URL
- [ ] **TRACK-04**: JS snippet captures mouse movement events throttled to 100ms intervals (x_pct, y_pct)
- [ ] **TRACK-05**: Snippet intercepts History API (pushState/replaceState) to detect SPA route changes and emit page view events
- [ ] **TRACK-06**: Cookie consent gate blocks all event capture until user accepts — RGPD compliant
- [ ] **TRACK-07**: All events emitted via RudderStack SDK (v3.x) to the Kafka/Redpanda pipeline

### Pipeline & Storage

- [ ] **PIPE-01**: Redpanda topic receives all events from RudderStack Kafka destination
- [ ] **PIPE-02**: ClickHouse Kafka Engine table consumes from Redpanda topic
- [ ] **PIPE-03**: Materialized View routes events into a MergeTree target table
- [ ] **PIPE-04**: MergeTree schema uses ORDER BY (page_url, event_type, toDate(event_time)) and stores: x_pct, y_pct, element_selector, device_type, session_id, anonymous_user_id (hashed — no raw PII)
- [ ] **PIPE-05**: Docker Compose spins up full stack locally: Redpanda + ClickHouse + RudderStack data plane + Streamlit

### Screenshot Service

- [ ] **SHOT-01**: Playwright service captures full-page screenshots for registered URLs at configured viewport widths (1440px desktop, 390px mobile)
- [ ] **SHOT-02**: Screenshots stored on disk and refreshable on demand from dashboard

### Heatmap Visualization

- [ ] **HEAT-01**: Click heatmap rendered as color intensity overlay on page screenshot (Plotly go.Heatmap + layout.images, 5% grid binning via ClickHouse GROUP BY)
- [ ] **HEAT-02**: Scroll depth heatmap rendered as horizontal gradient bands showing max scroll depth distribution
- [ ] **HEAT-03**: Hover/movement heatmap rendered from throttled mousemove events (same 5% grid)

### Dashboard

- [ ] **DASH-01**: Filter events by exact page URL or URL pattern with wildcard support (e.g. /product/*)
- [ ] **DASH-02**: Switch heatmap type between click / scroll / hover views
- [ ] **DASH-03**: Live event feed panel — real-time stream of latest incoming events (type, page, timestamp) demonstrating the pipeline is live
- [ ] **DASH-04**: Click ranking panel — top 10 most-clicked element selectors on the selected page
- [ ] **DASH-05**: Funnel / page flow visualization — Sankey or chord diagram showing which pages users visit in sequence
- [ ] **DASH-06**: Session stats panel — total sessions, average scroll depth, bounce rate, total events per page

## v2 Requirements

### Heatmap Enhancements

- **HEAT-04**: Rage click zones — highlight areas with 3+ rapid clicks within 400ms in same region
- **HEAT-05**: Dead click detection — clicks that produce no DOM change within 500ms
- **HEAT-06**: Side-by-side heatmap comparison between two time periods

### Filters

- **FILT-01**: Filter by date range (last 7/30/90 days or custom range)
- **FILT-02**: Filter by device type (desktop / mobile / tablet)

### Export

- **EXPO-01**: Export current heatmap view as PNG image

## Out of Scope

| Feature | Reason |
|---------|--------|
| Session replay (video) | Requires separate storage infrastructure and custom player — weeks of scope, not a heatmap feature |
| Lead scoring model | CdC Phase 5 — separate milestone |
| Synthetic data generation (CTGAN) | CdC Phase 3 — separate milestone |
| AI commercial assistant | CdC Phase 5 — separate milestone |
| Simulation engine (Mesa/SimPy) | CdC Phase 4 — separate milestone |
| RudderStack Cloud hosted | Self-hosted only — data stays local, RGPD compliant |
| Real-time heatmap updates | Batch refresh (60s) is sufficient; true streaming heatmap adds complexity without clear value |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PIPE-01 | Phase 1 | Pending |
| PIPE-02 | Phase 1 | Pending |
| PIPE-03 | Phase 1 | Pending |
| PIPE-04 | Phase 1 | Pending |
| PIPE-05 | Phase 1 | Pending |
| TRACK-01 | Phase 2 | Pending |
| TRACK-02 | Phase 2 | Pending |
| TRACK-03 | Phase 2 | Pending |
| TRACK-04 | Phase 2 | Pending |
| TRACK-05 | Phase 2 | Pending |
| TRACK-06 | Phase 2 | Pending |
| TRACK-07 | Phase 2 | Pending |
| SHOT-01 | Phase 3 | Pending |
| SHOT-02 | Phase 3 | Pending |
| HEAT-01 | Phase 4 | Pending |
| HEAT-02 | Phase 4 | Pending |
| HEAT-03 | Phase 4 | Pending |
| DASH-01 | Phase 4 | Pending |
| DASH-02 | Phase 4 | Pending |
| DASH-03 | Phase 5 | Pending |
| DASH-04 | Phase 5 | Pending |
| DASH-05 | Phase 5 | Pending |
| DASH-06 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-15*
*Last updated: 2026-04-15 after initial definition*
