"""
Synthetic session generator — Phase 13.

Loads a trained SDV CTGANSynthesizer from disk, samples N sessions (optionally
conditioned on a specific category), applies the Phase 11 MLScorer to tag each
row with ml_lead_score / ml_score_tier, and inserts the result into
analytics.synthetic_sessions.

Usage:
    python scripts/generate_synthetic_sessions.py [--n-sessions 10000]
                                                  [--category-filter 213]
                                                  [--overwrite]
                                                  [--model models/ctgan_sessions.pkl]
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
import logging
import os
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scoring.ml_scorer import MLScorer, _FEATURE_COLS

log = logging.getLogger(__name__)

# Batch size for ClickHouse INSERTs (matches score_sessions.py convention).
_INSERT_BATCH = 10_000

# Columns written to analytics.synthetic_sessions in insertion order.
_TARGET_COLS = [
    "session_id",
    "anonymous_user_id",
    "page_views",
    "product_views",
    "add_to_cart_count",
    "purchase_count",
    "search_count",
    "max_scroll_pct",
    "session_duration_seconds",
    "distinct_products_viewed",
    "cart_abandoned",
    "primary_category",
    "source",
    "is_synthetic",
    "ml_lead_score",
    "ml_score_tier",
]


# ---------------------------------------------------------------------------
# ClickHouse helpers
# ---------------------------------------------------------------------------

def _ch_client():
    try:
        import clickhouse_connect
    except ImportError as exc:
        raise ImportError(
            "clickhouse-connect is required. "
            "Install it with: pip install -r requirements-synth.txt"
        ) from exc

    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        username=os.getenv("CLICKHOUSE_USER", "analytics"),
        password=os.getenv("CLICKHOUSE_PASSWORD", "analytics_password"),
        database=os.getenv("CLICKHOUSE_DATABASE", "analytics"),
    )


def _truncate_table(client) -> None:
    client.command("TRUNCATE TABLE IF EXISTS analytics.synthetic_sessions")
    log.info("analytics.synthetic_sessions truncated.")


def _insert_batch(client, batch: pd.DataFrame) -> None:
    rows = [
        (
            str(row["session_id"]),
            str(row["anonymous_user_id"]),
            int(row["page_views"]),
            int(row["product_views"]),
            int(row["add_to_cart_count"]),
            int(row["purchase_count"]),
            int(row["search_count"]),
            float(row["max_scroll_pct"]) if pd.notna(row["max_scroll_pct"]) else None,
            int(row["session_duration_seconds"]),
            int(row["distinct_products_viewed"]),
            int(row["cart_abandoned"]),
            str(row.get("primary_category", "")),
            "synthetic",
            1,
            float(row["ml_lead_score"]) if pd.notna(row.get("ml_lead_score")) else None,
            str(row.get("ml_score_tier", "")),
        )
        for _, row in batch.iterrows()
    ]
    client.insert(
        "analytics.synthetic_sessions",
        rows,
        column_names=_TARGET_COLS,
    )


# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------

def _load_synthesizer(model_path: Path):
    try:
        import joblib
    except ImportError as exc:
        raise ImportError(
            "joblib is required. Install with: pip install -r requirements-synth.txt"
        ) from exc

    if not model_path.exists():
        raise FileNotFoundError(
            f"CTGAN model not found at {model_path}. "
            "Run 'make ctgan-train' to train the model first."
        )
    log.info("Loading CTGAN synthesizer from %s …", model_path)
    return joblib.load(model_path)


def _sample(synthesizer, n_sessions: int, category_filter: str | None) -> pd.DataFrame:
    if category_filter:
        log.info("Conditional sampling: n=%d, category=%s", n_sessions, category_filter)
        try:
            from sdv.sampling import Condition
            condition = Condition(
                num_rows=n_sessions,
                column_values={"primary_category": category_filter},
            )
            df = synthesizer.sample_from_conditions(conditions=[condition])
            if df.empty:
                log.warning(
                    "Conditional sampling for category '%s' returned 0 rows. "
                    "Falling back to unconditional sampling.",
                    category_filter,
                )
                df = synthesizer.sample(num_rows=n_sessions)
                df["primary_category"] = ""
        except Exception as exc:
            log.warning(
                "Conditional sampling failed (%s). Falling back to unconditional.", exc
            )
            df = synthesizer.sample(num_rows=n_sessions)
            df["primary_category"] = df.get("primary_category", "")
    else:
        log.info("Unconditional sampling: n=%d", n_sessions)
        df = synthesizer.sample(num_rows=n_sessions)

    return df


def _coerce_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enforce integer/float types that CTGAN may have relaxed during generation.
    Also fills in derived columns that callers expect downstream.
    """
    int_cols = [
        "page_views", "product_views", "add_to_cart_count", "purchase_count",
        "search_count", "session_duration_seconds", "distinct_products_viewed",
    ]
    for col in int_cols:
        if col in df.columns:
            df[col] = df[col].round().clip(lower=0).astype("int64")

    if "cart_abandoned" in df.columns:
        df["cart_abandoned"] = df["cart_abandoned"].round().clip(0, 1).astype("int8")
    else:
        # Derive: add_to_cart but no purchase
        df["cart_abandoned"] = (
            (df["add_to_cart_count"] > 0) & (df["purchase_count"] == 0)
        ).astype("int8")

    if "max_scroll_pct" in df.columns:
        df["max_scroll_pct"] = df["max_scroll_pct"].clip(lower=0.0, upper=100.0)
        # Preserve NaN — LightGBM handles it natively
    else:
        df["max_scroll_pct"] = None

    if "primary_category" not in df.columns:
        df["primary_category"] = ""

    return df


def _assign_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Assign synthetic session_id and anonymous_user_id."""
    import uuid
    n = len(df)
    df["session_id"] = [f"syn_{uuid.uuid4().hex[:12]}" for _ in range(n)]
    df["anonymous_user_id"] = [f"syn_user_{uuid.uuid4().hex[:8]}" for _ in range(n)]
    return df


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def generate_synthetic_sessions(
    model_path: Path,
    n_sessions: int,
    category_filter: str | None,
    overwrite: bool,
    dry_run: bool,
) -> None:
    t0 = time.time()

    synthesizer = _load_synthesizer(model_path)

    log.info("Sampling %d synthetic sessions …", n_sessions)
    df = _sample(synthesizer, n_sessions, category_filter)
    df = _coerce_dtypes(df)
    df = _assign_ids(df)

    # Score with MLScorer so downstream consumers don't need to re-score.
    log.info("Scoring with MLScorer …")
    try:
        scorer = MLScorer()
        df["ml_lead_score"] = scorer.predict(df)
        df["ml_score_tier"] = scorer.score_tier(df["ml_lead_score"] * 100)
    except FileNotFoundError:
        log.warning(
            "ML model not found — ml_lead_score will be NULL. "
            "Run 'make score-sessions' after 'make ml-setup' to populate scores."
        )
        df["ml_lead_score"] = None
        df["ml_score_tier"] = ""

    # Report tier distribution before writing.
    if "ml_score_tier" in df.columns and df["ml_score_tier"].notna().any():
        tier_dist = df["ml_score_tier"].value_counts().to_dict()
        log.info("Tier distribution: %s", tier_dist)
    else:
        log.info("Tier distribution: (scores unavailable)")

    if dry_run:
        log.info("[dry-run] Sample rows (first 5):")
        print(df[["session_id", "product_views", "add_to_cart_count", "ml_lead_score",
                   "ml_score_tier", "primary_category"]].head(5).to_string(index=False))
        log.info("[dry-run] Would insert %d rows into analytics.synthetic_sessions.", len(df))
        return

    client = _ch_client()

    if overwrite:
        log.info("--overwrite: truncating analytics.synthetic_sessions …")
        _truncate_table(client)

    total = len(df)
    inserted = 0
    for start in range(0, total, _INSERT_BATCH):
        batch = df.iloc[start : start + _INSERT_BATCH]
        _insert_batch(client, batch)
        inserted += len(batch)
        print(f"  Inserted {inserted:,}/{total:,} rows …", end="\r")

    elapsed = round(time.time() - t0, 2)
    print()
    log.info(
        "Done. %d rows written to analytics.synthetic_sessions in %.2fs.",
        inserted, elapsed,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate synthetic e-commerce sessions using a trained CTGAN model."
    )
    parser.add_argument(
        "--n-sessions",
        type=int,
        default=10_000,
        help="Number of synthetic sessions to generate (default: 10000).",
    )
    parser.add_argument(
        "--category-filter",
        type=str,
        default=None,
        help="Condition sampling on this category value (string, e.g. '213'). "
             "Omit for unconditional sampling.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Truncate analytics.synthetic_sessions before inserting. "
             "Without this flag, rows are appended.",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("models/ctgan_sessions.pkl"),
        help="Path to trained CTGANSynthesizer (joblib). Default: models/ctgan_sessions.pkl",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Sample and score but do not write to ClickHouse.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args()
    generate_synthetic_sessions(
        model_path=args.model,
        n_sessions=args.n_sessions,
        category_filter=args.category_filter,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log.info("Interrupted.")
        sys.exit(1)
    except Exception as exc:
        log.exception("Generation failed: %s", exc)
        sys.exit(1)
