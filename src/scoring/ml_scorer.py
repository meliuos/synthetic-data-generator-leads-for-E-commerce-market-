"""
ML lead scorer — Phase 11.

Loads a trained LightGBM model from disk and scores a DataFrame of session
features, returning a calibrated probability [0, 1] per session.

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

    Usage:
        scorer = MLScorer()                        # loads models/lead_scorer_lgbm.pkl
        scores = scorer.predict(session_df)        # Series of float [0, 1], same index
        tier   = scorer.score_tier(scores * 100)   # 'hot' / 'warm' / 'cold' Series
    """

    def __init__(self, model_path: Path | str = DEFAULT_MODEL_PATH) -> None:
        try:
            import joblib
        except ImportError as exc:
            raise ImportError(
                "joblib is required for MLScorer. "
                "Install it with: pip install -r requirements-ml.txt"
            ) from exc

        self._model = joblib.load(model_path)
        self.model_version = MODEL_VERSION

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
