"""
Product prediction CLI — Phase 17.

Calls predict_for_product() and prints a JSON summary to stdout.
Also writes one row to analytics.prediction_log for audit trail.

Usage:
    python scripts/predict_product.py --product "Wireless Headphones" \\
        --category 1051 --price 49.99 --keywords "audio,bluetooth,noise-cancelling" \\
        --n-sessions 1000

Environment variables:
    CLICKHOUSE_HOST      default: localhost
    CLICKHOUSE_PORT      default: 8123
    CLICKHOUSE_USER      default: analytics
    CLICKHOUSE_PASSWORD  default: analytics_password
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.prediction.product_predictor import predict_for_product

log = logging.getLogger(__name__)


def _ch_client():
    import clickhouse_connect
    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        username=os.getenv("CLICKHOUSE_USER", "analytics"),
        password=os.getenv("CLICKHOUSE_PASSWORD", "analytics_password"),
        database=os.getenv("CLICKHOUSE_DATABASE", "analytics"),
    )


def _log_to_clickhouse(product_name: str, result, price: float, keywords: str) -> None:
    try:
        ch = _ch_client()
        ch.insert(
            "analytics.prediction_log",
            [[
                product_name,
                result.category,
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
        log.info("Prediction logged to analytics.prediction_log")
    except Exception as exc:
        log.warning("Failed to log prediction to ClickHouse: %s", exc)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Predict lead conversion likelihood for a given product."
    )
    parser.add_argument("--product", required=True, help="Product name.")
    parser.add_argument("--category", required=True, type=str,
                        help="Category ID (integer string, e.g. '1051').")
    parser.add_argument("--price", required=True, type=float, help="Product price.")
    parser.add_argument("--keywords", default="", help="Comma-separated keywords.")
    parser.add_argument("--n-sessions", type=int, default=1_000,
                        help="Number of synthetic sessions to sample (default: 1000).")
    parser.add_argument("--model", type=Path, default=Path("models/ctgan_sessions.pkl"),
                        help="Path to trained CTGANSynthesizer pkl.")
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()

    log.info(
        "Predicting for product='%s' category=%s price=%.2f n=%d",
        args.product, args.category, args.price, args.n_sessions,
    )

    try:
        result = predict_for_product(
            category=args.category,
            price=args.price,
            keywords=args.keywords,
            n_sessions=args.n_sessions,
            model_path=args.model,
        )
    except FileNotFoundError as exc:
        log.error("%s", exc)
        return 1
    except Exception as exc:
        log.exception("Prediction failed: %s", exc)
        return 1

    if not result.used_conditional:
        log.warning(
            "Category '%s' was not seen during CTGAN training — "
            "unconditional sampling was used. Results are indicative only.",
            args.category,
        )

    summary = {
        "product_name": args.product,
        "category": result.category,
        "price": args.price,
        "n_sessions_sampled": result.n_sessions_sampled,
        "used_conditional_sampling": result.used_conditional,
        "conversion_rate_pct": result.conversion_rate_pct,
        "tier_distribution": result.tier_distribution,
        "tier_distribution_pct": result.tier_distribution_pct,
        "top_features": result.top_features,
    }
    print(json.dumps(summary, indent=2))

    _log_to_clickhouse(args.product, result, args.price, args.keywords)
    return 0


if __name__ == "__main__":
    sys.exit(main())
