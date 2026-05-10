---
phase: 18
milestone: v2.3
status: PENDING
depends_on: [13, 11]
---

# Phase 18 — Augmented Training Pipeline

Retrain the ML lead scorer using a combined corpus of real Retailrocket sessions +
CTGAN-generated synthetic sessions (Phase 13). Introduce model versioning so the
active model can be swapped without code changes, and validate that the augmented
model improves recall on the minority class over the Phase 11 baseline.

## Why This Phase Exists

Phase 11 trained the LightGBM scorer on Retailrocket alone (~0.82% class imbalance,
scale_pos_weight mitigation only). Phase 13 generates synthetic sessions explicitly
designed to fill this gap — but there is no phase that closes the loop by retraining
with the augmented corpus. Without this phase, the synthetic data generation produces
rows that are never used to improve the model. This phase is the missing link between
CTGAN output (Phase 13) and the product prediction quality (Phase 17).

## Plans

### 18-01: Dataset augmentation & preparation
- [ ] Write `scripts/build_augmented_dataset.py`:
  - Exports `analytics.session_features` WHERE source = 'retailrocket' to Parquet (real data baseline)
  - Exports `analytics.synthetic_sessions` to Parquet (CTGAN-generated data)
  - Aligns feature columns: ensure `_FEATURE_COLS` from `src/scoring/ml_scorer.py` are present in both
  - Resolves feature gaps: `max_scroll_pct` is NULL in Retailrocket rows and may exist in synthetic rows — keep NULL semantics, do not impute
  - Merges real + synthetic (with an `is_synthetic UInt8` discriminator column preserved in the combined DataFrame)
  - Labels: `converted = 1` if `purchase_count > 0`, else `0` (same definition as Phase 11)
  - Stratified 80/20 train/test split (preserves class ratio across both sets)
  - Saves to `data/augmented_training.parquet` and `data/augmented_test.parquet`
  - Logs: real_rows, synthetic_rows, combined positive_rate, train_size, test_size
- [ ] Add `data/augmented_training.parquet` and `data/augmented_test.parquet` to `.gitignore`
- [ ] Add `make build-augmented-dataset` Makefile target

### 18-02: Augmented training notebook
- [ ] `notebooks/augmented_training.ipynb` (7 cells):
  - **Cell 1 — Load**: read `data/augmented_training.parquet` + `data/augmented_test.parquet`; display class distribution before/after augmentation
  - **Cell 2 — Baseline recall**: load `models/lead_scorer_lgbm.pkl` (Phase 11 v1); score the augmented test set; record AUC, Precision@K (K=top 10%), Recall@K
  - **Cell 3 — Augmented train**: LightGBM with same hyperparameters as Phase 11 (`scale_pos_weight`, 5-fold stratified CV on training set); train on combined real+synthetic
  - **Cell 4 — Comparison**: side-by-side table of v1 vs v2 AUC, Precision@K, Recall@K; if v2 does not improve Recall@K by at least 5pp, log a warning and explain why (not a hard failure — document and proceed)
  - **Cell 5 — Feature importances**: bar chart comparing top-10 feature importances v1 vs v2; note if synthetic data shifted importance weights
  - **Cell 6 — Save**: export to `models/lead_scorer_lgbm_v2.pkl` via joblib
  - **Cell 7 — Model card update**: print updated model card snippet for `docs/model_card_v2.md` (training data size, AUC, recall, training date)
- [ ] Commit evaluation artifact to `docs/model_card_v2.md` (model card for v2 scorer)

### 18-03: Model versioning & active model selection
- [ ] Create `src/scoring/model_registry.py`:
  - `MODELS = {"v1": "models/lead_scorer_lgbm.pkl", "v2": "models/lead_scorer_lgbm_v2.pkl"}`
  - `get_active_model_path() -> str`: reads `models/ACTIVE_MODEL` file (single line: "v1" or "v2"); falls back to "v1" if file does not exist
  - `set_active_model(version: str)`: writes the version string to `models/ACTIVE_MODEL`; validates the target `.pkl` exists first
- [ ] Update `src/scoring/ml_scorer.py`:
  - Replace hardcoded `models/lead_scorer_lgbm.pkl` path with `model_registry.get_active_model_path()`
  - `MLScorer` constructor accepts optional `model_version: str = None`; if provided, loads that specific version instead of the active one
- [ ] Add `models/ACTIVE_MODEL` file (initial content: `v1`) — committed to git (it is a text config, not a binary artifact)
- [ ] Add `make select-model VERSION=v2` Makefile target: calls `python -c "from src.scoring.model_registry import set_active_model; set_active_model('$(VERSION)')"`
- [ ] Add `make train-augmented` Makefile target: runs `make build-augmented-dataset` then executes the notebook via `jupyter nbconvert --to notebook --execute`
- [ ] Smoke test: `make select-model VERSION=v2 && make score-sessions --dry-run` exits 0 and logs the active model path as "v2"
