# Milestones

Shipped milestones for the Lead Intelligence Platform. Each milestone records what shipped, what was dropped, and why — the canonical record the roadmap continues from.

---

## v1.0 — Heatmap Core

**Status:** Complete
**Shipped:** 2026-04-16
**Phases:** 1–4 (Phase 5 dropped)

### What Shipped

End-to-end heatmap platform for tracking user interaction on any page:

- **Phase 1 — Streaming and Storage Backbone** — Redpanda + ClickHouse + RudderStack data plane in Docker Compose. 3-table ingestion pattern (Kafka engine + materialized view + MergeTree target). 5-second ingestion SLA verified by smoke test.
- **Phase 2 — JS Tracker and Event Ingestion Pipeline** — vanilla JS tracker in [src/tracker/](../src/tracker/) captures clicks with document-relative `x_pct`/`y_pct`, scroll depth, throttled mousemove (10Hz), and SPA route changes. GDPR consent gate blocks all capture until the user opts in. Events flow Browser → RudderStack → Redpanda → ClickHouse.
- **Phase 3 — Screenshot Capture Service** — Playwright-based service at [services/screenshot/](../services/screenshot/) captures full-page screenshots at 1440px desktop and 390px mobile, cached by URL + viewport hash, refreshable from the dashboard.
- **Phase 4 — Heatmap Computation and Core Dashboard** — Streamlit dashboard at [dashboard/app.py](../dashboard/app.py) renders click, scroll, and hover heatmaps as Plotly overlays on cached screenshots. URL filter with wildcard support, mode switcher. All aggregation happens in ClickHouse (5% grid binning); Python never fetches raw event rows.

### Validated Requirements

All 18 v1.0 requirements shipped and verified: PIPE-01..05, TRACK-01..07, SHOT-01..02, HEAT-01..03, DASH-01..02. Full list in [REQUIREMENTS.md](./REQUIREMENTS.md).

### Dropped

- **Phase 5 — Analytics Features** (DASH-03 live feed, DASH-04 click ranking, DASH-05 page flow Sankey, DASH-06 session stats) was planned but never executed. Dropped at v1.1 pivot because the data collected (where people click/scroll) doesn't inform *lead generation* for e-commerce — you can't identify a lead from a mouse heatmap alone. The *useful* pieces (click ranking, session stats) are rolled into v1.1; Sankey and live feed are abandoned as not serving lead intel.

### Key Decisions

| Date | Decision | Outcome |
|------|----------|---------|
| 2026-04-14 | Redpanda instead of Kafka (simpler, no ZooKeeper) | ✓ Good — zero operational burden |
| 2026-04-14 | 3-table ClickHouse pattern (queue + MV + MergeTree) with `ORDER BY (page_url, event_type, toDate(event_time))` | ✓ Good — heatmap queries are bounded |
| 2026-04-14 | Document-relative `pageX`/`pageY` percentages (not viewport `clientX`) | ✓ Good — coordinates survive scroll |
| 2026-04-14 | Screenshot overlay with Plotly `layout.images` (not canvas injection) | ✓ Good — dashboard is the rendering surface |
| 2026-04-15 | Aggregate heatmaps in ClickHouse (5% grid), never in Python | ✓ Good — 400 cells instead of 50k rows |

---

## v1.1 — E-commerce Events & Lead Dataset

**Status:** Complete
**Shipped:** 2026-04-29 (verified by codebase inspection)
**Phases:** 5–8 (all shipped)

### What Shipped

Full e-commerce event capture and lead data foundation:

- **Phase 5 — E-commerce Event Schema** — Additive ClickHouse schema extension: 8 Nullable e-commerce columns on `analytics.click_events`, two sibling materialized views (`analytics.purchase_items` for per-line-item fan-out via `arrayJoin`, `analytics.orders` ReplacingMergeTree for server-side purchase dedup), zero-storage GA4 alias view (`analytics.click_events_ga4`). Migration idempotent via `make schema-v11`.
- **Phase 6 — E-commerce Tracker API** — 5 new public methods on the JS tracker (`productView`, `addToCart`, `removeFromCart`, `purchase`, `search`). Consent gate inherited from v1.0. Purchase dedup via `localStorage` seen-set on `order_id`. Demo-shop SPA (`src/test-spa-page.html`) exercises all 5 APIs with product cards, cart, checkout, and search bar.
- **Phase 7 — Retailrocket Import** — `scripts/download_retailrocket.sh` (Kaggle API, 4 CSVs, extras cleaned). `infra/clickhouse/sql/003_retailrocket_schema.sql` (3 tables + `item_latest` view, idempotent DDL). `scripts/retailrocket/import.py` (500k-row chunks, `load_batch_id` short-circuit, `insert_deduplication_token` per chunk, distribution validation). `scripts/retailrocket/smoke.sql`. Makefile targets: `retailrocket-download`, `retailrocket-import`, `retailrocket-smoke`, `retailrocket-reload`. Raw CSVs in `.gitignore`. Kaggle license evidence committed.
- **Phase 8 — Rolled-over Dashboard Panels** — Session stats panel (total sessions, avg scroll depth, bounce rate, total events) and click ranking panel (top 10 CSS selectors) added to `dashboard/app.py`. All SQL in `dashboard/heatmap_queries.py` following the v1.0 aggregation-in-ClickHouse rule. Graceful empty states on both panels.

### Validated Requirements

All 18 v1.1 requirements shipped: SCHEMA-01..03, ECOM-01..07, DATA-01..06, STATS-01..02.

### Key Decisions

| Date | Decision | Outcome |
|------|----------|---------|
| 2026-04-18 | Additive schema extension (`ALTER TABLE ADD COLUMN IF NOT EXISTS`, never rebuild) | ✓ v1.0 data preserved; migration idempotent |
| 2026-04-18 | Sibling MVs instead of projections for purchase fan-out and dedup | ✓ Correct — projections cannot ARRAY JOIN or change engine (ClickHouse #98953, #24778) |
| 2026-04-18 | Retailrocket in separate `retailrocket_raw.*` database, not merged into `click_events` | ✓ Correct — sort-key selectivity preserved; CC BY-NC-SA data isolated |
| 2026-04-18 | Two-layer idempotency: `load_batch_id` short-circuit + `insert_deduplication_token` per chunk | ✓ No Python-side row dedup; standard ClickHouse idiom |
| 2026-04-18 | `cart_id` tracker-maintained in `localStorage`, rotated after purchase | ✓ Cart state lives client-side where it belongs |

---

*Last updated: 2026-04-29 — v1.1 archived as complete.*
