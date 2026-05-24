"""
Pydantic request/response schemas — Phase 19.

All models use Pydantic v2 style. Field validators enforce the same
constraints as the Phase 17 Streamlit form (price > 0, n_sessions 100–5000).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class ProductPredictRequest(BaseModel):
    product_name: str = Field(..., min_length=1, description="Human-readable product name.")
    category: str = Field(..., min_length=1, description="Category ID (e.g. '1051').")
    price: float = Field(..., gt=0, description="Product price in local currency.")
    keywords: str = Field(default="", description="Comma-separated product keywords.")
    n_sessions: int = Field(
        default=1000,
        ge=100,
        le=5000,
        description="Synthetic sessions to sample (100–5000).",
    )

    @field_validator("category")
    @classmethod
    def category_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("category must not be blank")
        return v.strip()

    @field_validator("product_name")
    @classmethod
    def product_name_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("product_name must not be blank")
        return v.strip()


# ---------------------------------------------------------------------------
# Nested response models
# ---------------------------------------------------------------------------

class TierCounts(BaseModel):
    hot: int
    warm: int
    cold: int


class TierPct(BaseModel):
    hot: float
    warm: float
    cold: float


class FeatureImportance(BaseModel):
    name: str
    importance: float


class SessionRow(BaseModel):
    session_id: str
    score_tier: str
    ml_lead_score: float
    product_views: int | None = None
    add_to_cart_count: int | None = None
    cart_abandoned: int | None = None


# ---------------------------------------------------------------------------
# Primary response
# ---------------------------------------------------------------------------

class ProductPredictResponse(BaseModel):
    product_name: str
    category: str
    price: float
    n_sessions_sampled: int
    used_conditional_sampling: bool
    conversion_rate_pct: float
    tier_distribution: TierCounts
    tier_distribution_pct: TierPct
    top_features: list[FeatureImportance]
    sample_sessions: list[dict[str, Any]]
    model_version: str
    predicted_at: datetime


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

class PredictionHistoryItem(BaseModel):
    product_name: str
    category: str
    price: float
    n_sessions_sampled: int
    conversion_rate_pct: float
    tier_hot_pct: float
    tier_warm_pct: float
    tier_cold_pct: float
    used_conditional: int
    predicted_at: datetime


# ---------------------------------------------------------------------------
# Health / model info
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    active_model: str
    clickhouse: str


class ActiveModelResponse(BaseModel):
    version: str
    path: str
