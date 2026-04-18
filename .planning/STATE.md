# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-18)

**Core value:** Capture user behavior signals that identify purchase-intent leads for an e-commerce site — heatmap engagement plus e-commerce intent events — backed by a scalable real-time event pipeline.
**Current focus:** Milestone v1.1 — E-commerce Events & Lead Dataset. Roadmap locked; Phase 5 next.

## Current Position

Milestone: v1.1 — E-commerce Events & Lead Dataset
Phase: Phase 5 COMPLETE (3/3 plans shipped)
Plan: 05-02 complete (all 3 plans in Phase 5 done)
Status: 05-01, 05-02, and 05-03 all committed
Last activity: 2026-04-19 — Completed 05-02-PLAN.md (v1.1 e-commerce schema smoke test)

Progress: v1.0 complete (13/13 plans shipped); v1.1 in progress (Phase 5 done — Phases 6, 7, 8 next).

███████████████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░ (Phase 5: 3/3 plans complete)

## v1.1 Phase Status Snapshot

| Phase | Name | Requirements | Status | Next action |
|-------|------|--------------|--------|-------------|
| 5 | E-commerce Event Schema | SCHEMA-01, SCHEMA-02, SCHEMA-03 | COMPLETE (all 3 plans shipped) | — |
| 6 | E-commerce Tracker API | ECOM-01..07 | Not started (blocked on Phase 5) | — |
| 7 | Retailrocket Import | DATA-01..06 | Not started (blocked on Phase 5; can run parallel with 6) | — |
| 8 | Rolled-over Dashboard Panels | STATS-01, STATS-02 | Not started (blocked on Phase 5; can run parallel with 6/7) | — |

**Parallelism:** Once Phase 5 ships, Phases 6, 7, and 8 can execute in parallel. Phase 8 touches only v1.0 heatmap columns so it has no logical dependency on 6 or 7.

## Accumulated Decisions

Decisions from v1.0 — still load-bearing for v1.1:

| Date | Plan | Decision | Why it matters |
| --- | --- | --- | --- |
| 2026-04-15 | 04-01 | Centralize heatmap SQL in `dashboard/heatmap_queries.py` | v1.1 session stats + click ranking queries belong in this same module (Phase 8) |
| 2026-04-15 | 04-01 | Support URL matching as exact value or wildcard (`*` -> `LIKE`) | v1.1 e-commerce event queries reuse this URL scoping helper |
| 2026-04-15 | 04-01 | Expose only binned/aggregated dataframes from query helpers | v1.1 panels (Phase 8) must follow the same rule — never fetch raw rows into Streamlit |
| 2026-04-16 | 04-02 | Layer Plotly heatmaps over cached screenshots with `layout.images` | Pattern applies to any future overlay panel |
| 2026-04-16 | 04-03 | Normalize URL scope once and reuse it for every mode | v1.1 dashboard filters should consume the same normalized scope |
| 2026-04-16 | 04-04 | Render scroll as full-width bands, dispatch views by mode | Mode-dispatch pattern extends cleanly to new v1.1 panels |

Decisions locked during v1.1 roadmap creation:

| Date | Phase | Decision | Why it matters |
| --- | --- | --- | --- |
| 2026-04-18 | 5 | Schema extension is additive `ALTER TABLE ADD COLUMN` (never rebuild) | Preserves v1.0 data; v1.0 events still insert with new columns read as NULL |
| 2026-04-18 | 5 | Purchase dedup is defence-in-depth: tracker `localStorage` seen-set + `ReplacingMergeTree(event_time)` projection on `order_id` | Network retries and back-button reloads both handled |
| 2026-04-18 | 5 | Tracker emits RudderStack/Segment V2 shape; materialized view exposes GA4 aliases | Single tracker-side shape, one translation layer in ClickHouse |

Decisions locked during Phase 5 plan 3 execution:

| Date | Plan | Decision | Why it matters |
| --- | --- | --- | --- |
| 2026-04-18 | 05-03 | Per-milestone schema docs at `docs/schema-v<MAJOR>.<MINOR>.md`, always linked from README Notes section | Future milestones (v1.2+) follow same convention — discoverability guaranteed from repo root |
| 2026-04-18 | 05-03 | Substitution-rationale paragraphs (roadmap vs. implementation) are permanent inline doc in the schema file | Future contributors understand intentional deviations without re-deriving research |

Decisions locked during Phase 5 plan 2 execution:

| Date | Plan | Decision | Why it matters |
| --- | --- | --- | --- |
| 2026-04-19 | 05-02 | Each milestone gets its own smoke-test-vX.Y.sh + Makefile target (prior-version targets never modified) | Multi-version non-regression coverage; running all smoke targets sequentially proves additive schema changes don't break prior contracts |
| 2026-04-19 | 05-02 | Purchase events carry both 'event_time' (for events_mv→click_events) AND 'timestamp' (for purchase_items_mv/orders_mv) | Secondary MVs parse event_time from 'timestamp' (RudderStack V2 field); tracker must emit both fields on purchase events |
| 2026-04-19 | 05-02 | add_to_cart events should include 'category' in their properties block | Enables SCHEMA-01 c_category coverage assertion; semantically correct per e-commerce event taxonomy |

Decisions locked during Phase 5 plan 1 execution:

| Date | Plan | Decision | Why it matters |
| --- | --- | --- | --- |
| 2026-04-18 | 05-01 | `ALTER TABLE mv_name MODIFY QUERY` used instead of `CREATE OR REPLACE MATERIALIZED VIEW` (not supported in ClickHouse 24.8) | Future schema plans must use MODIFY QUERY for MV updates on ClickHouse 24.8 |
| 2026-04-18 | 05-01 | Secondary MVs (purchase_items_mv, orders_mv) as sibling tables — not projections | Projections cannot use ARRAY JOIN or different engines (confirmed in prod); this pattern is now standard for derived views in this project |
| 2026-04-18 | 05-01 | Migration files numbered sequentially (001_, 002_) — each additive, never modifying prior | Prevents accidental v1.0 breakage; each version's SQL is isolated |
| 2026-04-18 | 6 | `cart_id` is tracker-maintained in `localStorage` per cart session, rotated after `purchase` (not server-synthesized) | Keeps correlation logic client-side where cart state lives |
| 2026-04-18 | 6 | Single `purchase` event per order with `products[]` array (not one event per line item) | Matches Segment V2 / GA4 / RudderStack; makes `order_id` the single dedup key |
| 2026-04-18 | 7 | Retailrocket lands in parallel `retailrocket_raw.*` tables, NOT merged into `click_events` | Keeps live tracker sort-key selectivity intact; isolates CC BY-NC-SA data |
| 2026-04-18 | 7 | Idempotency = `load_batch_id` short-circuit + ClickHouse `insert_deduplication_token` per chunk (no Python-side dedup) | Standard ClickHouse idiom; no custom dedup state to maintain |
| 2026-04-18 | 7 | Raw Retailrocket CSVs NOT committed to git; `download.sh` uses Kaggle API + user-local `~/.kaggle/kaggle.json` | License hygiene (CC BY-NC-SA); repo stays small |

## Blockers / Concerns

- No v1.0 blockers.
- Environment note: host Python is externally managed (PEP 668); dependency verification must continue via isolated venvs (v1.0 used `.venv-phase4`).
- Phase 7 pre-flight requires a manual Kaggle license screenshot (committed under `.planning/research/v1.1/evidence/kaggle-license.png`) — first task of Phase 7, not a roadmap blocker.
- Phase 5 open question resolved at roadmap time: `cart_id` is tracker-maintained (per EVENTS.md recommendation).

## Milestone History

See [.planning/MILESTONES.md](./MILESTONES.md) for shipped milestones.

- **v1.0** — Heatmap Core (Complete, 2026-04-16) — Phases 1–4 shipped; Phase 5 dropped, useful parts rolled into v1.1.
- **v1.1** — E-commerce Events & Lead Dataset (Starting, 2026-04-18) — Roadmap locked (Phases 5-8), planning underway.

## Session Continuity

Last session: 2026-04-19T01:11:00Z
Stopped at: Completed 05-02-PLAN.md (v1.1 e-commerce schema smoke test) — Phase 5 now fully complete
Resume file: None — next action is execute Phase 6 (E-commerce Tracker API), Phase 7 (Retailrocket Import), and Phase 8 (Dashboard Panels) in parallel
