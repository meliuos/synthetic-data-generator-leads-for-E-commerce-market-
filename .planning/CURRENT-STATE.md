# Current State Analysis — Lead Intelligence Platform

**Date:** 2026-04-29
**Analyst:** Senior review against `.planning/` and `docs/` corpus
**Based on:** PROJECT.md, ROADMAP.md, STATE.md, MILESTONES.md, REQUIREMENTS.md, docs/schema-v1.1.md

---

## What Has Been Shipped

### v1.0 — Heatmap Core (Complete, 2026-04-16)

All 4 active phases shipped, Phase 5 (analytics) intentionally dropped and useful parts
rolled into v1.1.

| Phase | Deliverable | Status |
|-------|------------|--------|
| 1 | Redpanda + ClickHouse + RudderStack stack in Docker Compose | ✓ Complete |
| 2 | Vanilla JS tracker — clicks, scroll, hover, SPA, GDPR consent gate | ✓ Complete |
| 3 | Playwright screenshot service (1440px / 390px, hash-cached) | ✓ Complete |
| 4 | Streamlit dashboard — click/scroll/hover heatmap overlays, URL filter, wildcard | ✓ Complete |

**v1.0 requirement coverage:** 19 requirements shipped, 4 dropped (2 rolled into v1.1).

---

### v1.1 — E-commerce Events & Lead Dataset (In Progress)

5 of 6 plans complete. One phase (7) not yet started.

| Phase | Name | Plans | Status |
|-------|------|-------|--------|
| 5 | E-commerce Event Schema | 3/3 | ✓ Complete (2026-04-19) |
| 6 | E-commerce Tracker API | 1/1 | ✓ Complete (2026-04-19) |
| 7 | Retailrocket Import | 3/3 | ✓ Complete (verified 2026-04-29) |
| 8 | Rolled-over Dashboard Panels | 1/1 | ✓ Complete (2026-04-19) |

**v1.1 requirement coverage:** 18/18 requirements complete. v1.1 is FULLY SHIPPED.

#### Phase 5 — Schema highlights
- 8 additive `Nullable` columns on `analytics.click_events` (product_id, category, price,
  quantity, order_id, cart_value, search_query, results_count)
- Two sibling materialized views: `analytics.purchase_items` (per-line-item ARRAY JOIN) and
  `analytics.orders` (ReplacingMergeTree, purchase dedup)
- Zero-storage GA4 alias view `analytics.click_events_ga4`
- Migration is idempotent (`ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`)

#### Phase 6 — Tracker highlights
- 5 new public methods: `productView`, `addToCart`, `removeFromCart`, `purchase`, `search`
- Consent gate inherited from v1.0 (no opt-in = no emission)
- Purchase dedup: `localStorage` seen-set on `order_id` (client-side layer)
- Demo-shop SPA exercises all 5 APIs without DevTools

#### Phase 8 — Dashboard highlights
- Session stats panel: total sessions, avg scroll depth, bounce rate, total events
- Click ranking panel: top 10 CSS selectors by click count
- Both aggregated in ClickHouse; Python receives only aggregate dataframes

---

## v1.1 Is Fully Shipped

All 18 v1.1 requirements verified complete as of 2026-04-29. Phase 7 was confirmed by
direct codebase inspection (not just planning docs). Key Phase 7 deliverables verified:

| Deliverable | File | Status |
|-------------|------|--------|
| Download script | `scripts/download_retailrocket.sh` | ✓ Present, complete |
| ClickHouse schema | `infra/clickhouse/sql/003_retailrocket_schema.sql` | ✓ 3 tables + item_latest view |
| Import script | `scripts/retailrocket/import.py` | ✓ 500k-row chunks, load_batch_id, dedup_token, validation |
| Smoke query | `scripts/retailrocket/smoke.sql` | ✓ Row counts + distribution + category join |
| Makefile targets | `Makefile` | ✓ retailrocket-download/import/smoke/reload |
| .gitignore | `.gitignore` | ✓ data/retailrocket/* with README.md exception |
| Kaggle license evidence | `.planning/research/v1.1/evidence/kaggle-license.png` | ✓ Present |

---

## Not Yet Started (Future Milestones)

Per the CdC and REQUIREMENTS.md future-scope section:

| Milestone | Key Capability | Depends On |
|-----------|---------------|------------|
| v1.2 | Rule-based + ML lead scoring; lead identification dashboard | Phase 7 complete (corpus) |
| v2.0 | CTGAN synthetic data generation; behavioral simulation (Mesa/SimPy) | v1.2 feature vocabulary |
| v2.1 | LLM AI commercial assistant; sales script generation | v1.2 lead scores |

---

## Summary Assessment

The platform is **fully operational through v1.1**. The tracker pipeline works end-to-end,
the schema is extended correctly without data loss, the Retailrocket corpus is imported and
queryable, and the dashboard surfaces both heatmap and session-level analytics. The project
is ready to pivot to v1.2 lead scoring — which is where the CdC's commercial value lives.

**Next action:** Begin v1.2 Phase 9 (Lead Scoring Data Foundation). See NEXT-PHASES.md.

---
*Written: 2026-04-29*
