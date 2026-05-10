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

## v1.2 — Lead Scoring & Identification

**Status:** Complete
**Shipped:** 2026-04-29
**Phases:** 9–12 (all shipped)

### What Shipped

Full behavioral lead scoring pipeline:

- **Phase 9 — Lead Scoring Data Foundation** — `analytics.unified_events` UNION ALL view across live and Retailrocket sources. `analytics.session_features` per-session behavioral feature table (`page_views`, `product_views`, `add_to_cart_count`, `purchase_count`, `search_count`, `max_scroll_pct`, `session_duration_seconds`, `distinct_products_viewed`, `cart_abandoned`). Smoke query verifies feature coverage for both sources.
- **Phase 10 — Rule-Based Lead Scoring Engine** — `src/scoring/rules.py` table-driven scoring rubric (+30 add_to_cart, +20 purchase, +15 ≥3 product views, +10 search, +10 high scroll, -10 bounce). `analytics.lead_scores_rule_based` ClickHouse view. 40+ unit tests.
- **Phase 11 — ML Lead Scoring Model** — LightGBM binary classifier trained on Retailrocket `session_features`. 5-fold stratified CV, `scale_pos_weight` for 0.82% class imbalance. `MLScorer` wrapper. `scripts/score_sessions.py` batch CLI. `analytics.lead_scores_ml` ReplacingMergeTree table. Model card in `docs/`.
- **Phase 12 — Lead Identification Dashboard** — Streamlit multi-page "Leads" page (`dashboard/pages/leads.py`). Ranked table with rule + ML scores, tier/source filters, `rules_fired` breakdown column, ML-absent warning banner, CSV export. `fetch_lead_candidates()` LEFT JOINs `lead_scores_ml FINAL` so ML absence never blocks the view.

### Validated Requirements

All v1.2 requirements shipped: LEAD-01 (session features), LEAD-02 (lead dashboard), ML-01..04 (model training and serving).

### Key Decisions

| Date | Decision | Outcome |
|------|----------|---------|
| 2026-04-25 | UNION ALL view for unified events (not merged table) | Read-time join; source isolation preserved |
| 2026-04-28 | Rule weights as a config dict in `rules.py`, not hardcoded | Tunable without code change |
| 2026-04-29 | LEFT JOIN on `lead_scores_ml FINAL` — page works before ML training runs | Operational resilience; rule scores alone are usable |
| 2026-04-29 | `ifNull(ml_lead_score, rule_score/100)` sort order | Consistent ranking whether ML scores exist or not |

---

## v2.0 — Synthetic Data Generation (Planned)

**Status:** Pending
**Target:** TBD
**Phases:** 13–14

### Planned Scope

- **Phase 13 — CTGAN Behavioral Simulator** — Train a Conditional Tabular GAN on `analytics.session_features` to generate synthetic sessions with realistic behavioral distributions. Exports `models/ctgan_sessions.pkl`. CLI: `make generate-synthetic`.
- **Phase 14 — Simulation Engine (Mesa)** — Agent-based e-commerce simulator pushing synthetic event streams directly into the Redpanda pipeline. Three agent types: BrowserAgent, BuyerAgent, AbandonerAgent. CLI: `make simulate`.

### Entry Point

Phase 13. See NEXT-PHASES.md and ROADMAP.md for full detail.

---

## v2.1 — AI Commercial Assistant (Planned)

**Status:** Pending
**Target:** After v2.0
**Phases:** 15–16

### Planned Scope

- **Phase 15 — Lead Profiling & LLM Context Builder** — Context-assembly layer translating lead behavioral signals into a structured prompt for Claude (`claude-sonnet-4-6`). Prompt caching on system prompt per tier. Logs to `analytics.ai_script_log`.
- **Phase 16 — AI Script Generation Panel** — "Generate Script" button per lead row in the Streamlit Leads page. Spinner + `st.text_area` output. Token usage and cost display. Script history panel.

### Entry Point

Phase 15, after Phase 12 (lead identification) is confirmed stable and Phase 13 (CTGAN) is underway or complete.

---

## v2.2 — Product Intelligence Interface (Planned)

**Status:** Pending
**Target:** After v2.0 Phase 13
**Phases:** 17

### Planned Scope

- **Phase 17 — Product Input & Lead Prediction Interface** — Operator-facing Streamlit page where an e-commerce manager enters a product (name, category, price, keywords) and receives ML-backed lead predictions: conversion rate estimate, tier distribution, top behavioral signals, and a table of lookalike synthetic sessions. Powered by CTGAN sampling + Phase 11 ML scorer. Every prediction logged to `analytics.prediction_log`.

### Entry Point

Phase 17. Requires Phase 13 (CTGAN model) and Phase 11 (ML scorer) to be complete. Can start in parallel with Phase 14.

---

---

## v2.3 — ML Pipeline Hardening (Planned)

**Status:** Pending
**Target:** After v2.2 Phase 17
**Phases:** 18–19

### Planned Scope

- **Phase 18 — Augmented Training Pipeline** — Retrain the LightGBM scorer on real + synthetic combined corpus (Phase 13 output). Introduce model versioning (`models/ACTIVE_MODEL` file, `model_registry.py`). Export `models/lead_scorer_lgbm_v2.pkl`. Compare v1 vs v2 AUC/Recall@K, commit model card to `docs/model_card_v2.md`.
- **Phase 19 — Prediction REST API Service** — FastAPI service (`src/api/main.py`) in Docker Compose exposing `POST /predict/product`, `GET /health`, `GET /predictions/history`. The Streamlit predict page (Phase 17) calls the API instead of importing the predictor directly. Prediction history expander added to the predict page.

### Entry Point

Phase 18, after Phase 17 (product_predictor.py tested) and Phase 13 (synthetic_sessions populated).

### Why This Milestone Exists

Phase 13 generates synthetic sessions to address class imbalance in the ML scorer, but without Phase 18 that synthetic data is never used to improve the model — the training loop is incomplete. Phase 19 extracts the prediction logic into a proper service so the Streamlit dashboard does not block on CTGAN sampling and so the prediction capability is accessible programmatically.

---

## v2.4 — Production Monitoring & CI (Planned)

**Status:** Pending
**Target:** After v2.3
**Phases:** 20

### Planned Scope

- **Phase 20 — ML Monitoring & CI Hardening** — `src/monitoring/drift_detector.py` with Jensen-Shannon divergence per feature between real and synthetic distributions. `analytics.drift_log` ClickHouse table. Model Health panel in Streamlit admin sidebar. Redpanda Console container for consumer-lag observability. ClickHouse slow-query panel in sidebar. GitHub Actions CI pipeline (lint + unit-tests + docker-build).

### Entry Point

Phase 20, after the full Docker Compose stack (including Phase 19 `prediction-api`) is stable.

### Why This Milestone Exists

After v2.3, the system is functionally complete but operationally blind: no visibility into model drift, pipeline failures, or code regressions. This milestone closes those gaps with minimal effort (Redpanda Console is a zero-code Docker service addition; GitHub Actions adds automated test execution) and makes the system handoff-ready.

---

*Last updated: 2026-05-08 — v2.3 (ML Pipeline Hardening) and v2.4 (Production Monitoring & CI) milestones added.*
