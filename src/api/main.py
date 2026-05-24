"""
Prediction REST API — Phase 19.

Exposes the Phase 17 product prediction pipeline as a standalone FastAPI
service, decoupling ML inference from the Streamlit dashboard process.

Endpoints:
    POST /predict/product       — CTGAN sampling + ML scoring
    GET  /health                — liveness + ClickHouse probe
    GET  /predictions/history   — last N rows from analytics.prediction_log
    GET  /models/active         — currently active model version

Run locally (outside Docker):
    uvicorn src.api.main:app --reload --port 8000

Environment variables:
    CLICKHOUSE_HOST / PORT / DATABASE / USER / PASSWORD
    CTGAN_MODEL_PATH   (default: models/ctgan_sessions.pkl)
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

# Ensure repo root is on sys.path when run from any working directory.
_REPO_ROOT = Path(__file__).parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.api import dependencies as dep
from src.api.schemas import (
    ActiveModelResponse,
    FeatureImportance,
    HealthResponse,
    PredictionHistoryItem,
    ProductPredictRequest,
    ProductPredictResponse,
    TierCounts,
    TierPct,
)
from src.scoring.model_registry import MODELS, get_active_model_path, get_active_version

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan — load heavy resources once at startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log.info("API starting — loading models and ClickHouse client …")
    dep.init_ch_client()
    dep.init_synthesizer()
    dep.init_scorer()
    log.info("Startup complete.")
    yield
    log.info("API shutting down.")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Lead Intelligence — Prediction API",
    description=(
        "Product lead conversion prediction powered by CTGAN synthetic session "
        "sampling and a LightGBM ML scorer."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_prediction(
    client,
    product_name: str,
    category: str,
    price: float,
    keywords: str,
    result,
) -> None:
    try:
        client.insert(
            "analytics.prediction_log",
            [[
                product_name,
                category,
                float(price),
                keywords,
                result.n_sessions_sampled,
                result.conversion_rate_pct,
                result.tier_distribution_pct.get("hot", 0.0),
                result.tier_distribution_pct.get("warm", 0.0),
                result.tier_distribution_pct.get("cold", 0.0),
                int(result.used_conditional),
            ]],
            column_names=[
                "product_name", "category", "price", "keywords",
                "n_sessions_sampled", "conversion_rate_pct",
                "tier_hot_pct", "tier_warm_pct", "tier_cold_pct",
                "used_conditional",
            ],
        )
    except Exception as exc:
        log.warning("Failed to log prediction to ClickHouse: %s", exc)


def _sessions_to_records(sample_sessions) -> list[dict[str, Any]]:
    """Convert PredictionResult.sample_sessions DataFrame to JSON-safe records."""
    try:
        df = sample_sessions.copy()
        if "ml_lead_score" in df.columns:
            df["ml_lead_score"] = df["ml_lead_score"].astype(float).round(4)
        return df.to_dict(orient="records")
    except Exception:
        return []


# ---------------------------------------------------------------------------
# POST /predict/product
# ---------------------------------------------------------------------------

@app.post(
    "/predict/product",
    response_model=ProductPredictResponse,
    summary="Predict lead conversion likelihood for a product.",
)
def predict_product(body: ProductPredictRequest) -> ProductPredictResponse:
    """
    Sample N synthetic sessions from CTGAN conditioned on *category*, score them
    with the active LightGBM model, and return tier distribution + feature
    importances. Every successful call writes one row to analytics.prediction_log.
    """
    from src.prediction.product_predictor import predict_for_product

    log.info(
        "Prediction request: product='%s' category=%s price=%.2f n=%d",
        body.product_name, body.category, body.price, body.n_sessions,
    )

    try:
        result = predict_for_product(
            category=body.category,
            price=body.price,
            keywords=body.keywords,
            n_sessions=body.n_sessions,
            model_path=dep.CTGAN_MODEL_PATH,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        log.exception("Prediction failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Prediction failed: {exc}")

    _log_prediction(
        dep.get_ch_client(),
        body.product_name,
        body.category,
        body.price,
        body.keywords,
        result,
    )

    return ProductPredictResponse(
        product_name=body.product_name,
        category=result.category,
        price=body.price,
        n_sessions_sampled=result.n_sessions_sampled,
        used_conditional_sampling=result.used_conditional,
        conversion_rate_pct=result.conversion_rate_pct,
        tier_distribution=TierCounts(
            hot=result.tier_distribution.get("hot", 0),
            warm=result.tier_distribution.get("warm", 0),
            cold=result.tier_distribution.get("cold", 0),
        ),
        tier_distribution_pct=TierPct(
            hot=result.tier_distribution_pct.get("hot", 0.0),
            warm=result.tier_distribution_pct.get("warm", 0.0),
            cold=result.tier_distribution_pct.get("cold", 0.0),
        ),
        top_features=[
            FeatureImportance(name=f["name"], importance=f["importance"])
            for f in result.top_features
        ],
        sample_sessions=_sessions_to_records(result.sample_sessions),
        model_version=f"lgbm_{get_active_version()}",
        predicted_at=datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Service liveness + dependency probe.",
)
def health() -> HealthResponse:
    ch_status = "ok"
    try:
        dep.get_ch_client().query("SELECT 1")
    except Exception as exc:
        log.warning("ClickHouse health check failed: %s", exc)
        ch_status = "error"

    return HealthResponse(
        status="ok",
        active_model=get_active_version(),
        clickhouse=ch_status,
    )


# ---------------------------------------------------------------------------
# GET /predictions/history
# ---------------------------------------------------------------------------

@app.get(
    "/predictions/history",
    response_model=list[PredictionHistoryItem],
    summary="Retrieve recent predictions from analytics.prediction_log.",
)
def predictions_history(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[PredictionHistoryItem]:
    try:
        result = dep.get_ch_client().query(
            """
            SELECT
                product_name,
                category,
                price,
                n_sessions_sampled,
                conversion_rate_pct,
                tier_hot_pct,
                tier_warm_pct,
                tier_cold_pct,
                used_conditional,
                predicted_at
            FROM analytics.prediction_log
            ORDER BY predicted_at DESC
            LIMIT {limit:UInt32}
            """,
            parameters={"limit": limit},
        )
    except Exception as exc:
        log.error("Failed to query prediction_log: %s", exc)
        raise HTTPException(status_code=503, detail=f"ClickHouse query failed: {exc}")

    return [
        PredictionHistoryItem(
            product_name=row[0],
            category=row[1],
            price=row[2],
            n_sessions_sampled=row[3],
            conversion_rate_pct=row[4],
            tier_hot_pct=row[5],
            tier_warm_pct=row[6],
            tier_cold_pct=row[7],
            used_conditional=row[8],
            predicted_at=row[9],
        )
        for row in result.result_rows
    ]


# ---------------------------------------------------------------------------
# GET /models/active
# ---------------------------------------------------------------------------

@app.get(
    "/models/active",
    response_model=ActiveModelResponse,
    summary="Return the currently active model version.",
)
def models_active() -> ActiveModelResponse:
    version = get_active_version()
    return ActiveModelResponse(version=version, path=MODELS[version])
