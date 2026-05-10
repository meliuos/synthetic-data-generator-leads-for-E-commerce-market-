"""
ML lead scorer — Phase 11, updated Phase 18.

Loads a trained LightGBM model from disk and scores a DataFrame of session
features, returning a calibrated probability [0, 1] per session.

Phase 18 changes:
  - MLScorer now reads the active model via model_registry.get_active_model_path()
    when no explicit path or version is supplied.
  - New keyword-only argument `model_version` lets callers request a specific
    registered version ("v1", "v2") without knowing the file path.
  - All existing callers that pass an explicit model_path continue to work
    without any changes (backwards-compatible).

Design constraints:
  - No import-time dependency on lightgbm or joblib; both are imported lazily
    inside MLScorer.__init__ so the module is importable in environments where
    ML libraries are not installed (e.g., the unit-test venv for Phase 10).
  - Feature columns must match the training schema exactly. _FEATURE_COLS is the
    single source of truth — score_sessions.py selects only these columns before
    calling predict().
  - max_scroll_pct may be NULL (None / NaN). LightGBM handles NaN natively; the
    DataFrame must NOT fill NaN with 0 before prediction to preserve the signal.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

# Kept for backwards-compatibility; registry is now authoritative for default path.
DEFAULT_MODEL_PATH = Path("models/lead_scorer_lgbm.pkl")
MODEL_VERSION = "lgbm_v1"

# Must match the feature list used during training in notebooks/lead_scoring_model.ipynb.
_FEATURE_COLS: list[str] = [
    "product_views",
    "add_to_cart_count",
    "distinct_products_viewed",
    "max_scroll_pct",           # Nullable — NaN is valid; LightGBM handles it
    "search_count",
    "session_duration_seconds",
]


class MLScorer:
    """
    Wraps a trained LightGBM classifier for batch session scoring.

    Argument resolution order (first match wins):
      1. model_version="v2"  → load the registered v2 pkl path
      2. model_path="..."    → load that explicit path (legacy callers)
      3. (neither)           → load model_registry.get_active_model_path()

    Usage:
        scorer = MLScorer()                        # loads active model (from ACTIVE_MODEL)
        scorer = MLScorer(model_version="v2")      # load v2 specifically
        scorer = MLScorer("models/custom.pkl")     # legacy explicit path
        scores = scorer.predict(session_df)        # Series of float [0, 1], same index
        tier   = scorer.score_tier(scores * 100)   # 'hot' / 'warm' / 'cold' Series
    """

    def __init__(
        self,
        model_path: Path | str | None = None,
        *,
        model_version: str | None = None,
    ) -> None:
        try:
            import joblib
        except ImportError as exc:
            raise ImportError(
                "joblib is required for MLScorer. "
                "Install it with: pip install -r requirements-ml.txt"
            ) from exc

        if model_version is not None:
            from src.scoring.model_registry import MODELS
            if model_version not in MODELS:
                raise ValueError(
                    f"Unknown model version '{model_version}'. "
                    f"Available: {sorted(MODELS)}"
                )
            resolved = Path(MODELS[model_version])
            self.model_version = f"lgbm_{model_version}"
        elif model_path is not None:
            resolved = Path(model_path)
            # Preserve the existing version tag so callers that pass model_path
            # explicitly (e.g. score_sessions.py) see no change.
            self.model_version = MODEL_VERSION
        else:
            from src.scoring.model_registry import get_active_model_path, get_active_version
            resolved = Path(get_active_model_path())
            self.model_version = f"lgbm_{get_active_version()}"

        self._model = joblib.load(resolved)

    def predict(self, df: "pd.DataFrame") -> "pd.Series":
        """
        Return calibrated probability [0, 1] for each row in df.

        df must contain all columns in _FEATURE_COLS. Extra columns are ignored.
        Index is preserved in the returned Series.
        """
        import pandas as pd

        X = df[_FEATURE_COLS].copy()
        proba = self._model.predict_proba(X)[:, 1]
        return pd.Series(proba, index=df.index, name="ml_lead_score", dtype="float32")

    @staticmethod
    def score_tier(ml_score_0_100: "pd.Series") -> "pd.Series":
        """
        Map a Series of scores in [0, 100] to tier labels using the same
        thresholds as the rule-based engine (TIER_HOT_MIN=60, TIER_WARM_MIN=30).
        """
        import numpy as np
        import pandas as pd

        tiers = np.select(
            [ml_score_0_100 >= 60, ml_score_0_100 >= 30],
            ["hot", "warm"],
            default="cold",
        )
        return pd.Series(tiers, index=ml_score_0_100.index, name="ml_score_tier")
