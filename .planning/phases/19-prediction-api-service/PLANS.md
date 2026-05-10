---
phase: 19
milestone: v2.3
status: PENDING
depends_on: [17, 18]
---

# Phase 19 — Prediction REST API Service

Expose the product prediction pipeline (Phase 17) as a standalone FastAPI service
running in Docker Compose. The Streamlit dashboard calls the API instead of importing
`product_predictor` directly, decoupling ML inference from the dashboard process and
enabling programmatic access from external tools.

## Why This Phase Exists

Phase 17 wires the prediction backend directly into the Streamlit page via a function
call. This works for a demo but has two production problems:
1. CTGAN sampling (1,000 sessions) blocks the Streamlit event loop for several seconds,
   freezing the UI. FastAPI with async background tasks solves this.
2. The prediction capability is locked inside the Streamlit process — it cannot be
   called by external scripts, CI pipelines, or a future mobile/web client.
This phase extracts the predictor into a proper HTTP service.

## Plans

### 19-01: FastAPI prediction service
- [ ] Create `src/api/main.py` (FastAPI application):
  - `POST /predict/product` — synchronous endpoint (≤10s budget per Phase 17 success criterion):
    - Request body: `{product_name: str, category: str, price: float, keywords: str, n_sessions: int = 1000}`
    - Validates inputs (category non-empty, price > 0, n_sessions in [100, 5000])
    - Calls `product_predictor.predict_for_product()` synchronously (CTGAN sampling is CPU-bound; runs in FastAPI's thread pool via `run_in_executor`)
    - Writes prediction result to `analytics.prediction_log`
    - Response: `{conversion_rate_pct, tier_distribution: {hot, warm, cold}, top_features, sample_sessions, n_sessions_sampled, model_version, predicted_at}`
  - `GET /health` — returns `{status: "ok", active_model: str, clickhouse: "ok"|"error"}`
  - `GET /predictions/history?limit=20` — reads from `analytics.prediction_log`, returns last N predictions
  - `GET /models/active` — returns current active model version (from `model_registry.get_active_model_path()`)
- [ ] Create `src/api/schemas.py`: Pydantic request/response models for all endpoints
- [ ] Create `src/api/dependencies.py`: shared ClickHouse client + model loader (loaded once at startup, not per-request)
- [ ] Add `requirements-api.txt`: `fastapi`, `uvicorn[standard]`, `pydantic>=2.0`
- [ ] Unit tests: `tests/test_prediction_api.py` — mock `product_predictor` and ClickHouse; test validation errors, happy path, unseen-category fallback

### 19-02: Docker Compose integration
- [ ] Add `prediction-api` service to `docker-compose.yml`:
  ```yaml
  prediction-api:
    build: .
    command: uvicorn src.api.main:app --host 0.0.0.0 --port 8000
    ports: ["8000:8000"]
    volumes:
      - ./models:/app/models:ro
    depends_on: [clickhouse]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      retries: 3
  ```
- [ ] Create `Dockerfile` (if not already present) or add a `api` build target to an existing multi-stage Dockerfile
- [ ] Add `make api-up` Makefile target: `docker compose up -d prediction-api`
- [ ] Add `make api-test` Makefile target: calls `POST /predict/product` with a test payload via `curl` and asserts HTTP 200
- [ ] Smoke test: `make api-up && make api-test` — response body contains `conversion_rate_pct` and `tier_distribution`, prediction written to `analytics.prediction_log`

### 19-03: Dashboard integration
- [ ] Update `dashboard/pages/predict.py` (Phase 17):
  - Replace direct `from src.prediction.product_predictor import predict_for_product` call with an HTTP request to `http://prediction-api:8000/predict/product` via `requests` (synchronous, Streamlit is not async)
  - Use `PREDICTION_API_URL` environment variable (default: `http://prediction-api:8000`) to allow local vs Docker addressing
  - Show `st.spinner("Generating predictions via ML service...")` during the request
  - Handle API errors: if API returns non-200, show `st.error` with the API's error message instead of crashing
- [ ] Add a **Prediction History** expander at the bottom of the predict page:
  - Calls `GET /predictions/history?limit=5` on page load
  - Renders a `st.dataframe` of the last 5 predictions (product_name, category, conversion_rate_pct, tier_hot_pct, predicted_at)
  - Allows users to compare predictions across different product inputs without leaving the page
- [ ] Verify: submitting the form in Streamlit calls the API (observable via `docker compose logs prediction-api`); the Streamlit UI does not import `ctgan` or `lightgbm` directly
