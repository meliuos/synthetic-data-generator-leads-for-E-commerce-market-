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

**Status:** Starting
**Goal:** Capture lead-informative e-commerce events in the tracker (product_view, add_to_cart, remove_from_cart, purchase, search) and seed ClickHouse with the open-source Retailrocket dataset so downstream lead-generation work has both organic data and a bootstrap corpus. Roll in Phase 5's still-useful panels (session stats, click ranking); drop the rest.

Details live in [PROJECT.md](./PROJECT.md) and [ROADMAP.md](./ROADMAP.md).

---

*Last updated: 2026-04-18 — v1.0 archived, v1.1 started.*
