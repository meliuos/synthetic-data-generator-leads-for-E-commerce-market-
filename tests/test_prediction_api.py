"""
Unit tests for Phase 19 — Prediction REST API.

Uses FastAPI TestClient and mocks all heavy dependencies (CTGAN, LightGBM,
ClickHouse) so tests run in < 1 second without any external services.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Build a fake PredictionResult that matches the real dataclass interface
# ---------------------------------------------------------------------------

@dataclass
class _FakeResult:
    conversion_rate_pct: float = 35.0
    tier_distribution: dict = field(default_factory=lambda: {"hot": 350, "warm": 150, "cold": 500})
    tier_distribution_pct: dict = field(default_factory=lambda: {"hot": 35.0, "warm": 15.0, "cold": 50.0})
    top_features: list = field(default_factory=lambda: [
        {"name": "session_duration_seconds", "importance": 0.41},
        {"name": "product_views", "importance": 0.24},
    ])
    sample_sessions: object = field(default_factory=lambda: pd.DataFrame({
        "session_id": ["pred_abc123"],
        "score_tier": ["hot"],
        "ml_lead_score": [0.72],
        "product_views": [5],
        "add_to_cart_count": [2],
        "cart_abandoned": [0],
    }))
    used_conditional: bool = True
    category: str = "1051"
    n_sessions_sampled: int = 1000


# ---------------------------------------------------------------------------
# App fixture — patches dep singletons before TestClient loads the app
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    fake_ch = MagicMock()
    fake_ch.query.return_value = MagicMock(result_rows=[], column_names=[])

    with (
        # No-op the lifespan init functions so no real models are loaded
        patch("src.api.dependencies.init_ch_client"),
        patch("src.api.dependencies.init_synthesizer"),
        patch("src.api.dependencies.init_scorer"),
        # Stub the getters so endpoints receive usable mocks
        patch("src.api.dependencies.get_ch_client", return_value=fake_ch),
        patch("src.api.dependencies.get_synthesizer", return_value=MagicMock()),
        patch("src.api.dependencies.get_scorer", return_value=MagicMock()),
        # Stub the heavy prediction call and model registry
        patch(
            "src.prediction.product_predictor.predict_for_product",
            return_value=_FakeResult(),
        ),
        patch(
            "src.scoring.model_registry.get_active_version",
            return_value="v1",
        ),
    ):
        from src.api.main import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_body_has_required_fields(self, client):
        body = client.get("/health").json()
        assert "status" in body
        assert "active_model" in body
        assert "clickhouse" in body

    def test_status_is_ok(self, client):
        assert client.get("/health").json()["status"] == "ok"

    def test_clickhouse_ok_when_query_succeeds(self, client):
        assert client.get("/health").json()["clickhouse"] == "ok"


# ---------------------------------------------------------------------------
# GET /models/active
# ---------------------------------------------------------------------------

class TestModelsActive:
    def test_returns_200(self, client):
        assert client.get("/models/active").status_code == 200

    def test_version_field_present(self, client):
        body = client.get("/models/active").json()
        assert "version" in body and "path" in body


# ---------------------------------------------------------------------------
# POST /predict/product — happy path
# ---------------------------------------------------------------------------

class TestPredictProduct:
    _PAYLOAD = {
        "product_name": "Wireless Headphones",
        "category": "1051",
        "price": 49.99,
        "keywords": "audio,bluetooth",
        "n_sessions": 1000,
    }

    def test_returns_200(self, client):
        r = client.post("/predict/product", json=self._PAYLOAD)
        assert r.status_code == 200, r.text

    def test_response_has_conversion_rate(self, client):
        body = client.post("/predict/product", json=self._PAYLOAD).json()
        assert "conversion_rate_pct" in body
        assert isinstance(body["conversion_rate_pct"], float)

    def test_response_has_tier_distribution(self, client):
        body = client.post("/predict/product", json=self._PAYLOAD).json()
        td = body["tier_distribution"]
        assert set(td.keys()) == {"hot", "warm", "cold"}

    def test_response_has_top_features(self, client):
        body = client.post("/predict/product", json=self._PAYLOAD).json()
        assert isinstance(body["top_features"], list)
        assert len(body["top_features"]) > 0

    def test_response_has_sample_sessions(self, client):
        body = client.post("/predict/product", json=self._PAYLOAD).json()
        assert isinstance(body["sample_sessions"], list)

    def test_response_has_model_version(self, client):
        body = client.post("/predict/product", json=self._PAYLOAD).json()
        assert "model_version" in body
        assert body["model_version"].startswith("lgbm_")

    def test_predicted_at_is_iso_string(self, client):
        body = client.post("/predict/product", json=self._PAYLOAD).json()
        assert "predicted_at" in body
        datetime.fromisoformat(body["predicted_at"].replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# POST /predict/product — validation errors
# ---------------------------------------------------------------------------

class TestPredictValidation:
    def test_empty_product_name_returns_422(self, client):
        r = client.post("/predict/product", json={
            "product_name": "",
            "category": "1051",
            "price": 10.0,
        })
        assert r.status_code == 422

    def test_empty_category_returns_422(self, client):
        r = client.post("/predict/product", json={
            "product_name": "Test",
            "category": "",
            "price": 10.0,
        })
        assert r.status_code == 422

    def test_zero_price_returns_422(self, client):
        r = client.post("/predict/product", json={
            "product_name": "Test",
            "category": "1051",
            "price": 0.0,
        })
        assert r.status_code == 422

    def test_negative_price_returns_422(self, client):
        r = client.post("/predict/product", json={
            "product_name": "Test",
            "category": "1051",
            "price": -5.0,
        })
        assert r.status_code == 422

    def test_n_sessions_below_100_returns_422(self, client):
        r = client.post("/predict/product", json={
            "product_name": "Test",
            "category": "1051",
            "price": 10.0,
            "n_sessions": 50,
        })
        assert r.status_code == 422

    def test_n_sessions_above_5000_returns_422(self, client):
        r = client.post("/predict/product", json={
            "product_name": "Test",
            "category": "1051",
            "price": 10.0,
            "n_sessions": 9999,
        })
        assert r.status_code == 422

    def test_missing_required_fields_returns_422(self, client):
        r = client.post("/predict/product", json={"price": 10.0})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# POST /predict/product — predictor failures
# ---------------------------------------------------------------------------

class TestPredictErrors:
    def test_model_not_found_returns_503(self, client):
        with patch(
            "src.prediction.product_predictor.predict_for_product",
            side_effect=FileNotFoundError("model not found"),
        ):
            r = client.post("/predict/product", json={
                "product_name": "Test",
                "category": "1051",
                "price": 10.0,
            })
        assert r.status_code == 503

    def test_unexpected_error_returns_500(self, client):
        with patch(
            "src.prediction.product_predictor.predict_for_product",
            side_effect=RuntimeError("unexpected"),
        ):
            r = client.post("/predict/product", json={
                "product_name": "Test",
                "category": "1051",
                "price": 10.0,
            })
        assert r.status_code == 500


# ---------------------------------------------------------------------------
# GET /predictions/history
# ---------------------------------------------------------------------------

class TestPredictionsHistory:
    def test_returns_200(self, client):
        assert client.get("/predictions/history").status_code == 200

    def test_returns_list(self, client):
        assert isinstance(client.get("/predictions/history").json(), list)

    def test_limit_param_accepted(self, client):
        assert client.get("/predictions/history?limit=5").status_code == 200

    def test_limit_above_100_returns_422(self, client):
        assert client.get("/predictions/history?limit=999").status_code == 422
