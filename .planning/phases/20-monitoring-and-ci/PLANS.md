---
phase: 20
milestone: v2.4
status: COMPLETE
depends_on: [19]
shipped: 2026-05-10
---

# Phase 20 — ML Monitoring & CI Hardening

Close the production loop: add prediction quality monitoring (model drift detection),
pipeline observability (Redpanda consumer lag, ClickHouse query health), and a GitHub
Actions CI pipeline that validates the system on every pull request.

## Why This Phase Exists

The system now generates synthetic data (Phase 13), trains models (Phases 11, 18),
serves predictions via API (Phase 19), and logs everything to ClickHouse. But there
is no mechanism to detect if:
- The CTGAN model drifts (synthetic distributions diverge from real over time)
- The ML scorer degrades (prediction quality drops after a data update)
- The pipeline silently fails (Redpanda consumer lag grows, ClickHouse queries regress)
- Code changes break existing functionality (no automated CI)

This phase adds the observability and safety net layer that a real production system
requires before being handed off to a team that didn't build it.

## Plans

### 20-01: Model drift & prediction quality monitoring
- [x] Create `src/monitoring/drift_detector.py`:
  - `compute_feature_jsd(real_df: DataFrame, synthetic_df: DataFrame) -> dict[str, float]`:
    Jensen-Shannon divergence per feature column between real session_features and synthetic_sessions
  - `check_drift(threshold: float = 0.15) -> DriftReport`:
    Exports both tables from ClickHouse, calls `compute_feature_jsd`, flags features exceeding the threshold
    Returns: `{checked_at, features_checked, features_drifted: [{name, jsd}], status: "ok"|"warn"|"fail"}`
  - Thresholds: JSD < 0.1 → ok; 0.1–0.15 → warn; > 0.15 → fail (same scale as Phase 13 training target)
- [x] Create `scripts/check_model_drift.py`: CLI wrapper around `drift_detector.check_drift()`, prints JSON report, exits 1 if status == "fail"
- [x] Add `make check-drift` Makefile target
- [x] Add a **Model Health** section to the Streamlit admin sidebar (`dashboard/app.py`):
  - Button: "Run Drift Check" → calls `drift_detector.check_drift()` inline
  - Displays: last check timestamp, drift status badge (green/yellow/red), per-feature JSD bar chart
  - Results cached in `st.session_state` for the browser session (don't re-run on every render)
- [x] Add `analytics.drift_log` ClickHouse table (`infra/clickhouse/sql/008_drift_log.sql`):
  `checked_at DateTime, features_drifted UInt8, max_jsd Float32, status LowCardinality(String)`
  — every drift check writes one row; enables trending "is drift getting worse over time?"

### 20-02: Pipeline observability (Redpanda Console + ClickHouse query log)
- [x] Add `redpandadata/console` service to `docker-compose.yml` (port 8080):
  - Provides Kafka consumer group lag visibility, topic throughput graphs, and partition health
  - Zero-code addition: the console reads from Redpanda's existing Admin API
  - Health check: `GET http://localhost:8080/api/cluster/overview`
  - Document in README: "Visit http://localhost:8080 to monitor Redpanda consumer lag"
- [x] Add slow query panel to Streamlit admin sidebar:
  - Query: `SELECT query_id, query, query_duration_ms, read_rows, memory_usage FROM system.query_log WHERE type = 'QueryFinish' AND query_duration_ms > 500 ORDER BY query_duration_ms DESC LIMIT 10`
  - Displayed as `st.dataframe` (truncate query text to 80 chars)
  - Refresh button (no auto-poll — dashboard must stay read-only and fast)
- [x] Add `make console-up` Makefile target: `docker compose up -d redpanda-console`

### 20-03: GitHub Actions CI pipeline
- [x] Create `.github/workflows/ci.yml`:
  ```yaml
  name: CI
  on: [push, pull_request]
  jobs:
    lint:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with: {python-version: "3.11"}
        - run: pip install ruff && ruff check src/ scripts/ tests/
    unit-tests:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with: {python-version: "3.11"}
        - run: pip install -r requirements.txt -r requirements-ml.txt
        - run: pytest tests/ -v --tb=short
    docker-build:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - run: docker compose build --no-cache
  ```
- [x] Ensure all existing tests pass under `pytest tests/` (fix any broken imports from new modules added in Phases 18-20)
- [x] Add `make lint` Makefile target: `ruff check src/ scripts/ tests/`
- [x] Add `ruff` to `requirements-dev.txt` (new file): `ruff>=0.4`
- [x] Document CI status badge in `README.md`: `[![CI](https://github.com/<org>/<repo>/actions/workflows/ci.yml/badge.svg)](…)`
- [x] Verify: push to a feature branch triggers all 3 CI jobs; `lint` and `unit-tests` pass; `docker-build` completes without error
