---
phase: 17
milestone: v2.2
status: PENDING
depends_on: [13, 11]
---

# Phase 17 — Product Input & Lead Prediction Interface

Operator-facing Streamlit page: enter a product (name, category, price, keywords) → receive
ML-backed lead predictions powered by CTGAN conditional sampling + the Phase 11 ML scorer.

## Plans

### 17-01: `product_predictor.py` backend
- [ ] Create `src/prediction/product_predictor.py`:
  - `predict_for_product(category: str, price: float, keywords: str, n_sessions: int = 1000) -> dict`
  - Loads `models/ctgan_sessions.pkl`; samples N sessions conditioned on `category`
  - Falls back to unconditional sampling + logs a warning if category is unseen in training data
  - Runs `MLScorer` (from `src/scoring/ml_scorer.py`) on sampled sessions
  - Returns: `{conversion_rate_pct, tier_distribution: {hot, warm, cold}, top_features: [{name, importance}], sample_sessions: DataFrame}`
- [ ] Write `scripts/predict_product.py` CLI wrapper:
  - `--product STR --category INT --price FLOAT --keywords STR --n-sessions INT`
  - Calls `predict_for_product()`, prints JSON result, writes to `analytics.prediction_log`
- [ ] Unit tests: `tests/test_product_predictor.py` — mock CTGAN + MLScorer, verify output shape and fallback behavior

### 17-02: `dashboard/pages/predict.py` Streamlit page
- [ ] Form inputs (all inside `st.form`):
  - Product name: `st.text_input`
  - Category: `st.selectbox` populated from `SELECT categoryid, name FROM retailrocket_raw.category_tree ORDER BY name`
  - Price: `st.number_input` (min_value=0.01)
  - Keywords: `st.text_area`
  - Submit button triggers validation then `product_predictor.predict_for_product()`
- [ ] Results display (shown after submit, wrapped in `st.spinner`):
  - Conversion rate: `st.metric` gauge showing `{conversion_rate_pct:.1f}%`
  - Tier breakdown: Plotly pie chart (hot/warm/cold counts)
  - Top 5 behavioral signals: Plotly horizontal bar chart (feature importances weighted by score)
  - Top 10 synthetic sessions: `st.dataframe` with columns `session_id`, `score_tier`, `ml_lead_score`, `product_views`, `add_to_cart_count`, `cart_abandoned`
  - Sample size note: "Based on N synthetic sessions"
  - Disclaimer: "Predictions are based on synthetic behavioral data and are indicative only."
- [ ] Invalid form: show `st.warning` inline without calling the backend
- [ ] Unseen category fallback: show `st.info` banner noting unconditional sampling was used

### 17-03: `analytics.prediction_log` ClickHouse table + Makefile target
- [ ] `infra/clickhouse/sql/008_prediction_log.sql` (idempotent DDL):
  - `analytics.prediction_log` MergeTree table:
    `product_name String, category String, price Float32, keywords String,
     n_sessions_sampled UInt32, conversion_rate_pct Float32,
     tier_hot_pct Float32, tier_warm_pct Float32, tier_cold_pct Float32,
     predicted_at DateTime DEFAULT now()`
  - ORDER BY `(category, predicted_at)`
- [ ] Update `Makefile`: `make predict-product` target running `scripts/predict_product.py`
- [ ] Verify: form submission + CLI both write to `prediction_log`; `SELECT count() FROM analytics.prediction_log` increments each time
