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

## v2.0 — Synthetic Data Generation

**Status:** Complete
**Shipped:** 2026-05-10
**Phases:** 13–14

### What Shipped

- **Phase 13 — CTGAN Behavioral Simulator** — `CTGANSynthesizer` (SDV) trained on `analytics.session_features` with top-50 category cardinality cap to avoid OHE memory error. Exports `models/ctgan_sessions.pkl`. `analytics.synthetic_sessions` ClickHouse table (mirrors session_features schema + `is_synthetic` discriminator). CLI: `make ctgan-train` + `make generate-synthetic`.
- **Phase 14 — Simulation Engine (Mesa)** — Mesa 3.x agent-based simulator with `BrowserAgent`, `BuyerAgent`, `AbandonerAgent`. Kafka/Redpanda event emission bridge. `scripts/run_simulation.py` CLI. Makefile targets: `make sim-setup`, `make simulate`, `make smoke-test-sim`.

### Key Decisions

| Date | Decision | Outcome |
|------|----------|---------|
| 2026-05-10 | Top-50 category cardinality cap in CTGAN training | Avoids 13 GiB OHE memory error with 1,079 distinct categories |
| 2026-05-10 | Mesa 3.x API (`Agent(model)`, `self.agents.shuffle_do("step")`) | Mesa 3.x removed `RandomActivation`; new API required |
| 2026-05-10 | Single 100-epoch training run on 200K stratified sample | Avoids timeout from checkpoint-loop re-training from scratch |

---

## v2.1 — AI Commercial Assistant

**Status:** Complete
**Shipped:** 2026-05-10
**Phases:** 15–16

### What Shipped

- **Phase 15 — Lead Profiling & LLM Context Builder** — `src/ai/lead_profiler.py` (ClickHouse context assembly), `src/ai/prompt_builder.py` (Jinja2 per-tier templates), `src/ai/llm_client.py` (Ollama HTTP API, `qwen2.5:7b`, fully local — replaced Anthropic/Claude). Logs to `analytics.ai_script_log` with `cost_usd=0`. 11 unit tests passing.
- **Phase 16 — AI Script Generation Panel** — Per-lead "Generate Script" button in `dashboard/pages/leads.py`. Tier emoji (🔥/🌡️/❄️). `st.session_state` caching per lead. Sentinel-string routing for missing-lead / timeout errors. Script history `st.dataframe`.

### Key Decisions

| Date | Decision | Outcome |
|------|----------|---------|
| 2026-05-10 | Replaced Anthropic/Claude with Ollama + Qwen2.5:7b (local inference) | Zero API cost; no rate limits; `OLLAMA_HOST` env var configurable |
| 2026-05-10 | `build_script()` in `src/ai/__init__.py` never raises — returns sentinel strings | Dashboard layer does not need try/except; sentinel routing in UI |

---

## v2.2 — Product Intelligence Interface

**Status:** Complete
**Shipped:** 2026-05-10
**Phases:** 17

### What Shipped

- **Phase 17 — Product Input & Lead Prediction Interface** — `src/prediction/product_predictor.py` with `predict_for_product()`, `PredictionResult` dataclass, lazy-cached CTGAN synthesizer and MLScorer, conditional CTGAN sampling with unconditional fallback, heuristic fallback scorer. `dashboard/pages/predict.py` Streamlit page with form, metrics row, Plotly pie/bar charts, top-10 sessions table, prediction history. `analytics.prediction_log` ClickHouse table. `scripts/predict_product.py` CLI. 26 unit tests passing.

### Key Decisions

| Date | Decision | Outcome |
|------|----------|---------|
| 2026-05-10 | `lru_cache` on synthesizer and MLScorer loaders | Avoids repeated 6 MB pkl deserialization on multi-call workflows |
| 2026-05-10 | Heuristic fallback score when LightGBM model absent | Prediction page works even before `make score-sessions` runs |
| 2026-05-10 | `category_tree` has no name column — selectbox shows IDs directly | Avoids broken join; IDs match CTGAN training column |

---

## v2.3 — ML Pipeline Hardening

**Status:** Complete
**Shipped:** 2026-05-10
**Phases:** 18–19

### What Shipped

- **Phase 18 — Augmented Training Pipeline** — `scripts/build_augmented_dataset.py` exports real Retailrocket + CTGAN synthetic sessions, aligns `_FEATURE_COLS`, labels `converted`, stratified 80/20 split to `data/augmented_{training,test}.parquet`. `notebooks/augmented_training.ipynb` 7-cell notebook: load → v1 baseline recall → LightGBM v2 5-fold CV → v1 vs v2 comparison (5pp Recall@K target) → feature importance delta chart → save `models/lead_scorer_lgbm_v2.pkl` → model card export to `docs/model_card_v2.md`. `src/scoring/model_registry.py` with `get_active_version()`, `get_active_model_path()`, `set_active_model()`. `MLScorer` updated to use registry as default (backwards-compatible). `models/ACTIVE_MODEL` committed (initial: `v1`). 20 unit tests passing.
- **Phase 19 — Prediction REST API Service** — FastAPI service (`src/api/main.py`) with lifespan model loading, `POST /predict/product`, `GET /health`, `GET /predictions/history`, `GET /models/active`. Pydantic v2 request/response schemas with field validators. `Dockerfile.api` + `prediction-api` Docker Compose service (port 8000, `./models:/app/models:ro` volume, `start_period: 60s` healthcheck). `dashboard/pages/predict.py` rewritten to call API via `PREDICTION_API_URL` env var — no direct CTGAN/LightGBM imports in dashboard. 26 unit tests with TestClient + mocked lifespan dependencies.

### Key Decisions

| Date | Decision | Outcome |
|------|----------|---------|
| 2026-05-10 | `models/ACTIVE_MODEL` is plain-text committed to git | Config, not artifact — safe to commit; `models/*.pkl` remain gitignored |
| 2026-05-10 | `MLScorer(model_version="v2")` kwarg resolves via registry; explicit `model_path=` still works | Zero breakage to existing callers |
| 2026-05-10 | Synthetic table fetch in dataset builder is non-fatal | `make build-augmented-dataset` works before `make generate-synthetic` runs |
| 2026-05-10 | FastAPI lifespan patched as no-op in tests; prediction patched at source module | Avoids SDV/CTGAN import in CI; test isolation clean |
| 2026-05-10 | Dashboard predict page calls API over HTTP; no ML imports in Streamlit process | Streamlit event loop stays unblocked; inference isolated to API container |

---

## v2.4 — Production Monitoring & CI

**Status:** Complete
**Shipped:** 2026-05-10
**Phases:** 20

### What Shipped

- **Phase 20 — ML Monitoring & CI Hardening** — `src/monitoring/drift_detector.py` with `compute_feature_jsd()` (scipy JSD, 50-bin histogram with Laplace smoothing) and `check_drift()` returning `DriftReport` (ok/warn/fail bands at 0.10/0.15). `scripts/check_model_drift.py` CLI exits 1 on fail. `analytics.drift_log` ClickHouse table (`infra/clickhouse/sql/010_drift_log.sql`). `dashboard/drift_panel.py` self-contained module with `render_model_health_sidebar()` (status badge, JSD bar chart) and `render_slow_query_sidebar()` (system.query_log top 10 > 500 ms). Both panels wired into `dashboard/app.py` sidebar. `redpanda-console` service in Docker Compose (port 9080, zero-code Kafka consumer lag UI). `.github/workflows/ci.yml` with three jobs: `lint` (ruff), `unit-tests` (pytest), `docker-build`. `requirements.txt` (root, for CI), `requirements-dev.txt` (ruff, pytest, scipy). `make` targets: `schema-phase20`, `check-drift`, `console-up`, `lint`.

### Key Decisions

| Date | Decision | Outcome |
|------|----------|---------|
| 2026-05-10 | `dashboard/drift_panel.py` self-contained (no `src/` import) | Dashboard Docker image build context is `./dashboard` — can't reference `src/` without changing context |
| 2026-05-10 | Redpanda Console on port 9080 (not 8080) | 8080 already bound to RudderStack; 9080 avoids conflict |
| 2026-05-10 | Root `requirements.txt` covers test deps; heavy ML in `requirements-ml.txt` | SDV/CTGAN mocked in tests — not installed in CI; avoids 10-min install on every push |
| 2026-05-10 | JSD via `jensenshannon(p, q)**2` with Laplace-smoothed shared histogram | scipy returns JS distance, not JSD; squaring recovers JSD ∈ [0,1]; smoothing avoids log(0) |

---

*Last updated: 2026-05-10 — v2.4 complete. All phases (1–20) shipped.*
