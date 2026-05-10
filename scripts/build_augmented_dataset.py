"""
Augmented dataset builder — Phase 18.

Exports real Retailrocket sessions and CTGAN-generated synthetic sessions
from ClickHouse, aligns their schemas to the MLScorer feature set, labels
each row (converted = 1 if purchase_count > 0), and produces a stratified
80/20 train/test split saved as Parquet files.

Usage:
    python scripts/build_augmented_dataset.py [--output-dir data]
                                              [--real-limit 0]
                                              [--synth-limit 0]
                                              [--test-size 0.2]
                                              [--seed 42]
                                              [--dry-run]

Outputs:
    data/augmented_training.parquet
    data/augmented_test.parquet

Environment variables:
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
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scoring.ml_scorer import _FEATURE_COLS

log = logging.getLogger(__name__)

# Columns fetched from ClickHouse — feature set + labelling signal + provenance.
_REAL_COLS = _FEATURE_COLS + ["purchase_count", "session_id"]
_SYNTH_COLS = _FEATURE_COLS + ["purchase_count", "session_id", "is_synthetic"]

# ---------------------------------------------------------------------------
# ClickHouse helpers
# ---------------------------------------------------------------------------

def _ch_client():
    try:
        import clickhouse_connect
    except ImportError as exc:
        raise ImportError(
            "clickhouse-connect is required. "
            "Install with: pip install -r requirements-ml.txt"
        ) from exc

    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        username=os.getenv("CLICKHOUSE_USER", "analytics"),
        password=os.getenv("CLICKHOUSE_PASSWORD", "analytics_password"),
        database=os.getenv("CLICKHOUSE_DATABASE", "analytics"),
    )


def _fetch_real_sessions(client, limit: int) -> pd.DataFrame:
    """
    Export Retailrocket sessions from analytics.session_features.

    max_scroll_pct is NULL for Retailrocket — preserved as NaN so LightGBM
    can distinguish genuine absence from a zero-scroll session.
    """
    limit_clause = f"LIMIT {limit}" if limit > 0 else ""
    query = f"""
        SELECT
            session_id,
            product_views,
            add_to_cart_count,
            distinct_products_viewed,
            max_scroll_pct,
            search_count,
            session_duration_seconds,
            purchase_count
        FROM analytics.session_features
        WHERE source = 'retailrocket'
        {limit_clause}
    """
    result = client.query(query)
    df = pd.DataFrame(result.result_rows, columns=result.column_names)
    df["max_scroll_pct"] = pd.to_numeric(df["max_scroll_pct"], errors="coerce")
    df["is_synthetic"] = 0
    return df


def _fetch_synthetic_sessions(client, limit: int) -> pd.DataFrame:
    """
    Export CTGAN-generated sessions from analytics.synthetic_sessions.

    Rows without a purchase_count column default to 0 (synthetic rows are
    scored but not necessarily labeled during generation).
    """
    limit_clause = f"LIMIT {limit}" if limit > 0 else ""
    query = f"""
        SELECT
            session_id,
            product_views,
            add_to_cart_count,
            distinct_products_viewed,
            max_scroll_pct,
            search_count,
            session_duration_seconds,
            purchase_count,
            is_synthetic
        FROM analytics.synthetic_sessions
        {limit_clause}
    """
    result = client.query(query)
    df = pd.DataFrame(result.result_rows, columns=result.column_names)
    df["max_scroll_pct"] = pd.to_numeric(df["max_scroll_pct"], errors="coerce")
    return df


# ---------------------------------------------------------------------------
# Feature alignment
# ---------------------------------------------------------------------------

def _align_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure all _FEATURE_COLS exist with correct numeric dtypes.

    Missing columns are added as NaN (LightGBM handles missing natively).
    Extra columns beyond _FEATURE_COLS + ['purchase_count', 'session_id',
    'is_synthetic', 'converted'] are dropped to keep Parquet lean.
    """
    for col in _FEATURE_COLS:
        if col not in df.columns:
            log.warning("Column '%s' missing from DataFrame — filling with NaN", col)
            df[col] = float("nan")

    # Clip integer columns to non-negative — CTGAN may produce tiny negatives.
    int_cols = [
        c for c in _FEATURE_COLS
        if c != "max_scroll_pct" and c in df.columns
    ]
    for col in int_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce").clip(lower=0)

    if "max_scroll_pct" in df.columns:
        df["max_scroll_pct"] = df["max_scroll_pct"].clip(0.0, 100.0)

    keep = _FEATURE_COLS + [
        c for c in ["purchase_count", "session_id", "is_synthetic", "converted"]
        if c in df.columns
    ]
    return df[keep]


# ---------------------------------------------------------------------------
# Labelling & splitting
# ---------------------------------------------------------------------------

def _label(df: pd.DataFrame) -> pd.DataFrame:
    """Add `converted` column: 1 if purchase_count > 0, else 0."""
    df["converted"] = (df["purchase_count"].fillna(0) > 0).astype("int8")
    return df


def _stratified_split(
    df: pd.DataFrame, test_size: float, seed: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Stratified 80/20 split on `converted` label.

    Uses sklearn so the class ratio is preserved in both sets even when the
    minority class is tiny (0.82% positive rate in Retailrocket baseline).
    """
    from sklearn.model_selection import train_test_split

    train, test = train_test_split(
        df,
        test_size=test_size,
        random_state=seed,
        stratify=df["converted"],
    )
    return train.reset_index(drop=True), test.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_augmented_dataset(
    output_dir: Path,
    real_limit: int,
    synth_limit: int,
    test_size: float,
    seed: int,
    dry_run: bool,
) -> None:
    log.info("Connecting to ClickHouse …")
    client = _ch_client()

    log.info("Exporting real Retailrocket sessions …")
    df_real = _fetch_real_sessions(client, real_limit)
    log.info("  Real rows: %d", len(df_real))

    log.info("Exporting CTGAN synthetic sessions …")
    try:
        df_synth = _fetch_synthetic_sessions(client, synth_limit)
        log.info("  Synthetic rows: %d", len(df_synth))
    except Exception as exc:
        log.warning(
            "Could not fetch synthetic sessions (%s). "
            "Proceeding with real data only. "
            "Run 'make generate-synthetic' to populate analytics.synthetic_sessions.",
            exc,
        )
        df_synth = pd.DataFrame(columns=df_real.columns)

    # Combine
    df_combined = pd.concat([df_real, df_synth], ignore_index=True)
    real_rows = len(df_real)
    synth_rows = len(df_synth)
    combined_rows = len(df_combined)

    # Label
    df_combined = _label(df_combined)
    positive_rate = df_combined["converted"].mean()

    # Align features
    df_combined = _align_features(df_combined)

    # Report class distribution
    log.info(
        "Combined dataset: %d real + %d synthetic = %d rows | "
        "positive_rate=%.2f%%",
        real_rows, synth_rows, combined_rows, positive_rate * 100,
    )

    if dry_run:
        log.info("[dry-run] Skipping Parquet export.")
        print(df_combined.describe().to_string())
        return

    # Split
    df_train, df_test = _stratified_split(df_combined, test_size, seed)
    log.info(
        "Split: train=%d rows, test=%d rows (test_size=%.0f%%)",
        len(df_train), len(df_test), test_size * 100,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = output_dir / "augmented_training.parquet"
    test_path = output_dir / "augmented_test.parquet"

    df_train.to_parquet(train_path, index=False)
    df_test.to_parquet(test_path, index=False)

    log.info("Saved training set  → %s (%d rows)", train_path, len(df_train))
    log.info("Saved test set      → %s (%d rows)", test_path, len(df_test))

    # Summary report to stdout — consumed by notebook Cell 1 and CI logs.
    print(
        f"\n=== Augmented Dataset Summary ===\n"
        f"  real_rows        : {real_rows:>10,}\n"
        f"  synthetic_rows   : {synth_rows:>10,}\n"
        f"  combined_rows    : {combined_rows:>10,}\n"
        f"  positive_rate    : {positive_rate * 100:>9.2f}%\n"
        f"  train_size       : {len(df_train):>10,}\n"
        f"  test_size        : {len(df_test):>10,}\n"
        f"  train_path       : {train_path}\n"
        f"  test_path        : {test_path}\n"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build augmented training dataset (real + synthetic sessions)."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data"),
        help="Directory for output Parquet files (default: data/).",
    )
    parser.add_argument(
        "--real-limit",
        type=int,
        default=0,
        help="Max real rows to export; 0 = all (default: 0).",
    )
    parser.add_argument(
        "--synth-limit",
        type=int,
        default=0,
        help="Max synthetic rows to export; 0 = all (default: 0).",
    )
    parser.add_argument(
        "--test-size",
        type=float,
        default=0.2,
        help="Fraction of data held out for test set (default: 0.2).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible splits (default: 42).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and align data but do not write Parquet files.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = _parse_args()
    build_augmented_dataset(
        output_dir=args.output_dir,
        real_limit=args.real_limit,
        synth_limit=args.synth_limit,
        test_size=args.test_size,
        seed=args.seed,
        dry_run=args.dry_run,
    )
