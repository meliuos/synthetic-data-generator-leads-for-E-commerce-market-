"""
Unit tests for Phase 17 — product_predictor.py.

Tests use monkeypatching to avoid loading real CTGAN / LightGBM models,
so they run without any large binary dependencies.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.prediction.product_predictor import (
    PredictionResult,
    _assign_ids,
    _build_result,
    _coerce_dtypes,
    _extract_feature_importances,
    _heuristic_score,
    predict_for_product,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_df(n: int = 50) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame({
        "page_views": rng.integers(0, 20, n),
        "product_views": rng.integers(0, 15, n),
        "add_to_cart_count": rng.integers(0, 5, n),
        "purchase_count": rng.integers(0, 3, n),
        "search_count": rng.integers(0, 8, n),
        "session_duration_seconds": rng.integers(10, 3600, n),
        "distinct_products_viewed": rng.integers(1, 20, n),
        "cart_abandoned": rng.integers(0, 2, n),
        "max_scroll_pct": rng.uniform(0, 100, n),
        "primary_category": ["1051"] * n,
        "ml_lead_score": rng.uniform(0, 1, n).astype("float32"),
        "score_tier": rng.choice(["hot", "warm", "cold"], n),
    })


# ---------------------------------------------------------------------------
# _coerce_dtypes
# ---------------------------------------------------------------------------

class TestCoerceDtypes:
    def test_clips_negatives(self):
        df = pd.DataFrame({
            "page_views": [-5, 3],
            "product_views": [10, -1],
            "add_to_cart_count": [-1, 2],
            "purchase_count": [0, -3],
            "search_count": [2, -2],
            "session_duration_seconds": [-10, 60],
            "distinct_products_viewed": [5, -5],
        })
        result = _coerce_dtypes(df)
        for col in ["page_views", "product_views", "add_to_cart_count",
                    "purchase_count", "search_count", "session_duration_seconds",
                    "distinct_products_viewed"]:
            assert (result[col] >= 0).all(), f"{col} has negative values"

    def test_cart_abandoned_binary(self):
        df = pd.DataFrame({
            "cart_abandoned": [0.4, 0.7, -0.1, 1.9],
        })
        result = _coerce_dtypes(df)
        assert set(result["cart_abandoned"].unique()).issubset({0, 1})

    def test_cart_abandoned_inferred_when_missing(self):
        df = pd.DataFrame({
            "add_to_cart_count": [1, 0],
            "purchase_count": [0, 0],
        })
        result = _coerce_dtypes(df)
        assert "cart_abandoned" in result.columns
        assert result["cart_abandoned"].iloc[0] == 1
        assert result["cart_abandoned"].iloc[1] == 0

    def test_max_scroll_pct_clamped(self):
        df = pd.DataFrame({"max_scroll_pct": [-5.0, 110.0, 50.0]})
        result = _coerce_dtypes(df)
        assert result["max_scroll_pct"].max() <= 100.0
        assert result["max_scroll_pct"].min() >= 0.0

    def test_max_scroll_pct_nan_when_missing(self):
        df = pd.DataFrame({"page_views": [1, 2]})
        result = _coerce_dtypes(df)
        assert "max_scroll_pct" in result.columns
        assert result["max_scroll_pct"].isna().all()


# ---------------------------------------------------------------------------
# _assign_ids
# ---------------------------------------------------------------------------

class TestAssignIds:
    def test_unique_ids(self):
        df = _make_df(100)
        df = _assign_ids(df)
        assert df["session_id"].nunique() == 100

    def test_id_prefix(self):
        df = _assign_ids(_make_df(5))
        assert all(sid.startswith("pred_") for sid in df["session_id"])


# ---------------------------------------------------------------------------
# _heuristic_score
# ---------------------------------------------------------------------------

class TestHeuristicScore:
    def test_range(self):
        df = _make_df(200)
        scores = _heuristic_score(df)
        assert (scores >= 0).all() and (scores <= 1).all()

    def test_dtype(self):
        scores = _heuristic_score(_make_df(10))
        assert scores.dtype == "float32"

    def test_higher_cart_higher_score(self):
        low = pd.DataFrame({"add_to_cart_count": [0], "purchase_count": [0],
                            "product_views": [0], "search_count": [0]})
        high = pd.DataFrame({"add_to_cart_count": [5], "purchase_count": [3],
                             "product_views": [10], "search_count": [5]})
        assert _heuristic_score(high).iloc[0] > _heuristic_score(low).iloc[0]


# ---------------------------------------------------------------------------
# _build_result
# ---------------------------------------------------------------------------

class TestBuildResult:
    def test_returns_prediction_result(self):
        df = _make_df(100)
        r = _build_result(df, "1051", True)
        assert isinstance(r, PredictionResult)

    def test_tier_distribution_keys(self):
        df = _make_df(100)
        r = _build_result(df, "1051", True)
        assert set(r.tier_distribution.keys()) == {"hot", "warm", "cold"}
        assert set(r.tier_distribution_pct.keys()) == {"hot", "warm", "cold"}

    def test_tier_pct_sums_to_100(self):
        df = _make_df(100)
        r = _build_result(df, "1051", True)
        total = sum(r.tier_distribution_pct.values())
        assert abs(total - 100.0) < 0.5

    def test_conversion_rate_in_range(self):
        df = _make_df(500)
        r = _build_result(df, "1051", False)
        assert 0.0 <= r.conversion_rate_pct <= 100.0

    def test_sample_sessions_top10(self):
        df = _make_df(200)
        r = _build_result(df, "1051", True)
        assert len(r.sample_sessions) <= 10

    def test_used_conditional_propagated(self):
        df = _make_df(50)
        assert _build_result(df, "1051", True).used_conditional is True
        assert _build_result(df, "1051", False).used_conditional is False

    def test_category_propagated(self):
        df = _make_df(50)
        r = _build_result(df, "9999", True)
        assert r.category == "9999"

    def test_n_sessions_sampled(self):
        df = _make_df(77)
        r = _build_result(df, "1051", True)
        assert r.n_sessions_sampled == 77


# ---------------------------------------------------------------------------
# _extract_feature_importances — fallback path (no real model)
# ---------------------------------------------------------------------------

class TestExtractFeatureImportances:
    def test_returns_list(self):
        df = _make_df(100)
        result = _extract_feature_importances(df)
        assert isinstance(result, list)

    def test_at_most_5(self):
        df = _make_df(100)
        result = _extract_feature_importances(df)
        assert len(result) <= 5

    def test_each_entry_has_name_and_importance(self):
        df = _make_df(100)
        for entry in _extract_feature_importances(df):
            assert "name" in entry and "importance" in entry

    def test_importances_sum_to_one(self):
        df = _make_df(100)
        items = _extract_feature_importances(df)
        if items:
            total = sum(i["importance"] for i in items)
            assert abs(total - 1.0) < 0.01


# ---------------------------------------------------------------------------
# predict_for_product — integration with mocked synthesizer
# ---------------------------------------------------------------------------

class TestPredictForProduct:
    def _make_synthesizer(self, n=200):
        synth = MagicMock()
        synth.sample_from_conditions.return_value = _make_df(n)
        synth.sample.return_value = _make_df(n)
        return synth

    def test_returns_prediction_result(self):
        synth = self._make_synthesizer()
        with patch("src.prediction.product_predictor._load_synthesizer", return_value=synth), \
             patch("src.prediction.product_predictor._load_scorer", side_effect=FileNotFoundError):
            result = predict_for_product(
                category="1051", price=29.99, keywords="test",
                n_sessions=200, model_path=Path("dummy.pkl"),
            )
        assert isinstance(result, PredictionResult)

    def test_conditional_flag_true_when_sampling_succeeds(self):
        synth = self._make_synthesizer(200)
        with patch("src.prediction.product_predictor._load_synthesizer", return_value=synth), \
             patch("src.prediction.product_predictor._load_scorer", side_effect=FileNotFoundError):
            result = predict_for_product(
                category="1051", price=9.99, keywords="",
                n_sessions=200, model_path=Path("dummy.pkl"),
            )
        assert result.used_conditional is True

    def test_fallback_to_unconditional_on_empty_sample(self):
        synth = MagicMock()
        synth.sample_from_conditions.return_value = pd.DataFrame()
        synth.sample.return_value = _make_df(100)
        with patch("src.prediction.product_predictor._load_synthesizer", return_value=synth), \
             patch("src.prediction.product_predictor._load_scorer", side_effect=FileNotFoundError):
            result = predict_for_product(
                category="9999", price=1.0, keywords="",
                n_sessions=100, model_path=Path("dummy.pkl"),
            )
        assert result.used_conditional is False

    def test_file_not_found_propagates(self):
        with patch("src.prediction.product_predictor._load_synthesizer",
                   side_effect=FileNotFoundError("model not found")):
            with pytest.raises(FileNotFoundError):
                predict_for_product(
                    category="1051", price=1.0, keywords="",
                    n_sessions=100, model_path=Path("nonexistent.pkl"),
                )
