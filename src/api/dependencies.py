"""
Shared FastAPI dependencies — Phase 19.

All heavy resources (ClickHouse client, CTGAN synthesizer, MLScorer) are
module-level singletons initialized once at startup via the FastAPI lifespan.
This avoids the 6 MB pkl deserialization cost on every request.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (read from environment — overridable in Docker Compose)
# ---------------------------------------------------------------------------

CLICKHOUSE_HOST     = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT     = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DATABASE = os.getenv("CLICKHOUSE_DATABASE", "analytics")
CLICKHOUSE_USER     = os.getenv("CLICKHOUSE_USER", "analytics")
CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "analytics_password")

CTGAN_MODEL_PATH = Path(
    os.getenv("CTGAN_MODEL_PATH", "models/ctgan_sessions.pkl")
)

# ---------------------------------------------------------------------------
# Module-level singletons (set by lifespan, read by endpoints)
# ---------------------------------------------------------------------------

_ch_client = None
_synthesizer = None
_scorer = None


def get_ch_client():
    """Return the shared ClickHouse client (initialized at startup)."""
    if _ch_client is None:
        raise RuntimeError("ClickHouse client not initialized — check lifespan startup.")
    return _ch_client


def get_synthesizer():
    """Return the cached CTGAN synthesizer (initialized at startup)."""
    if _synthesizer is None:
        raise RuntimeError("CTGAN synthesizer not initialized — check lifespan startup.")
    return _synthesizer


def get_scorer():
    """Return the cached MLScorer (initialized at startup)."""
    if _scorer is None:
        raise RuntimeError("MLScorer not initialized — check lifespan startup.")
    return _scorer


# ---------------------------------------------------------------------------
# Initialization helpers called from lifespan
# ---------------------------------------------------------------------------

def init_ch_client():
    global _ch_client
    import clickhouse_connect
    _ch_client = clickhouse_connect.get_client(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        database=CLICKHOUSE_DATABASE,
        username=CLICKHOUSE_USER,
        password=CLICKHOUSE_PASSWORD,
    )
    log.info("ClickHouse client connected to %s:%s", CLICKHOUSE_HOST, CLICKHOUSE_PORT)


def init_synthesizer():
    global _synthesizer
    import joblib
    if not CTGAN_MODEL_PATH.exists():
        log.warning(
            "CTGAN model not found at %s — predictions will fail until the model "
            "is available. Run 'make ctgan-train' to build it.",
            CTGAN_MODEL_PATH,
        )
        return
    _synthesizer = joblib.load(CTGAN_MODEL_PATH)
    log.info("CTGAN synthesizer loaded from %s", CTGAN_MODEL_PATH)


def init_scorer():
    global _scorer
    from src.scoring.ml_scorer import MLScorer
    try:
        _scorer = MLScorer()
        log.info("MLScorer loaded (model_version=%s)", _scorer.model_version)
    except FileNotFoundError as exc:
        log.warning(
            "MLScorer model not found (%s) — heuristic fallback will be used.", exc
        )
