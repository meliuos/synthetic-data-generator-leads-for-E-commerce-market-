"""
Product predictor — Phase 17.

Given a product's category, price, and keywords, samples N synthetic behavioral
sessions from the trained CTGAN model (conditioned on category), scores them
with the Phase 11 MLScorer, and returns a structured prediction dict.

The CTGAN synthesizer is loaded once and cached in-process for the lifetime of
the Python interpreter (avoids repeated 6 MB pickle deserialization on each call).

Usage:
    from src.prediction.product_predictor import predict_for_product

    result = predict_for_product(category="1051", price=29.99,
                                 keywords="wireless headphones", n_sessions=1000)
    # result.keys(): conversion_rate_pct, tier_distribution, top_features,
    #                sample_sessions, used_conditional, category, n_sessions_sampled
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.scoring.ml_scorer import MLScorer, _FEATURE_COLS

log = logging.getLogger(__name__)

_DEFAULT_MODEL_PATH = Path("models/ctgan_sessions.pkl")
_DEFAULT_N_SESSIONS = 1_000

# Score tier thresholds — mirror ml_scorer.score_tier
_HOT_MIN = 60
_WARM_MIN = 30


# ---------------------------------------------------------------------------
# Lazy-loaded singletons
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _load_synthesizer(model_path: str):
    """Load and cache the CTGANSynthesizer. Raises FileNotFoundError if missing."""
    try:
        import joblib
    except ImportError as exc:
        raise ImportError(
            "joblib is required. Install with: pip install -r requirements-synth.txt"
        ) from exc

    path = Path(model_path)
    if not path.exists():
        raise FileNotFoundError(
            f"CTGAN model not found at {path}. "
            "Run 'make ctgan-train' to train the model first."
        )
    log.info("Loading CTGAN synthesizer from %s …", path)
    return joblib.load(path)


@lru_cache(maxsize=1)
def _load_scorer() -> MLScorer:
    """Load and cache the LightGBM MLScorer."""
    return MLScorer()


# ---------------------------------------------------------------------------
# Core prediction logic
# ---------------------------------------------------------------------------

@dataclass
class PredictionResult:
    conversion_rate_pct: float
    tier_distribution: dict[str, int]          # {"hot": N, "warm": N, "cold": N}
    tier_distribution_pct: dict[str, float]    # {"hot": %, "warm": %, "cold": %}
    top_features: list[dict[str, Any]]         # [{name, importance}, …] top-5
    sample_sessions: pd.DataFrame              # top-10 by ml_lead_score
    used_conditional: bool                     # False = fallback to unconditional
    category: str
    n_sessions_sampled: int


def predict_for_product(
    category: str,
    price: float,
    keywords: str,
    n_sessions: int = _DEFAULT_N_SESSIONS,
    model_path: Path | str = _DEFAULT_MODEL_PATH,
) -> PredictionResult:
    """
    Sample N synthetic sessions for the given product category and score them.

    Parameters
    ----------
    category : str
        Category ID string (e.g. "1051"). Must match values in training data.
    price : float
        Product price in local currency (informational; not fed to CTGAN).
    keywords : str
        Comma-separated product keywords (informational; logged for audit trail).
    n_sessions : int
        Number of synthetic sessions to sample (default 1,000).
    model_path : Path | str
        Path to the trained CTGANSynthesizer pkl file.

    Returns
    -------
    PredictionResult
    """
    synthesizer = _load_synthesizer(str(model_path))

    df, used_conditional = _sample_sessions(synthesizer, category, n_sessions)
    df = _coerce_dtypes(df)
    df = _assign_ids(df)
    df = _score(df)

    return _build_result(df, category, used_conditional)


def _sample_sessions(
    synthesizer, category: str, n_sessions: int
) -> tuple[pd.DataFrame, bool]:
    """
    Try conditional sampling on category; fall back to unconditional on failure.
    Returns (dataframe, used_conditional).
    """
    try:
        from sdv.sampling import Condition

        condition = Condition(
            num_rows=n_sessions,
            column_values={"primary_category": category},
        )
        df = synthesizer.sample_from_conditions(conditions=[condition])

        if df.empty:
            log.warning(
                "Conditional sampling for category '%s' returned 0 rows — "
                "falling back to unconditional sampling.",
                category,
            )
            df = synthesizer.sample(num_rows=n_sessions)
            df["primary_category"] = ""
            return df, False

        log.info(
            "Conditional sampling OK: category=%s, sampled=%d rows", category, len(df)
        )
        return df, True

    except Exception as exc:
        log.warning(
            "Conditional sampling failed for category '%s' (%s) — "
            "falling back to unconditional sampling.",
            category, exc,
        )
        df = synthesizer.sample(num_rows=n_sessions)
        df["primary_category"] = df.get("primary_category", "")
        return df, False


def _coerce_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Clip and cast CTGAN float outputs to valid integer ranges."""
    int_cols = [
        "page_views", "product_views", "add_to_cart_count", "purchase_count",
        "search_count", "session_duration_seconds", "distinct_products_viewed",
    ]
    for col in int_cols:
        if col in df.columns:
            df[col] = df[col].round().clip(lower=0).astype("int64")

    if "cart_abandoned" in df.columns:
        df["cart_abandoned"] = df["cart_abandoned"].round().clip(0, 1).astype("int8")
    elif "add_to_cart_count" in df.columns and "purchase_count" in df.columns:
        df["cart_abandoned"] = (
            (df["add_to_cart_count"] > 0) & (df["purchase_count"] == 0)
        ).astype("int8")
    else:
        df["cart_abandoned"] = np.int8(0)

    if "max_scroll_pct" in df.columns:
        df["max_scroll_pct"] = df["max_scroll_pct"].clip(0.0, 100.0)
    else:
        df["max_scroll_pct"] = np.nan

    return df


def _assign_ids(df: pd.DataFrame) -> pd.DataFrame:
    n = len(df)
    df["session_id"] = [f"pred_{uuid.uuid4().hex[:10]}" for _ in range(n)]
    return df


def _score(df: pd.DataFrame) -> pd.DataFrame:
    """Apply MLScorer; handles missing model gracefully."""
    try:
        scorer = _load_scorer()
        df["ml_lead_score"] = scorer.predict(df)
        df["score_tier"] = scorer.score_tier(df["ml_lead_score"] * 100)
    except FileNotFoundError:
        log.warning(
            "ML model not found — scoring with rule heuristic. "
            "Run 'make score-sessions' to enable proper scoring."
        )
        df["ml_lead_score"] = _heuristic_score(df)
        df["score_tier"] = MLScorer.score_tier(df["ml_lead_score"] * 100)
    return df


def _heuristic_score(df: pd.DataFrame) -> pd.Series:
    """
    Lightweight fallback score when the LightGBM model is unavailable.
    Uses the same signals as the Phase 10 rule engine, normalised to [0, 1].
    """
    s = (
        df.get("add_to_cart_count", pd.Series(0, index=df.index)).clip(0, 5) * 12
        + df.get("purchase_count", pd.Series(0, index=df.index)).clip(0, 3) * 20
        + df.get("product_views", pd.Series(0, index=df.index)).clip(0, 10) * 3
        + df.get("search_count", pd.Series(0, index=df.index)).clip(0, 5) * 5
    ).clip(0, 100) / 100.0
    return s.astype("float32")


def _build_result(
    df: pd.DataFrame, category: str, used_conditional: bool
) -> PredictionResult:
    n = len(df)

    # Tier distribution
    tier_counts = df["score_tier"].value_counts().reindex(
        ["hot", "warm", "cold"], fill_value=0
    ).to_dict()
    tier_pct = {k: round(100 * v / n, 1) for k, v in tier_counts.items()}

    # Conversion rate: sessions with ml_lead_score >= 0.60 as proxy for converters
    conversion_rate_pct = round(float((df["ml_lead_score"] >= 0.60).mean() * 100), 2)

    # Top features: LightGBM importances from the cached model, if available
    top_features = _extract_feature_importances(df)

    # Top 10 sample sessions sorted by score descending
    sample_cols = [
        "session_id", "score_tier", "ml_lead_score",
        "product_views", "add_to_cart_count", "cart_abandoned",
    ]
    available = [c for c in sample_cols if c in df.columns]
    sample_sessions = (
        df[available]
        .sort_values("ml_lead_score", ascending=False)
        .head(10)
        .reset_index(drop=True)
    )

    return PredictionResult(
        conversion_rate_pct=conversion_rate_pct,
        tier_distribution=tier_counts,
        tier_distribution_pct=tier_pct,
        top_features=top_features,
        sample_sessions=sample_sessions,
        used_conditional=used_conditional,
        category=category,
        n_sessions_sampled=n,
    )


def _extract_feature_importances(df: pd.DataFrame) -> list[dict[str, Any]]:
    """
    Return top-5 feature importances from the LightGBM model.
    Falls back to correlation-based importance if the model is unavailable.
    """
    try:
        scorer = _load_scorer()
        model = scorer._model
        importances = model.feature_importances_
        features = _FEATURE_COLS
        pairs = sorted(
            zip(features, importances), key=lambda x: x[1], reverse=True
        )
        total = sum(imp for _, imp in pairs) or 1
        return [
            {"name": name, "importance": round(imp / total, 4)}
            for name, imp in pairs[:5]
        ]
    except Exception:
        # Fallback: variance of each feature column as proxy importance
        result = []
        for col in _FEATURE_COLS:
            if col in df.columns:
                var = float(df[col].var(skipna=True) or 0.0)
                result.append({"name": col, "importance": round(var, 4)})
        result.sort(key=lambda x: x["importance"], reverse=True)
        total = sum(r["importance"] for r in result) or 1
        for r in result:
            r["importance"] = round(r["importance"] / total, 4)
        return result[:5]
