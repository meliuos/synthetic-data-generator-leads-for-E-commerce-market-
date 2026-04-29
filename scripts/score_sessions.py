"""
Batch ML lead scoring — Phase 11.

Pulls all sessions from analytics.session_features, scores them with the
trained LightGBM model, and writes results to analytics.lead_scores_ml.

Usage:
    python scripts/score_sessions.py [--model models/lead_scorer_lgbm.pkl]
                                     [--source live|retailrocket|all]
                                     [--batch-size 10000]
                                     [--dry-run]

Environment variables (override docker-compose defaults):
    CLICKHOUSE_HOST      default: localhost
    CLICKHOUSE_PORT      default: 8123
    CLICKHOUSE_USER      default: analytics
    CLICKHOUSE_PASSWORD  default: analytics_password
    CLICKHOUSE_DATABASE  default: analytics
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

# Ensure src/ is importable when run from repo root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scoring.ml_scorer import MODEL_VERSION, MLScorer

# ---------------------------------------------------------------------------
# ClickHouse connection helpers
# ---------------------------------------------------------------------------

def _ch_client():
    try:
        import clickhouse_connect
    except ImportError as exc:
        raise ImportError(
            "clickhouse-connect is required. "
            "Install it with: pip install -r requirements-ml.txt"
        ) from exc

    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        username=os.getenv("CLICKHOUSE_USER", "analytics"),
        password=os.getenv("CLICKHOUSE_PASSWORD", "analytics_password"),
        database=os.getenv("CLICKHOUSE_DATABASE", "analytics"),
    )


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

_SELECT_FEATURES = """
SELECT
    session_id,
    anonymous_user_id,
    source,
    product_views,
    add_to_cart_count,
    distinct_products_viewed,
    max_scroll_pct,
    search_count,
    session_duration_seconds
FROM analytics.session_features
{where_clause}
"""

_INSERT_SCORES = """
INSERT INTO analytics.lead_scores_ml
    (session_id, anonymous_user_id, source, ml_lead_score, model_version)
VALUES
"""


def _fetch_sessions(client, source: str) -> pd.DataFrame:
    where = "" if source == "all" else f"WHERE source = '{source}'"
    result = client.query(_SELECT_FEATURES.format(where_clause=where))
    df = pd.DataFrame(result.result_rows, columns=result.column_names)
    # max_scroll_pct arrives as float or None; convert None → NaN for LightGBM
    df["max_scroll_pct"] = pd.to_numeric(df["max_scroll_pct"], errors="coerce")
    return df


def _insert_batch(client, batch: pd.DataFrame, model_version: str) -> None:
    rows = [
        (
            row["session_id"],
            row["anonymous_user_id"],
            row["source"],
            float(row["ml_lead_score"]),
            model_version,
        )
        for _, row in batch.iterrows()
    ]
    client.insert(
        "analytics.lead_scores_ml",
        rows,
        column_names=["session_id", "anonymous_user_id", "source", "ml_lead_score", "model_version"],
    )


def score_sessions(
    model_path: Path,
    source: str,
    batch_size: int,
    dry_run: bool,
) -> None:
    print(f"Loading model from {model_path} …")
    scorer = MLScorer(model_path)

    print("Connecting to ClickHouse …")
    client = _ch_client()

    print(f"Fetching sessions (source={source}) …")
    df = _fetch_sessions(client, source)
    print(f"  {len(df):,} sessions loaded.")

    print("Scoring …")
    df["ml_lead_score"] = scorer.predict(df)

    if dry_run:
        print("[dry-run] Sample scores (first 10 rows):")
        cols = ["session_id", "source", "ml_lead_score"]
        print(df[cols].head(10).to_string(index=False))
        print(f"[dry-run] Would insert {len(df):,} rows into analytics.lead_scores_ml.")
        return

    total = len(df)
    inserted = 0
    for start in range(0, total, batch_size):
        batch = df.iloc[start : start + batch_size]
        _insert_batch(client, batch, scorer.model_version)
        inserted += len(batch)
        print(f"  Inserted {inserted:,}/{total:,} rows …", end="\r")

    print(f"\nDone. {inserted:,} rows written to analytics.lead_scores_ml.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch ML lead scorer.")
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("models/lead_scorer_lgbm.pkl"),
        help="Path to trained LightGBM model (joblib).",
    )
    parser.add_argument(
        "--source",
        choices=["live", "retailrocket", "all"],
        default="all",
        help="Which session source to score (default: all).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10_000,
        help="Rows per ClickHouse INSERT (default: 10000).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and score but do not write to ClickHouse.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    score_sessions(
        model_path=args.model,
        source=args.source,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
    )
