"""
Phase 20-01 — Model drift detection via Jensen-Shannon divergence.

Compares the per-feature distributions of real session_features against
analytics.synthetic_sessions and flags columns that have drifted beyond a
configurable threshold.

Threshold bands (JSD, Jensen-Shannon Divergence in [0, 1]):
    < 0.10  → ok    (matches Phase 13 training target)
    0.10–0.15 → warn
    > 0.15  → fail
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from scipy.spatial.distance import jensenshannon

_FEATURE_COLS: list[str] = [
    "page_views",
    "product_views",
    "add_to_cart_count",
    "purchase_count",
    "search_count",
    "max_scroll_pct",
    "session_duration_seconds",
    "distinct_products_viewed",
]

_CLICKHOUSE_HOST     = os.getenv("CLICKHOUSE_HOST", "localhost")
_CLICKHOUSE_PORT     = int(os.getenv("CLICKHOUSE_PORT", "8123"))
_CLICKHOUSE_DB       = os.getenv("CLICKHOUSE_DB", "analytics")
_CLICKHOUSE_USER     = os.getenv("CLICKHOUSE_USER", "analytics")
_CLICKHOUSE_PASSWORD = os.getenv("CLICKHOUSE_PASSWORD", "analytics_password")

_WARN_JSD  = 0.10
_FAIL_JSD  = 0.15
_N_BINS    = 50
_MAX_ROWS  = 50_000


@dataclass
class DriftReport:
    checked_at: str
    features_checked: int
    features_drifted: list[dict[str, Any]]
    status: str                              # "ok" | "warn" | "fail"
    max_jsd: float
    all_feature_jsd: dict[str, float] = field(default_factory=dict)


def _get_client():
    import clickhouse_connect
    return clickhouse_connect.get_client(
        host=_CLICKHOUSE_HOST,
        port=_CLICKHOUSE_PORT,
        database=_CLICKHOUSE_DB,
        username=_CLICKHOUSE_USER,
        password=_CLICKHOUSE_PASSWORD,
    )


def compute_feature_jsd(
    real_df: pd.DataFrame,
    synthetic_df: pd.DataFrame,
) -> dict[str, float]:
    """Jensen-Shannon divergence per feature between real and synthetic DataFrames.

    scipy.spatial.distance.jensenshannon returns the JS *distance* (sqrt of JSD);
    squaring gives the true JSD in [0, 1].  Returns NaN for missing/constant columns.
    """
    result: dict[str, float] = {}
    shared_cols = [c for c in _FEATURE_COLS if c in real_df.columns and c in synthetic_df.columns]

    for col in shared_cols:
        r = real_df[col].dropna().to_numpy(dtype=float)
        s = synthetic_df[col].dropna().to_numpy(dtype=float)

        if r.size == 0 or s.size == 0:
            result[col] = float("nan")
            continue

        lo = min(r.min(), s.min())
        hi = max(r.max(), s.max())

        if lo == hi:
            result[col] = 0.0
            continue

        bins = np.linspace(lo, hi, _N_BINS + 1)
        p, _ = np.histogram(r, bins=bins, density=True)
        q, _ = np.histogram(s, bins=bins, density=True)

        # Laplace smoothing — avoids log(0) in KL divergence
        eps = 1e-10
        p = p + eps
        q = q + eps
        p /= p.sum()
        q /= q.sum()

        result[col] = float(jensenshannon(p, q) ** 2)

    return result


def check_drift(threshold: float = _FAIL_JSD) -> DriftReport:
    """Export real + synthetic sessions from ClickHouse, compute JSD, write to drift_log.

    Args:
        threshold: JSD value above which a feature is considered failed (default 0.15).

    Returns:
        DriftReport with per-feature JSD values and overall status.
    """
    client = _get_client()
    cols_expr = ", ".join(_FEATURE_COLS)

    # Real sessions
    real_result = client.query(
        f"SELECT {cols_expr} FROM analytics.session_features LIMIT {_MAX_ROWS}"
    )
    real_df = pd.DataFrame(real_result.result_rows, columns=real_result.column_names)

    # Synthetic sessions — non-fatal if table absent
    try:
        synth_result = client.query(
            f"SELECT {cols_expr} FROM analytics.synthetic_sessions LIMIT {_MAX_ROWS}"
        )
        synth_df = pd.DataFrame(synth_result.result_rows, columns=synth_result.column_names)
    except Exception:
        synth_df = pd.DataFrame(columns=_FEATURE_COLS)

    jsd_map = compute_feature_jsd(real_df, synth_df)

    features_drifted: list[dict[str, Any]] = []
    status = "ok"

    for name, jsd in jsd_map.items():
        if np.isnan(jsd):
            continue
        if jsd > threshold:
            features_drifted.append({"name": name, "jsd": round(jsd, 4)})
            status = "fail"
        elif jsd >= _WARN_JSD and status != "fail":
            features_drifted.append({"name": name, "jsd": round(jsd, 4)})
            status = "warn"

    valid_jsds = [v for v in jsd_map.values() if not np.isnan(v)]
    max_jsd = round(max(valid_jsds, default=0.0), 4)
    checked_at = datetime.now(timezone.utc).isoformat()

    report = DriftReport(
        checked_at=checked_at,
        features_checked=len(jsd_map),
        features_drifted=features_drifted,
        status=status,
        max_jsd=max_jsd,
        all_feature_jsd={k: round(v, 4) for k, v in jsd_map.items() if not np.isnan(v)},
    )

    # Log to ClickHouse — non-fatal
    try:
        client.insert(
            "analytics.drift_log",
            [[datetime.now(timezone.utc).replace(tzinfo=None), len(features_drifted), max_jsd, status]],
            column_names=["checked_at", "features_drifted", "max_jsd", "status"],
        )
    except Exception:
        pass

    return report
