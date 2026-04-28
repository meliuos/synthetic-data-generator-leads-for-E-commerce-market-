# Requirements: Lead Intelligence Platform — Event Tracking & Heatmap

**Defined:** 2026-04-15 (v1.0) / 2026-04-18 (v1.1)
**Core Value:** Capture user behavior signals that identify purchase-intent leads for an e-commerce site — heatmap engagement plus e-commerce intent events — backed by a scalable real-time event pipeline.

## v1.0 Requirements (Shipped)

All v1.0 requirements shipped 2026-04-16. Phase 5 (DASH-03 through DASH-06) was dropped at v1.1 pivot; useful parts rolled into v1.1.

### Event Capture (JS Tracker) — v1.0

- [x] **TRACK-01**: JS snippet captures page view events (URL, timestamp, referrer, screen dimensions, device type)
- [x] **TRACK-02**: JS snippet captures click events with document-relative coordinates (x_pct, y_pct), CSS element selector, and tag name
- [x] **TRACK-03**: JS snippet captures scroll depth — max percentage of page scrolled per session per URL
- [x] **TRACK-04**: JS snippet captures mouse movement events throttled to 100ms intervals (x_pct, y_pct)
- [x] **TRACK-05**: Snippet intercepts History API (pushState/replaceState) to detect SPA route changes and emit page view events
- [x] **TRACK-06**: Cookie consent gate blocks all event capture until user accepts — RGPD compliant
- [x] **TRACK-07**: All events emitted via RudderStack SDK (v3.x) to the Kafka/Redpanda pipeline

### Pipeline & Storage — v1.0

- [x] **PIPE-01**: Redpanda topic receives all events from RudderStack Kafka destination
- [x] **PIPE-02**: ClickHouse Kafka Engine table consumes from Redpanda topic
- [x] **PIPE-03**: Materialized View routes events into a MergeTree target table
- [x] **PIPE-04**: MergeTree schema uses ORDER BY (page_url, event_type, toDate(event_time)) and stores: x_pct, y_pct, element_selector, device_type, session_id, anonymous_user_id (hashed — no raw PII)
- [x] **PIPE-05**: Docker Compose spins up full stack locally: Redpanda + ClickHouse + RudderStack data plane + Streamlit

### Screenshot Service — v1.0

- [x] **SHOT-01**: Playwright service captures full-page screenshots for registered URLs at configured viewport widths (1440px desktop, 390px mobile)
- [x] **SHOT-02**: Screenshots stored on disk and refreshable on demand from dashboard

### Heatmap Visualization — v1.0

- [x] **HEAT-01**: Click heatmap rendered as color intensity overlay on page screenshot (Plotly go.Heatmap + layout.images, 5% grid binning via ClickHouse GROUP BY)
- [x] **HEAT-02**: Scroll depth heatmap rendered as horizontal gradient bands showing max scroll depth distribution
- [x] **HEAT-03**: Hover/movement heatmap rendered from throttled mousemove events (same 5% grid)

### Dashboard — v1.0

- [x] **DASH-01**: Filter events by exact page URL or URL pattern with wildcard support (e.g. /product/*)
- [x] **DASH-02**: Switch heatmap type between click / scroll / hover views

### Dropped at v1.1 pivot

- ~~**DASH-03**: Live event feed panel~~ — dropped; doesn't serve lead intel
- ~~**DASH-05**: Funnel / page flow Sankey~~ — dropped; doesn't serve lead intel
- ~~**DASH-04**: Click ranking panel~~ → **rolled into v1.1 as STATS-02**
- ~~**DASH-06**: Session stats panel~~ → **rolled into v1.1 as STATS-01**

## v1.1 Requirements (Active)

Scope: capture lead-informative e-commerce events, import Retailrocket dataset, add useful panels rolled over from dropped Phase 5. No lead scoring in this milestone (deferred to v1.2).

### E-commerce Event Capture

- [x] **ECOM-01**: Tracker exposes `tracker.productView({product_id, category, price, currency})` and emits a `product_view` event
- [x] **ECOM-02**: Tracker exposes `tracker.addToCart({product_id, quantity, price})` and emits an `add_to_cart` event
- [x] **ECOM-03**: Tracker exposes `tracker.removeFromCart({product_id, quantity})` and emits a `remove_from_cart` event
- [x] **ECOM-04**: Tracker exposes `tracker.purchase({order_id, total, items, currency})` and emits a `purchase` event
- [x] **ECOM-05**: Tracker exposes `tracker.search({query, results_count})` and emits a `search` event
- [x] **ECOM-06**: All 5 e-commerce APIs inherit the existing consent gate (no capture before opt-in)
- [x] **ECOM-07**: Test SPA page exercises every e-commerce API with real click affordances (product cards, cart, checkout, search bar)

### Schema Extension

- [x] **SCHEMA-01**: `analytics.click_events` gains additive columns for e-commerce fields: `product_id`, `category`, `price`, `quantity`, `order_id`, `cart_value`, `search_query`, `results_count` — all `Nullable` so v1.0 events still insert without change
- [x] **SCHEMA-02**: Materialized view extracts the new fields from both flat and `properties` JSON shapes (consistent with v1.0 pattern)
- [x] **SCHEMA-03**: Schema migration is idempotent and runs via `make schema` without dropping or rebuilding the table

### Retailrocket Dataset Import

- [x] **DATA-01**: Retailrocket CSVs (events.csv, item_properties_part1.csv, item_properties_part2.csv, category_tree.csv) are downloadable and documented in the README
- [x] **DATA-02**: Import script normalizes Retailrocket rows into ClickHouse parallel tables (`analytics.retailrocket_*` / `retailrocket_raw.*`) preserving visitor, item, event type, timestamp, and transaction id
- [x] **DATA-03**: Import is idempotent — rerunning the script doesn't duplicate rows
- [x] **DATA-04**: Item properties (category id, price where available) are joinable from the events table
- [x] **DATA-05**: Category tree is loaded as a separate ClickHouse table for hierarchical joins
- [x] **DATA-06**: Smoke query verifies imported row count matches the source CSV and event-type distribution (view / addtocart / transaction)

### Dashboard Panels (rolled from dropped Phase 5)

- [x] **STATS-01**: Session stats panel displays total sessions, average scroll depth, bounce rate, and total events for the selected page scope — aggregated in ClickHouse, not Python
- [x] **STATS-02**: Click ranking panel shows the top 10 most-clicked CSS element selectors on the selected page scope

## v2 / Future Requirements

Deferred to later milestones (v1.2+).

### Lead Scoring & Identification — v1.2

- [x] **LEAD-01**: Rule-based lead score from behavioral signals (cart abandonment, repeat product views, search intent)
- [x] **LEAD-02**: Dashboard panel listing candidate leads with score breakdown
- [ ] **LEAD-03**: ML lead scoring model trained on Retailrocket (logistic regression / lightgbm baseline)

### Synthetic Data & Simulation — CdC Phase 3/4

- **SYNTH-01..N**: CTGAN/behavioral simulation — separate milestone

### AI Sales Assistant — CdC Phase 5

- **AI-01..N**: LLM-driven script generation — separate milestone

## Out of Scope (v1.1)

| Feature | Reason |
|---------|--------|
| Session replay (video) | Requires separate storage infrastructure and custom player — weeks of scope, not a lead feature |
| Lead scoring model | v1.2 — requires stable event corpus first |
| Synthetic data generation (CTGAN) | CdC Phase 3 — separate milestone |
| AI commercial assistant | CdC Phase 5 — separate milestone |
| Live event feed panel | Dropped from v1.0 Phase 5 — doesn't serve lead intel |
| Page flow Sankey diagram | Dropped from v1.0 Phase 5 — doesn't serve lead intel |
| Real-time heatmap updates | Batch refresh (60s) is sufficient |
| Mobile SDK | Web-first, mobile is a separate milestone |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PIPE-01 | Phase 1 | Complete |
| PIPE-02 | Phase 1 | Complete |
| PIPE-03 | Phase 1 | Complete |
| PIPE-04 | Phase 1 | Complete |
| PIPE-05 | Phase 1 | Complete |
| TRACK-01 | Phase 2 | Complete |
| TRACK-02 | Phase 2 | Complete |
| TRACK-03 | Phase 2 | Complete |
| TRACK-04 | Phase 2 | Complete |
| TRACK-05 | Phase 2 | Complete |
| TRACK-06 | Phase 2 | Complete |
| TRACK-07 | Phase 2 | Complete |
| SHOT-01 | Phase 3 | Complete |
| SHOT-02 | Phase 3 | Complete |
| HEAT-01 | Phase 4 | Complete |
| HEAT-02 | Phase 4 | Complete |
| HEAT-03 | Phase 4 | Complete |
| DASH-01 | Phase 4 | Complete |
| DASH-02 | Phase 4 | Complete |
| SCHEMA-01 | Phase 5 (v1.1) | Complete |
| SCHEMA-02 | Phase 5 (v1.1) | Complete |
| SCHEMA-03 | Phase 5 (v1.1) | Complete |
| ECOM-01 | Phase 6 (v1.1) | Complete |
| ECOM-02 | Phase 6 (v1.1) | Complete |
| ECOM-03 | Phase 6 (v1.1) | Complete |
| ECOM-04 | Phase 6 (v1.1) | Complete |
| ECOM-05 | Phase 6 (v1.1) | Complete |
| ECOM-06 | Phase 6 (v1.1) | Complete |
| ECOM-07 | Phase 6 (v1.1) | Complete |
| DATA-01 | Phase 7 (v1.1) | Complete |
| DATA-02 | Phase 7 (v1.1) | Complete |
| DATA-03 | Phase 7 (v1.1) | Complete |
| DATA-04 | Phase 7 (v1.1) | Complete |
| DATA-05 | Phase 7 (v1.1) | Complete |
| DATA-06 | Phase 7 (v1.1) | Complete |
| STATS-01 | Phase 8 (v1.1) | Complete |
| STATS-02 | Phase 8 (v1.1) | Complete |
| LEAD-01 | Phase 9 (v1.2) | Complete |
| LEAD-02 | Phase 9 (v1.2) | Complete |
| LEAD-03 | v1.2 | Pending |

**Coverage:**
- v1.0: 19 requirements, all shipped (4 dropped from Phase 5, 2 rolled into v1.1)
- v1.1: 18 requirements, all mapped to Phases 5-8 (SCHEMA→5, ECOM→6, DATA→7, STATS→8)

---
*Requirements defined: 2026-04-15 (v1.0) / 2026-04-18 (v1.1)*
*Last updated: 2026-04-19 — Phase 6 completed (ECOM-01..07 marked complete)*
