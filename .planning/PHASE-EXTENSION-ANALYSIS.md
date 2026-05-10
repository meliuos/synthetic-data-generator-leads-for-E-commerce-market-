# Phase Extension Analysis — Lead Intelligence Platform
**Date:** 2026-05-08
**Scope:** Gap analysis from current state (v1.2 complete, v2.0 pending) through a
production-ready end-to-end prediction system

---

## 1. Missing Phases Analysis

### What the existing roadmap covers (Phases 13–17)

| Phase | Milestone | What it does |
|-------|-----------|-------------|
| 13 | v2.0 | Trains CTGAN on session_features, generates synthetic rows into `analytics.synthetic_sessions` |
| 14 | v2.0 | Mesa agent-based simulator pushes event streams into Redpanda |
| 15 | v2.1 | LLM context builder for lead profiling + Claude API integration |
| 16 | v2.1 | AI script generation panel in Streamlit |
| 17 | v2.2 | Streamlit product form + CTGAN sampling + ML scoring + prediction display |

### What is genuinely missing

**Gap 1 — The training loop is broken after Phase 13**

Phase 13 generates synthetic sessions to address Retailrocket's 0.82% class imbalance.
But Phase 11's LightGBM model is never retrained with this data. The synthetic corpus
is produced, inserted into ClickHouse, and then... nothing uses it for model improvement.
The loop is: generate synthetic → augment training data → retrain model → improve predictions.
Phases 13 and 17 exist; the middle step (retrain) does not.

**Gap 2 — No model versioning**

The Phase 11 `MLScorer` hardcodes `models/lead_scorer_lgbm.pkl`. If a new model is
trained (in Phase 18 or later), there is no mechanism to switch the active model without
editing code. No version registry. No rollback path.

**Gap 3 — No prediction service layer**

Phase 17 calls `product_predictor.predict_for_product()` as a direct Python import inside
Streamlit. Two consequences:
- CTGAN sampling (1,000 sessions) blocks Streamlit's event loop for several seconds,
  freezing the UI with no feedback to the user.
- The prediction capability is embedded in the dashboard process — it cannot be called
  from external scripts, CI pipelines, or a future API consumer.

**Gap 4 — No monitoring or observability**

After Phase 17 ships, the system operates blind:
- No way to detect if CTGAN distributions are drifting from real data over time
- No Redpanda consumer-lag visibility (ISSUE-04 flagged in ARCHITECTURE-REVIEW.md but
  never scheduled)
- No ClickHouse query performance tracking
- Silent model degradation goes undetected

**Gap 5 — No CI/CD**

The Makefile is the current "CI". There is no automated test runner on pull requests.
A code change that breaks `tests/` or fails `ruff` can be merged without anyone noticing.

---

## 2. Updated Full Roadmap

### Complete phase list

| Phase | Milestone | Name | Depends On | Status |
|-------|-----------|------|-----------|--------|
| 1–4 | v1.0 | Heatmap Core | — | Complete 2026-04-16 |
| 5–8 | v1.1 | E-commerce Events & Lead Dataset | — | Complete 2026-04-29 |
| 9–12 | v1.2 | Lead Scoring & Identification | — | Complete 2026-04-29 |
| 13 | v2.0 | CTGAN Behavioral Simulator | 9, 11 | **Pending — entry point** |
| 14 | v2.0 | Simulation Engine (Mesa) | 13 | Pending |
| 15 | v2.1 | Lead Profiling & LLM Context Builder | 12 | Pending |
| 16 | v2.1 | AI Script Generation Panel | 15 | Pending |
| 17 | v2.2 | Product Input & Lead Prediction Interface | 13, 11 | Pending |
| 18 | v2.3 | Augmented Training Pipeline | 13, 11 | Pending |
| 19 | v2.3 | Prediction REST API Service | 17, 18 | Pending |
| 20 | v2.4 | ML Monitoring & CI Hardening | 19 | Pending |

### Full execution order with parallelism

```
v1.2 COMPLETE
  ↓
Phase 13 (CTGAN)
  ├── Phase 14 (Simulation)          ← v2.0 — can run in parallel with 17, 18
  ├── Phase 17 (Product Prediction)  ← v2.2 — needs CTGAN model only
  └── Phase 18 (Augmented Training)  ← v2.3 — needs synthetic_sessions; parallel with 17

Phase 12 → Phase 15 → Phase 16      ← v2.1 — fully independent of 17–20

Phase 17 + Phase 18 both complete
  ↓
Phase 19 (Prediction API)
  ↓
Phase 20 (Monitoring & CI)
  ↓
  SYSTEM PRODUCTION-READY
```

---

## 3. Phase Summaries

### Phase 13 — CTGAN Behavioral Simulator (v2.0, already planned)

**Objectives:**
- Train a Conditional Tabular GAN on `analytics.session_features` (real Retailrocket + live data)
- Generate synthetic sessions conditioned on `category` for Phase 17 product predictions
- Validate generation quality: Jensen-Shannon divergence < 0.1 per continuous feature

**Technical tasks (from PLANS.md — already complete):**
- `analytics.synthetic_sessions` ClickHouse schema (mirrors session_features + `is_synthetic` flag)
- `notebooks/ctgan_trainer.ipynb`: 300 epochs, column metadata, JS divergence evaluation
- `scripts/generate_synthetic_sessions.py`: CLI, MLScorer tagging, ClickHouse insert

**Dependencies:** Phase 9 (session_features), Phase 11 (MLScorer for quality tagging)

**Deliverables:** `models/ctgan_sessions.pkl`, `analytics.synthetic_sessions`, `docs/ctgan_evaluation.md`

---

### Phase 14 — Simulation Engine (v2.0, already planned)

**Objectives:**
- Generate realistic event streams (not just session aggregates) via Mesa agents
- Enable "what-if" scenario testing: what does traffic look like with N BuyerAgents?

**Technical tasks:**
- `src/simulation/agents.py`: BrowserAgent, BuyerAgent, AbandonerAgent
- `src/simulation/ecommerce_env.py`: Mesa Model, time-stepped environment
- Events pushed to Redpanda via RudderStack SDK path (transparent to downstream tables)
- Simulated sessions use `sim_` prefix on session_id/user_id for filtering

**Dependencies:** Phase 13 (CTGAN behavioral priors)

**Deliverables:** `scripts/run_simulation.py`, `make simulate` target, smoke test

---

### Phase 15 — Lead Profiling & LLM Context Builder (v2.1, already planned)

**Objectives:**
- Translate a lead's behavioral signals into a structured Claude API prompt
- Generate personalized sales scripts, one per score tier (hot/warm/cold)
- Log all LLM calls with token counts + cost to `analytics.ai_script_log`

**Technical tasks:**
- `src/ai/lead_profiler.py`: query lead signals from ClickHouse, build JSON context
- `src/ai/prompt_builder.py`: per-tier templates with `cache_control: ephemeral` on system prompt
- `src/ai/llm_client.py`: Claude Sonnet 4.6 via Anthropic SDK, prompt caching

**Dependencies:** Phase 12 (lead scores in ClickHouse)

**Deliverables:** `build_script(anonymous_user_id)` function, `analytics.ai_script_log` table

---

### Phase 16 — AI Script Generation Panel (v2.1, already planned)

**Objectives:**
- "Generate Script" button on each lead row in the Streamlit Leads page
- Display generated script, token usage, cost, and script history

**Technical tasks:**
- Button → `build_script()` call inside `st.spinner`
- `st.text_area` output + copy-to-clipboard
- Script history panel from `analytics.ai_script_log`

**Dependencies:** Phase 15

**Deliverables:** Updated `dashboard/pages/leads.py`

---

### Phase 17 — Product Input & Lead Prediction Interface (v2.2, already planned)

**Objectives:**
- Streamlit form: product name, category (from category_tree), price, keywords
- CTGAN conditional sampling on category → ML scoring → prediction results
- Log every prediction to `analytics.prediction_log`

**Technical tasks:**
- `src/prediction/product_predictor.py`: `predict_for_product()` function
- `dashboard/pages/predict.py`: form + spinner + conversion gauge + tier pie + feature bar chart
- `infra/clickhouse/sql/007_prediction_log.sql`: `analytics.prediction_log` MergeTree

**Dependencies:** Phase 13 (CTGAN model), Phase 11 (MLScorer)

**Deliverables:** Streamlit predict page, `predict_for_product()` backend, prediction log table

> **Note on SQL file numbering:** Phase 17 PLANS.md references `004_prediction_log.sql`
> which conflicts with Phase 9's `004_phase9_foundation.sql`. The correct number is `007`
> (continuing from Phase 11's `006_ml_scores.sql`). Implementers should use
> `infra/clickhouse/sql/007_prediction_log.sql`.

---

### Phase 18 — Augmented Training Pipeline (v2.3, **NEW**)

**Objectives:**
- Retrain LightGBM scorer on real Retailrocket sessions + CTGAN synthetic sessions
- Validate that augmented training improves Recall@K on the minority class
- Introduce model versioning so the active model is switchable without code changes

**Technical tasks:**
- `scripts/build_augmented_dataset.py`: merge real + synthetic session features, stratified split
- `notebooks/augmented_training.ipynb`: train v2, compare v1 vs v2 metrics, feature importance delta
- `src/scoring/model_registry.py`: `get_active_model_path()`, `set_active_model(version)`
- `models/ACTIVE_MODEL` text file (committed); `make select-model VERSION=v2` switches it
- `MLScorer` updated to read model path from `model_registry`

**Dependencies:** Phase 13 (`analytics.synthetic_sessions`), Phase 11 (baseline model)

**Deliverables:** `models/lead_scorer_lgbm_v2.pkl`, `docs/model_card_v2.md`, model registry, `make train-augmented`

**Why critical:** Without this phase, Phase 13's synthetic data generation produces rows
that are never used to improve the ML model. The full value chain is:
`real data → CTGAN → synthetic augmentation → retrain → better predictions`.
Phases 13 and 17 exist; Phase 18 is the missing link.

---

### Phase 19 — Prediction REST API Service (v2.3, **NEW**)

**Objectives:**
- Expose `predict_for_product()` as a FastAPI HTTP service in Docker Compose
- Decouple ML inference from the Streamlit process (no blocking, no ML imports in dashboard)
- Enable programmatic/external access to predictions

**Technical tasks:**
- `src/api/main.py`: `POST /predict/product`, `GET /health`, `GET /predictions/history`
- `src/api/schemas.py`: Pydantic request/response models
- `src/api/dependencies.py`: shared ClickHouse client + model loader (singleton)
- Docker Compose `prediction-api` service (port 8000, shared models volume read-only)
- `dashboard/pages/predict.py` updated: HTTP call to API + Prediction History expander

**Dependencies:** Phase 17 (`product_predictor.py`), Phase 18 (model versioning)

**Deliverables:** `src/api/`, `requirements-api.txt`, `prediction-api` Compose service, updated predict page

**Why critical:** Streamlit's event loop blocks on CPU-bound work. CTGAN sampling
takes several seconds. Without an async service layer, the dashboard freezes during
prediction and shows no progress feedback. The API pattern is also standard for any
real production deployment.

---

### Phase 20 — ML Monitoring & CI Hardening (v2.4, **NEW**)

**Objectives:**
- Detect CTGAN distribution drift before it silently degrades prediction quality
- Surface Redpanda consumer lag and ClickHouse query health in the dashboard
- Automate lint + unit tests + docker build on every pull request

**Technical tasks:**
- `src/monitoring/drift_detector.py`: JSD per feature, `analytics.drift_log` table
- Streamlit Model Health panel: drift status badge, per-feature bar chart
- `redpandadata/console` Docker Compose service (port 8080, zero code)
- ClickHouse slow-query panel: `system.query_log` aggregated in sidebar
- `.github/workflows/ci.yml`: `lint` (ruff), `unit-tests` (pytest), `docker-build`

**Dependencies:** Phase 19 (full Compose stack stable)

**Deliverables:** `src/monitoring/`, `make check-drift`, Redpanda Console, `.github/workflows/ci.yml`

---

## 4. Final End-to-End Workflow

### Client Product Input → Processing → Prediction → Results

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│  OPERATOR ACTION                                                                │
│  Opens dashboard → navigates to "Predict" tab                                  │
│  Fills form: product_name, category (dropdown from ClickHouse), price, keywords│
│  Clicks "Submit"                                                                │
└───────────────────────────────┬─────────────────────────────────────────────────┘
                                 │ HTTP POST /predict/product
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  PREDICTION API SERVICE (FastAPI, port 8000)                                   │
│  1. Validates input (Pydantic model)                                            │
│  2. Calls product_predictor.predict_for_product() in thread pool                │
│     ├── Loads models/ctgan_sessions.pkl                                         │
│     ├── CTGAN.sample(n=1000, conditions={"category": input.category})           │
│     │     └── Falls back to unconditional if category unseen → logs warning     │
│     ├── MLScorer.predict(sampled_sessions_df)  [uses ACTIVE_MODEL version]      │
│     └── Aggregates: conversion_rate, tier_distribution, top_features            │
│  3. Writes result to analytics.prediction_log                                   │
│  4. Returns JSON response                                                        │
└───────────────────────────────┬─────────────────────────────────────────────────┘
                                 │ JSON response
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  STREAMLIT PREDICT PAGE (dashboard/pages/predict.py)                            │
│  Receives API response (shown via st.spinner during request)                    │
│  Renders:                                                                        │
│    • Conversion Rate gauge (st.metric: e.g. "12.4%")                           │
│    • Tier Distribution pie chart (hot 12% / warm 38% / cold 50%)               │
│    • Top 5 Behavioral Signals bar chart (feature importances weighted by score) │
│    • Top 10 Scored Synthetic Sessions table                                     │
│    • Sample size note + disclaimer                                              │
│  Prediction History expander: last 5 predictions from GET /predictions/history │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Parallel flows running continuously

```
REAL TRAFFIC FLOW:
  Browser JS Tracker → RudderStack → Redpanda → ClickHouse (click_events)
  → analytics.session_features → analytics.lead_scores_rule_based
  → analytics.lead_scores_ml (batch: make score-sessions)
  → Leads dashboard (ranked table, filters, CSV export)

SYNTHETIC TRAFFIC FLOW (Phase 14):
  Mesa Simulator → Redpanda → ClickHouse (same path as real traffic)
  → sim_* prefixed session_ids distinguishable in filters

AI ASSISTANT FLOW (Phase 16):
  Lead row → "Generate Script" → LLM context builder → Claude API → script text
  → ai_script_log ClickHouse table → token/cost display

MONITORING FLOW (Phase 20):
  make check-drift → compare analytics.session_features vs analytics.synthetic_sessions
  → JSD per feature → analytics.drift_log → Streamlit Model Health panel
```

---

## 5. Architecture Recommendations

### A. Maintain the existing 3-layer principle everywhere

The existing architecture rule "aggregate in ClickHouse, never fetch raw rows to Python"
must extend to the new phases:
- Phase 19 API: the prediction log query uses `LIMIT` + `ORDER BY` in SQL before
  returning to FastAPI — never pull all rows into Python
- Phase 20 drift checker: export only the columns needed for JSD, not full row data

### B. SQL file numbering correction

The existing sequence is `001_`–`006_`. Two existing PLANS.md files incorrectly
reference `004_` for new tables that would conflict with Phase 9's `004_phase9_foundation.sql`:

| Phase | Incorrect reference | Correct number |
|-------|--------------------|--------------:|
| 13 | `004_synthetic_sessions.sql` | `007_synthetic_sessions.sql` |
| 17 | `004_prediction_log.sql` | `008_prediction_log.sql` |
| 20 | (new) drift_log | `009_drift_log.sql` |

Implementers should use the correct numbers. The `PLANS.md` files for Phases 13 and 17
should be updated when implementation begins.

### C. Model artifact versioning

Never commit `.pkl` binary model artifacts to git. The registry approach in Phase 18
(a committed text file `models/ACTIVE_MODEL` + gitignored `.pkl` files) is the correct
pattern. Document the regeneration commands in the README.

### D. Dependency isolation per subsystem

Maintain separate requirements files per concern:
- `requirements.txt` — core runtime (ClickHouse connect, Streamlit, Plotly)
- `requirements-ml.txt` — LightGBM, scikit-learn, pandas (ML venv: `.venv-ml`)
- `requirements-synth.txt` — ctgan, sdv (synthetic data venv, Phase 13)
- `requirements-api.txt` — FastAPI, uvicorn, pydantic (API service, Phase 19)
- `requirements-dev.txt` — ruff, pytest (CI only, Phase 20)

This prevents the Streamlit dashboard from importing heavy ML/CTGAN dependencies
and ensures each component can be built and tested independently.

### E. CTGAN conditional sampling fallback

Phase 17 specifies a fallback to unconditional sampling for unseen categories. This
fallback must be propagated through Phase 19's API response as a visible field
(`{"fallback_used": true, "fallback_reason": "category not in training distribution"}`).
The Streamlit page must show this as `st.info` (not silently ignored).

---

## 6. Risks & Future Improvements

### Risks

| Risk | Severity | Mitigation |
|------|----------|-----------|
| CTGAN training on small synthetic_sessions table produces poor quality | High | Phase 13 plan 02 enforces JS divergence < 0.1 gate before proceeding |
| Phase 18 augmented model performs worse than v1 (synthetic data adds noise) | Medium | v1 fallback via `make select-model VERSION=v1`; document comparison in model card |
| FastAPI prediction-api becomes a bottleneck under concurrent Streamlit users | Medium | CTGAN model loaded once at startup (not per-request); `n_sessions=1000` is configurable |
| CTGAN `category` conditional sampling fails for rare categories | Medium | Phase 17/19 unconditional fallback + visible warning to user |
| Redpanda consumer lag accumulates during long simulation runs (Phase 14) | Low | Redpanda Console (Phase 20) makes this observable; `sim_` prefix filtering limits dashboard impact |
| SQL file numbering conflicts (004 used twice) | Low | Fixed in Phase 18+ with correct numbering (007, 008, 009) |

### Future Improvements (Post v2.4)

1. **Online retraining trigger** — When drift_detector reports `status == "fail"` on
   3 consecutive days, auto-schedule a `make train-augmented` run via a GitHub Actions
   scheduled workflow. This closes the monitoring → retraining feedback loop.

2. **A/B model serving** — Phase 19's API could serve a random 10% of requests with
   `VERSION=v1` and log which version produced the response, enabling online evaluation
   of model quality on real operator queries.

3. **Product catalog integration** — Phase 17 currently requires the operator to manually
   enter product attributes. A future phase could pull attributes from a product catalog
   API (e.g., a connected e-commerce backend) to auto-populate the form.

4. **Async prediction jobs** — For large `n_sessions` requests (> 2,000), Phase 19's API
   could switch to an async job pattern: POST returns `job_id`, client polls
   `GET /predictions/{job_id}/status`. This avoids timeouts for heavy workloads.

5. **MLflow experiment tracking** — Phase 18 runs experiments in a notebook. A future
   milestone could add MLflow (`mlflow.lightgbm.autolog()`) for structured experiment
   comparison, artifact versioning, and a model registry UI.

6. **Feature store** — `analytics.session_features` is currently a read-time view (no
   materialization). Under heavy concurrent load, repeated UNION ALL queries on large
   tables could be slow. A scheduled materialized table refresh (daily or hourly) would
   improve inference latency for Phase 19.

---
*Written: 2026-05-08*
