---
phase: 13
milestone: v2.0
status: COMPLETE
---

# Phase 13 — CTGAN Behavioral Simulator

Train a Conditional Tabular GAN on `analytics.session_features` to generate synthetic
e-commerce sessions with realistic behavioral distributions, providing a controlled
augmentation corpus for the ML scorer and the simulation engine.

## Plans

### 13-01: ClickHouse schema + tooling scaffold ✓
- [x] Add `analytics.synthetic_sessions` table DDL to `infra/clickhouse/sql/007_synthetic_sessions.sql`
  - Schema mirrors `session_features` with an added `is_synthetic UInt8 DEFAULT 1` discriminator
  - Also adds `primary_category LowCardinality(String)` (category axis for Phase 17 conditional sampling)
  - Also adds `ml_lead_score Nullable(Float32)` and `ml_score_tier LowCardinality(String)` (scoring tags)
  - Idempotent DDL (`CREATE TABLE IF NOT EXISTS`)
- [x] Add `requirements-synth.txt` pinning `sdv>=1.9.0`, `ctgan>=0.9.0`, `joblib`, `pyarrow`, `scipy`, `jupyter`
- [x] Add `make synth-setup`, `make schema-phase13`, `make ctgan-train`, `make generate-synthetic`,
      `make smoke-test-phase13` Makefile targets
- [x] Add `.venv-synth/`, `data/session_features.parquet`, `models/ctgan_checkpoint_*.pkl`,
      `notebooks/ctgan_trainer_executed.ipynb` to `.gitignore`

### 13-02: CTGAN training notebook ✓
- [x] `notebooks/ctgan_trainer.ipynb` (7 cells):
  - Cell 1: imports, ClickHouse connection, assert Retailrocket data present
  - Cell 2: export `analytics.retailrocket_session_features` enriched with `primary_category`
    (derived via `retailrocket_raw.item_properties` JOIN) and `score_tier` (derived from
    Phase 10 rule weights in SQL); saves to `data/session_features.parquet`
  - Cell 3: define `SingleTableMetadata` with continuous/categorical column types;
    train `CTGANSynthesizer` for 300 epochs, save checkpoint every 50 epochs
    (`models/ctgan_checkpoint_N.pkl`); save final to `models/ctgan_sessions.pkl`
  - Cell 4: evaluate marginal distributions — KDE plots for all continuous features,
    JSD per feature (target < 0.10); saves `docs/ctgan_kde_plots.png`
  - Cell 5: verify conditional sampling for top-5 categories
    (`sample_from_conditions` with `Condition(primary_category=X)`)
  - Cell 6: smoke-test generation script with `--n-sessions 200 --dry-run`
  - Cell 7: write evaluation summary to `docs/ctgan_evaluation.md`
- [x] Notebook executed — `models/ctgan_sessions.pkl` produced (6.0 MB, 100 epochs, 200K-row stratified sample)

### 13-03: Generation script + smoke test ✓
- [x] `scripts/generate_synthetic_sessions.py`:
  - CLI: `--n-sessions INT` (default 10,000), `--category-filter STR` (optional), `--overwrite`,
    `--model PATH`, `--dry-run`
  - Loads `models/ctgan_sessions.pkl` (CTGANSynthesizer via joblib); fails with clear message if missing
  - Samples unconditionally or via `sample_from_conditions` with fallback to unconditional on failure
  - Applies Phase 11 `MLScorer` to tag each row with `ml_lead_score` / `ml_score_tier`
  - Coerces dtypes (rounds floats to ints for count columns, clips to valid ranges)
  - Assigns synthetic `session_id` (`syn_<hex12>`) and `anonymous_user_id` (`syn_user_<hex8>`)
  - Inserts into `analytics.synthetic_sessions` in batches of 10,000; `--overwrite` truncates first
  - Logs: sessions generated, insertion time, score tier distribution
- [x] Smoke test passed: `generate-synthetic N_SESSIONS=500` → `SELECT count() = 500` ✓

## Next Action

Run `make synth-setup && make schema-phase13` to set up the environment and apply the
ClickHouse schema. Then run `make ctgan-train` (requires Retailrocket data imported —
`make retailrocket-import` if not done yet). Finally validate with `make smoke-test-phase13`.

## Implementation Notes

- `primary_category` in `synthetic_sessions` is a string representation of the Retailrocket
  `category_id` (e.g. `'213'`) or `''` for unknown. This is the conditional sampling axis
  for Phase 17 (`predict_for_product(category='213', ...)`).
- `first_event_at` / `last_event_at` are deliberately excluded from `synthetic_sessions` —
  synthetic timestamps would be misleading. Use `generated_at` for time reference.
- The notebook trains on Retailrocket sessions only (same corpus as Phase 11) because live
  tracker sessions are small and lack scroll/search coverage.
- SQL file numbering: this file is `007_synthetic_sessions.sql` (following Phase 11's
  `006_ml_scores.sql`). Do not use `004_` — that is taken by Phase 9.
