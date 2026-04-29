# Next Phases Roadmap — Lead Intelligence Platform

**Date:** 2026-04-29
**Continues from:** ROADMAP.md (Phases 1–8), CURRENT-STATE.md, ARCHITECTURE-REVIEW.md
**Context:** v1.1 is 5/6 plans complete. Phase 7 (Retailrocket import) must ship first to
unlock the corpus that all v1.2 ML work depends on.

---

## v1.1 Status: Complete

v1.1 is fully shipped (verified 2026-04-29). All 4 phases (5–8) and all 18 requirements
complete. The Retailrocket corpus is imported and queryable in `retailrocket_raw.*`. The
project enters v1.2 immediately.

---

## v1.2 — Lead Scoring & Identification

**Goal:** Transform captured behavioral signals into ranked lead candidates. A lead is a
visitor whose behavior pattern indicates purchase intent — repeat product views, cart activity,
high-intent searches — even if they never completed a purchase.

**Depends on:** Phase 7 complete (Retailrocket corpus in ClickHouse)

**Parallelism:** Phases 9 and 10 can run in parallel once Phase 7 ships.
Phase 11 depends on Phase 10 baseline. Phase 12 depends on Phase 11 (scores must exist before
the dashboard can surface them).

---

### Phase 9: Lead Scoring Data Foundation

**Objective:** Build the data layer that v1.2 scoring models will consume — a unified events
view, a per-session feature table, and the ClickHouse SQL that computes behavioral signals.

**Depends on:** Phase 7 (Retailrocket tables must exist for the UNION)

**Key tasks:**
1. Define `analytics.unified_events` — read-time UNION ALL view across `analytics.click_events`
   and `retailrocket_raw.events`, with a `source` discriminator column (`'live'` vs `'retailrocket'`).
   Add to `infra/clickhouse/sql/003_unified_view.sql`.
2. Define `analytics.session_features` — a materialized view (or scheduled query) that
   computes per-session behavioral signals:
   - `session_id`, `anonymous_user_id`, `page_views`, `product_views`, `add_to_cart_count`,
     `purchase_count`, `search_count`, `max_scroll_pct`, `session_duration_seconds`,
     `distinct_products_viewed`, `cart_abandoned` (add_to_cart=true AND purchase=false)
3. Verify the feature table is queryable for both live events and Retailrocket rows.
4. Write `scripts/verify_features.sql` — a smoke query confirming feature coverage across
   both sources.

**Expected outcome:** `SELECT * FROM analytics.session_features LIMIT 10` returns populated
rows for both live tracker sessions and Retailrocket sessions. Feature SQL is reviewed and
locked before scoring logic builds on top.

---

### Phase 10: Rule-Based Lead Scoring Engine

**Objective:** Implement a deterministic, interpretable lead score from behavioral signals.
Rule-based scoring is the first layer — it's fast, requires no training, and gives a usable
score immediately. It also provides the baseline to beat for the ML model in Phase 11.

**Depends on:** Phase 9 (session_features view must exist)

**Key tasks:**
1. Define the scoring rubric in `src/scoring/rules.py` (plain Python, no ML):
   - +30: any `add_to_cart` event in session (strong purchase intent signal)
   - +20: `purchase` event (already converted — high-value repeat buyer candidate)
   - +15: ≥3 distinct product views in session (browsing depth)
   - +10: `search` event with results (active search intent)
   - +10: scroll_depth > 70% on a product page (high engagement)
   - -10: session has only 1 page_view and no e-commerce events (bouncer)
   - Score capped at 100. Stored as `lead_score INT, score_tier ENUM('hot', 'warm', 'cold')`
2. Apply rules to `analytics.session_features` via a ClickHouse view
   `analytics.lead_scores_rule_based`.
3. Write `tests/test_scoring_rules.py` — unit tests covering edge cases: all signals present
   (max score), bounce session (min score), purchase without cart (direct buy).
4. Validate: spot-check 10 Retailrocket sessions against expected scores.

**Expected outcome:** `SELECT anonymous_user_id, lead_score, score_tier FROM analytics.lead_scores_rule_based ORDER BY lead_score DESC LIMIT 20` returns a ranked candidate list.

---

### Phase 11: ML Lead Scoring Model

**Objective:** Train a LightGBM binary classifier (converted vs not-converted) on Retailrocket
sessions, export it, and serve predictions alongside the rule-based scores.

**Depends on:** Phase 10 (rule-based baseline must exist as benchmark; feature engineering SQL
from Phase 9 is reused as model inputs)

**Key tasks:**
1. Prepare the training dataset:
   - Pull `session_features` for all Retailrocket sessions.
   - Label: `converted = 1` if session has a `transaction` event, else `0`.
   - Note class imbalance: ~0.82% conversion rate in Retailrocket — use SMOTE or `scale_pos_weight`.
2. Train in `notebooks/lead_scoring_model.ipynb`:
   - Features: `product_views`, `add_to_cart_count`, `distinct_products_viewed`,
     `max_scroll_pct`, `search_count`, `session_duration_seconds`
   - Model: LightGBM with 5-fold stratified CV. Metric: ROC-AUC + Precision@K (K=top 10%).
   - Baseline: rule-based score as a single-feature logistic regression to beat.
3. Export trained model to `models/lead_scorer_lgbm.pkl` (joblib).
4. Write `src/scoring/ml_scorer.py` — loads the model, accepts a session_features dataframe,
   returns `ml_lead_score FLOAT (0–1)` per session.
5. Store ML scores in `analytics.lead_scores_ml` (ClickHouse table, populated by a daily
   batch run of `scripts/score_sessions.py`).
6. Document model card: training data size, AUC, feature importances, known gaps (Retailrocket
   lacks `remove_from_cart` and `search` — those features will be NULL in Retailrocket rows).

**Expected outcome:** ML model achieves ROC-AUC > 0.75 on held-out Retailrocket test set.
Scores for both Retailrocket and live tracker sessions are available in ClickHouse.

---

### Phase 12: Lead Identification Dashboard

**Objective:** Surface the scored leads in the existing Streamlit dashboard as a new panel —
a ranked table of candidate leads with score breakdown and behavioral signals.

**Depends on:** Phase 11 (scores must exist in ClickHouse before the panel can query them)

**Key tasks:**
1. Add a new Streamlit page `dashboard/pages/leads.py` (multi-page app pattern):
   - Table: `anonymous_user_id`, `score_tier`, `rule_score`, `ml_score`, `product_views`,
     `add_to_cart_count`, `cart_abandoned`, `session_duration_seconds`, `source`
   - Filters: score tier (hot / warm / cold), source (live / retailrocket), date range
   - Default sort: `ml_score DESC`
2. Add ClickHouse query `dashboard/heatmap_queries.py` → `get_lead_candidates(tier, source, date_from, date_to)` — returns aggregate only (no raw event rows).
3. Score breakdown tooltip per row: show which rules fired and the feature values that drove
   the ML score.
4. Export button: download the ranked table as CSV for stakeholder reporting.
5. Empty state: "No leads scored yet — run `make score-sessions` to populate scores."

**Expected outcome:** Dashboard has a "Leads" page showing a ranked candidate table, filterable
by tier and source, with CSV export. Panel queries run in <2s (ClickHouse-side aggregation).

---

## v2.0 — Synthetic Data Generation

**Goal:** Generate realistic synthetic e-commerce behavior datasets that augment Retailrocket
for training, handle class imbalance, and enable simulation of new acquisition strategies.

**Depends on:** v1.2 complete (feature vocabulary and schema are stable inputs to the generator)

**Note:** This is CdC Phase 3/4. Listed here for roadmap continuity. Planning should not
start until v1.2 Phase 12 ships.

---

### Phase 13: CTGAN Behavioral Simulator

**Objective:** Train a CTGAN (Conditional Tabular GAN) on `analytics.session_features` to
generate synthetic sessions with realistic behavioral distributions.

**Depends on:** Phase 9 (session_features), Phase 11 (trained model provides quality signal)

**Key tasks:**
1. Install `ctgan` (SDV library) in a dedicated `requirements-synth.txt`.
2. Extract training data: `analytics.session_features` (all columns, both sources, deduplicated
   by `anonymous_user_id + session_id`).
3. Train CTGAN in `notebooks/ctgan_trainer.ipynb`:
   - Define column metadata (continuous vs discrete fields).
   - Train for 300 epochs, checkpoint every 50.
   - Evaluate: compare marginal distributions of synthetic vs real (KDE plots, Jensen-Shannon
     divergence per feature).
4. Export trained model to `models/ctgan_sessions.pkl`.
5. Write `scripts/generate_synthetic_sessions.py`:
   - Accepts `--n_sessions INT` (default: 10,000)
   - Generates sessions, applies the Phase 11 ML scorer to tag them with lead scores
   - Inserts into `analytics.synthetic_sessions` (schema mirrors `session_features`)
6. Add `make generate-synthetic` Makefile target.

**Expected outcome:** `analytics.synthetic_sessions` contains N synthetic rows with realistic
feature distributions. Jensen-Shannon divergence < 0.1 on all continuous features.

---

### Phase 14: Simulation Engine (Mesa / SimPy)

**Objective:** Build an agent-based e-commerce traffic simulator that generates event streams
(not just session aggregates) — enabling "what-if" scenario testing for lead acquisition.

**Depends on:** Phase 13 (CTGAN provides the behavioral prior for agent initialization)

**Key tasks:**
1. Design agent types in `src/simulation/agents.py` (Mesa framework):
   - `BrowserAgent`: generates click/scroll/product_view events based on CTGAN-sampled profile
   - `BuyerAgent`: has a `conversion_probability` drawn from the ML model's calibrated output
   - `AbandonerAgent`: adds to cart then exits (tests cart abandonment detection)
2. Implement environment in `src/simulation/ecommerce_env.py` (Mesa `Model`):
   - Time step = 1 minute of simulated traffic
   - Configurable: `n_agents`, `session_duration_mean`, `product_catalog_size`
3. Event emission: simulator pushes events directly to the Redpanda topic (same pipeline as
   the live tracker), so all downstream ClickHouse tables and dashboard panels work unchanged.
4. Write `scripts/run_simulation.py`:
   - CLI: `--n-agents 1000 --duration-minutes 60 --seed 42`
   - Logs: events emitted count, conversion rate, session duration distribution
5. Smoke test: run a 100-agent, 10-minute simulation and verify events appear in
   `analytics.click_events` within 30 seconds.

**Expected outcome:** A 1,000-agent, 60-minute simulation populates ClickHouse with realistic
synthetic events that are indistinguishable to the dashboard from real traffic.

---

## v2.1 — AI Commercial Assistant

**Goal:** Generate personalized sales outreach scripts for candidate leads identified in v1.2,
using an LLM with lead behavioral context as grounding.

**Depends on:** Phase 12 (lead identification — scores and behavioral signals must exist)

**Note:** This is CdC Phase 5. Listed here for roadmap continuity. Architecture decisions
should not be made until v2.0 is underway.

---

### Phase 15: Lead Profiling & LLM Context Builder

**Objective:** Build the context assembly layer that translates a lead's behavioral signals
into a structured prompt payload for the LLM.

**Depends on:** Phase 12 (lead candidates with scores and signals)

**Key tasks:**
1. Design `src/ai/lead_profiler.py`:
   - Accepts `anonymous_user_id` (or batch)
   - Queries `analytics.lead_scores_ml + session_features + purchase_items` for the lead
   - Produces a structured JSON context object: `{score_tier, top_categories, viewed_products,
     cart_abandoned, session_count, avg_scroll_pct, last_active}`
2. Write `src/ai/prompt_builder.py`:
   - Templates: one per score tier (hot / warm / cold)
   - Injects lead context into the template
   - Adds guardrails: max prompt tokens, PII-safe fields only (anonymous_user_id, no email/IP)
3. Define the LLM interface in `src/ai/llm_client.py`:
   - Use Claude API (`claude-sonnet-4-6`) via the Anthropic SDK
   - Include prompt caching headers (`cache_control: {"type": "ephemeral"}`) on the system
     prompt (the template is static per tier — high cache hit rate expected)
   - Return: `script_text`, `model`, `input_tokens`, `cache_tokens`, `output_tokens`
4. Log all LLM calls to `analytics.ai_script_log` (ClickHouse table): `lead_id`, `tier`,
   `model`, `prompt_tokens`, `cache_tokens`, `output_tokens`, `cost_usd`, `generated_at`.

**Expected outcome:** `python -c "from src.ai.lead_profiler import build_script; print(build_script('anon_123'))"` returns a personalized sales script in <3 seconds.

---

### Phase 16: AI Script Generation Dashboard Panel

**Objective:** Surface the script generation capability in the Streamlit dashboard as an
interactive panel on the Leads page.

**Depends on:** Phase 15 (LLM context builder must be callable from the dashboard)

**Key tasks:**
1. Add "Generate Script" button to each row in the Leads table (Phase 12 panel).
2. On click: call `build_script(anonymous_user_id)` asynchronously (use `st.spinner`).
3. Display the generated script in a `st.text_area` with a copy-to-clipboard button.
4. Show token usage and estimated cost (from `ai_script_log`) below the script.
5. Add a script history panel: last 10 generated scripts for the session, queryable from
   `analytics.ai_script_log`.
6. Add a `make test-ai` target that generates a script for the top-scored lead and verifies
   the output is non-empty and under 500 words.

**Expected outcome:** Dashboard users can click a button on any lead row and receive a
personalized sales script in <5 seconds, with token usage displayed.

---

## Phase Summary Table

| Phase | Milestone | Name | Depends On | Priority |
|-------|-----------|------|-----------|----------|
| ~~7~~ | ~~v1.1~~ | ~~Retailrocket Import~~ | ~~—~~ | ~~Complete (2026-04-29)~~ |
| 9 | v1.2 | Lead Scoring Data Foundation | Phase 7 ✓ | **High — current entry point** |
| 10 | v1.2 | Rule-Based Lead Scoring | Phase 9 | High |
| 11 | v1.2 | ML Lead Scoring Model | Phase 10 | High |
| 12 | v1.2 | Lead Identification Dashboard | Phase 11 | High |
| 13 | v2.0 | CTGAN Behavioral Simulator | Phase 9, 11 | Medium |
| 14 | v2.0 | Simulation Engine (Mesa) | Phase 13 | Medium |
| 15 | v2.1 | Lead Profiling & LLM Context | Phase 12 | Medium |
| 16 | v2.1 | AI Script Generation Panel | Phase 15 | Low |

---

## Execution Order

```
Phase 7 (Retailrocket) — complete v1.1
  ↓
Phase 9 (Data Foundation) ──────┐
                                 ├── can run in parallel
Phase 10 (Rule Scoring) ────────┘
  ↓
Phase 11 (ML Scoring)
  ↓
Phase 12 (Lead Dashboard)   ← v1.2 DONE
  ↓
Phase 13 (CTGAN) ────────────┐
                              ├── can run in parallel
Phase 14 (Simulation) ───────┘  ← v2.0 DONE
  ↓
Phase 15 (LLM Context)
  ↓
Phase 16 (AI Panel)         ← v2.1 DONE
```

---
*Written: 2026-04-29*
