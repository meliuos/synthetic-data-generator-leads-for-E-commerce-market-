"""
CTGAN trainer — produces ctgan_sessions.pkl for the prediction API.

Defaults: 200K rows / 10 epochs (the "whole-data, shallow-fit" profile).
Bump CTGAN_EPOCHS for a deeper fit.

primary_category comes from the *modal product-view category* per session —
joined via retailrocket_raw.item_latest (item_id -> category_id). This
gives real category labels for ~88% of retailrocket sessions, instead of
'unknown' for everything (which happens when category is sourced from
purchase_items, since only purchasers have rows there).

Usage:
    .venv-synth/bin/python scripts/quick_train_ctgan.py

Options (env vars):
    CTGAN_N_ROWS    rows to sample from session_features (default: 200000)
    CTGAN_EPOCHS    training epochs (default: 100)
    CTGAN_OUT       output path (default: models/ctgan_sessions.pkl)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import clickhouse_connect
import joblib
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

N_ROWS   = int(os.getenv("CTGAN_N_ROWS", "200000"))
EPOCHS   = int(os.getenv("CTGAN_EPOCHS", "10"))
OUT_PATH = Path(os.getenv("CTGAN_OUT", "models/ctgan_sessions.pkl"))

FEATURE_COLS = [
    "page_views", "product_views", "add_to_cart_count", "purchase_count",
    "search_count", "max_scroll_pct", "session_duration_seconds",
    "distinct_products_viewed", "cart_abandoned",
]
CATEGORY_COL = "primary_category"


def fetch_data() -> pd.DataFrame:
    log.info("Connecting to ClickHouse …")
    ch = clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        username=os.getenv("CLICKHOUSE_USER", "analytics"),
        password=os.getenv("CLICKHOUSE_PASSWORD", "analytics_password"),
        database=os.getenv("CLICKHOUSE_DATABASE", "analytics"),
    )

    log.info("Fetching %d rows from session_features (category from product views) …", N_ROWS)
    # Category source: modal product-view category per session, looked up via
    # retailrocket_raw.item_latest (item_id -> category_id). Sessions with no
    # mappable category get 'unknown' but are kept so CTGAN sees a realistic
    # distribution. Only retailrocket sessions for which a category exists
    # are sampled, to maximise the share of usable category labels.
    result = ch.query(f"""
        SELECT
            sf.page_views,
            sf.product_views,
            sf.add_to_cart_count,
            sf.purchase_count,
            sf.search_count,
            sf.max_scroll_pct,
            sf.session_duration_seconds,
            sf.distinct_products_viewed,
            sf.cart_abandoned,
            coalesce(nullIf(cat.primary_category, ''), 'unknown') AS primary_category
        FROM analytics.session_features AS sf
        INNER JOIN (
            SELECT
                ue.session_id AS session_id,
                topK(1)(toString(il.category_id))[1] AS primary_category
            FROM analytics.unified_events AS ue
            INNER JOIN retailrocket_raw.item_latest AS il
                ON toUInt64OrZero(ue.product_id) = il.item_id
            WHERE ue.source = 'retailrocket'
              AND ue.event_type = 'product_view'
              AND il.category_id IS NOT NULL
            GROUP BY ue.session_id
        ) AS cat ON sf.session_id = cat.session_id
        WHERE sf.source = 'retailrocket'
        LIMIT {N_ROWS}
    """)

    df = pd.DataFrame(result.result_rows, columns=result.column_names)
    log.info("Fetched %d rows, %d columns", len(df), len(df.columns))
    return df


def train(df: pd.DataFrame) -> None:
    from sdv.metadata import SingleTableMetadata
    from sdv.single_table import CTGANSynthesizer

    log.info("Building SDV metadata …")
    metadata = SingleTableMetadata()
    metadata.detect_from_dataframe(df)

    # Override types for known columns
    for col in ["page_views", "product_views", "add_to_cart_count",
                "purchase_count", "search_count", "distinct_products_viewed"]:
        if col in df.columns:
            metadata.update_column(col, sdtype="numerical", computer_representation="Int64")

    for col in ["max_scroll_pct", "session_duration_seconds"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float32")
            metadata.update_column(col, sdtype="numerical", computer_representation="Float")

    if "cart_abandoned" in df.columns:
        metadata.update_column("cart_abandoned", sdtype="categorical")

    if CATEGORY_COL in df.columns:
        metadata.update_column(CATEGORY_COL, sdtype="categorical")

    log.info("Training CTGANSynthesizer (%d epochs, %d rows) …", EPOCHS, len(df))
    synth = CTGANSynthesizer(
        metadata,
        epochs=EPOCHS,
        batch_size=500,
        verbose=True,
    )
    synth.fit(df)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(synth, OUT_PATH)
    log.info("Saved CTGANSynthesizer to %s", OUT_PATH)

    # Quick smoke-test
    log.info("Smoke-testing: sampling 100 rows …")
    sample = synth.sample(100)
    log.info("Sample OK — shape: %s", sample.shape)


if __name__ == "__main__":
    df = fetch_data()
    if df.empty:
        log.error("No data fetched — is ClickHouse running and session_features populated?")
        sys.exit(1)
    train(df)
    log.info("Done. Run `make api-up` then test the Predict page.")
