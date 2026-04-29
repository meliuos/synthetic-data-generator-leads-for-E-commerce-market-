---
phase: 11
plan: 1
status: COMPLETE
shipped: 2026-04-29
---

# Phase 11 Plan 01 — Summary

## What shipped

| Artifact | Description |
|---|---|
| `notebooks/lead_scoring_model.ipynb` | 7-cell training notebook: data load from ClickHouse, stratified train/test split, 5-fold CV, final fit, test-set evaluation, rule-based baseline comparison, feature importances, joblib export. |
| `src/scoring/ml_scorer.py` | `MLScorer` class with lazy-loading model, `predict()` returning Float32 Series [0,1], `score_tier()` applying the same tier thresholds as `rules.py`. |
| `src/scoring/__init__.py` | `MLScorer` added to package exports. |
| `scripts/score_sessions.py` | Batch CLI: pulls all sessions from `analytics.session_features`, scores with `MLScorer`, inserts to `analytics.lead_scores_ml` in configurable batches. Flags: `--source`, `--batch-size`, `--dry-run`. |
| `infra/clickhouse/sql/006_ml_scores.sql` | `analytics.lead_scores_ml` — `ReplacingMergeTree(scored_at)` ordered by `(source, anonymous_user_id, session_id)`. |
| `scripts/smoke_phase11.sql` | Four queries: score count/range by source, [0,1] boundary check, top-10 ML leads, ML/rule join. |
| `requirements-ml.txt` | `lightgbm`, `scikit-learn`, `pandas`, `numpy`, `joblib`, `clickhouse-connect`, `imbalanced-learn`, `matplotlib`. |
| `models/.gitkeep` | Tracks `models/` in git; the `.pkl` binary is gitignored. |
| `Makefile` | `ml-setup`, `score-sessions`, `schema-phase11`, `smoke-test-phase11` targets. |

## Key decisions

| Decision | Reason |
|---|---|
| `scale_pos_weight = neg/pos` instead of SMOTE | Avoids positive leakage across CV folds; LightGBM handles the weight natively without resampling the training set |
| Retailrocket-only training corpus | Live sessions have too few conversions (~0) to contribute signal; Retailrocket provides 2.7M sessions with a ~0.82% conversion rate |
| Lazy imports in `ml_scorer.py` | The module must be importable in the unit-test venv (which has no ML deps) and in Streamlit Cloud deployments where `lightgbm` may not be installed |
| `ReplacingMergeTree(scored_at)` for `lead_scores_ml` | Re-runs of `score_sessions.py` (e.g., after a model update) dedup automatically; use `FINAL` in downstream queries to get the latest score per session |
| `_FEATURE_COLS` as single source of truth | Notebook, `ml_scorer.py`, and `score_sessions.py` all reference the same list — drift between training and serving is prevented |
| `models/` gitignored except `.gitkeep` | Binary model artifacts belong in a model registry or object store, not in git; `.gitkeep` ensures the directory is created on fresh clone |

## Workflow to regenerate the model

```bash
make ml-setup                                          # create .venv-ml
source .venv-ml/bin/activate
jupyter nbconvert --to notebook --execute \
  --ExecutePreprocessor.timeout=600 \
  notebooks/lead_scoring_model.ipynb                   # trains and saves model
make schema-phase11                                    # create lead_scores_ml table
make score-sessions                                    # populate ML scores
make smoke-test-phase11                                # verify
```
