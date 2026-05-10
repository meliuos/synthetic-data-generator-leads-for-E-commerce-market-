"""
Unit tests for Phase 18 — model_registry.py and MLScorer registry integration.

All tests use tmp_path (pytest fixture) so they never touch the real
models/ACTIVE_MODEL file or any actual pkl artifact.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scoring.model_registry import (
    MODELS,
    _ACTIVE_MODEL_FILE,
    _FALLBACK_VERSION,
    get_active_model_path,
    get_active_version,
    set_active_model,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_active_file(tmp_path: Path, content: str | None):
    """
    Return a context manager that redirects _ACTIVE_MODEL_FILE to a temp file.
    If content is None the file is not created (simulates missing file).
    """
    fake_file = tmp_path / "ACTIVE_MODEL"
    if content is not None:
        fake_file.write_text(content, encoding="utf-8")
    return patch("src.scoring.model_registry._ACTIVE_MODEL_FILE", fake_file)


# ---------------------------------------------------------------------------
# get_active_version
# ---------------------------------------------------------------------------

class TestGetActiveVersion:
    def test_returns_v1_when_file_missing(self, tmp_path):
        with _patch_active_file(tmp_path, None):
            assert get_active_version() == _FALLBACK_VERSION

    def test_reads_v1_from_file(self, tmp_path):
        with _patch_active_file(tmp_path, "v1\n"):
            assert get_active_version() == "v1"

    def test_reads_v2_from_file(self, tmp_path):
        with _patch_active_file(tmp_path, "v2\n"):
            assert get_active_version() == "v2"

    def test_falls_back_on_unknown_version(self, tmp_path):
        with _patch_active_file(tmp_path, "v99\n"):
            assert get_active_version() == _FALLBACK_VERSION

    def test_strips_whitespace(self, tmp_path):
        with _patch_active_file(tmp_path, "  v2  \n"):
            assert get_active_version() == "v2"


# ---------------------------------------------------------------------------
# get_active_model_path
# ---------------------------------------------------------------------------

class TestGetActiveModelPath:
    def test_returns_v1_path_when_file_missing(self, tmp_path):
        with _patch_active_file(tmp_path, None):
            assert get_active_model_path() == MODELS["v1"]

    def test_returns_v2_path_when_selected(self, tmp_path):
        with _patch_active_file(tmp_path, "v2\n"):
            assert get_active_model_path() == MODELS["v2"]

    def test_path_is_string(self, tmp_path):
        with _patch_active_file(tmp_path, "v1\n"):
            assert isinstance(get_active_model_path(), str)


# ---------------------------------------------------------------------------
# set_active_model
# ---------------------------------------------------------------------------

class TestSetActiveModel:
    def test_writes_version_to_file(self, tmp_path):
        fake_pkl = tmp_path / "lead_scorer_lgbm.pkl"
        fake_pkl.write_bytes(b"")  # simulate existing model file
        fake_active = tmp_path / "ACTIVE_MODEL"

        with (
            patch("src.scoring.model_registry._ACTIVE_MODEL_FILE", fake_active),
            patch.dict("src.scoring.model_registry.MODELS", {"v1": str(fake_pkl)}),
        ):
            set_active_model("v1")
            assert fake_active.read_text().strip() == "v1"

    def test_raises_value_error_for_unknown_version(self, tmp_path):
        with _patch_active_file(tmp_path, "v1\n"):
            with pytest.raises(ValueError, match="Unknown model version"):
                set_active_model("v99")

    def test_raises_file_not_found_when_pkl_missing(self, tmp_path):
        fake_active = tmp_path / "ACTIVE_MODEL"
        missing_pkl = tmp_path / "nonexistent.pkl"
        with (
            patch("src.scoring.model_registry._ACTIVE_MODEL_FILE", fake_active),
            patch.dict("src.scoring.model_registry.MODELS", {"v1": str(missing_pkl)}),
        ):
            with pytest.raises(FileNotFoundError):
                set_active_model("v1")

    def test_roundtrip_read_after_write(self, tmp_path):
        fake_pkl = tmp_path / "lead_scorer_lgbm_v2.pkl"
        fake_pkl.write_bytes(b"")
        fake_active = tmp_path / "ACTIVE_MODEL"
        with (
            patch("src.scoring.model_registry._ACTIVE_MODEL_FILE", fake_active),
            patch.dict("src.scoring.model_registry.MODELS", {"v2": str(fake_pkl)}),
        ):
            set_active_model("v2")
            assert get_active_version() == "v2"


# ---------------------------------------------------------------------------
# MODELS dict invariants
# ---------------------------------------------------------------------------

class TestModelsDict:
    def test_v1_and_v2_exist(self):
        assert "v1" in MODELS and "v2" in MODELS

    def test_values_are_strings(self):
        for v, path in MODELS.items():
            assert isinstance(path, str), f"MODELS['{v}'] should be a str"

    def test_v1_points_to_lgbm_pkl(self):
        assert "lead_scorer_lgbm.pkl" in MODELS["v1"]

    def test_v2_points_to_lgbm_v2_pkl(self):
        assert "lead_scorer_lgbm_v2.pkl" in MODELS["v2"]


# ---------------------------------------------------------------------------
# MLScorer registry integration (without loading a real model)
# ---------------------------------------------------------------------------

class TestMLScorerRegistryIntegration:
    def _mock_joblib(self, mock_model):
        """Patch joblib.load to return a fake model object."""
        import unittest.mock
        return patch("joblib.load", return_value=mock_model)

    def test_default_constructor_uses_active_model(self, tmp_path):
        from unittest.mock import MagicMock
        from src.scoring.ml_scorer import MLScorer

        fake_model = MagicMock()
        fake_model.predict_proba.return_value = [[0.8, 0.2]]

        with (
            _patch_active_file(tmp_path, "v1\n"),
            self._mock_joblib(fake_model),
        ):
            scorer = MLScorer()
            assert scorer.model_version == "lgbm_v1"

    def test_model_version_kwarg_sets_correct_tag(self, tmp_path):
        from unittest.mock import MagicMock
        from src.scoring.ml_scorer import MLScorer

        fake_model = MagicMock()

        with (
            _patch_active_file(tmp_path, "v1\n"),
            self._mock_joblib(fake_model),
        ):
            scorer = MLScorer(model_version="v2")
            assert scorer.model_version == "lgbm_v2"

    def test_explicit_path_preserves_legacy_version_tag(self, tmp_path):
        from unittest.mock import MagicMock
        from src.scoring.ml_scorer import MLScorer, MODEL_VERSION

        fake_model = MagicMock()

        with self._mock_joblib(fake_model):
            scorer = MLScorer(model_path="models/custom.pkl")
            assert scorer.model_version == MODEL_VERSION

    def test_unknown_model_version_raises(self):
        from src.scoring.ml_scorer import MLScorer
        with pytest.raises(ValueError, match="Unknown model version"):
            MLScorer(model_version="v99")
