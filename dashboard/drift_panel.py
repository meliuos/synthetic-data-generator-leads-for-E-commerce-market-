"""
Phase 20-01 — Streamlit Model Health sidebar panel.

Self-contained module (no src/ dependency) so it is copyable into the
dashboard Docker image without changing the build context.

Mirrors the JSD computation logic in src/monitoring/drift_detector.py.
"""

from __future__ import annotations

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

_WARN_JSD = 0.10
_FAIL_JSD = 0.15
_N_BINS   = 50
_MAX_ROWS = 50_000


def _compute_jsd(real_df: pd.DataFrame, synth_df: pd.DataFrame) -> dict[str, float]:
    result: dict[str, float] = {}
    cols = [c for c in _FEATURE_COLS if c in real_df.columns and c in synth_df.columns]
    for col in cols:
        r = real_df[col].dropna().to_numpy(dtype=float)
        s = synth_df[col].dropna().to_numpy(dtype=float)
        if r.size == 0 or s.size == 0:
            result[col] = float("nan")
            continue
        lo, hi = min(r.min(), s.min()), max(r.max(), s.max())
        if lo == hi:
            result[col] = 0.0
            continue
        bins = np.linspace(lo, hi, _N_BINS + 1)
        p, _ = np.histogram(r, bins=bins, density=True)
        q, _ = np.histogram(s, bins=bins, density=True)
        eps = 1e-10
        p = (p + eps) / (p + eps).sum()
        q = (q + eps) / (q + eps).sum()
        result[col] = float(jensenshannon(p, q) ** 2)
    return result


def run_drift_check(client) -> dict[str, Any]:
    """Compute per-feature JSD and write one row to analytics.drift_log.

    Returns a dict with: checked_at, status, max_jsd, features_drifted,
    all_feature_jsd.
    """
    cols_expr = ", ".join(_FEATURE_COLS)

    real_result = client.query(
        f"SELECT {cols_expr} FROM analytics.session_features LIMIT {_MAX_ROWS}"
    )
    real_df = pd.DataFrame(real_result.result_rows, columns=real_result.column_names)

    try:
        synth_result = client.query(
            f"SELECT {cols_expr} FROM analytics.synthetic_sessions LIMIT {_MAX_ROWS}"
        )
        synth_df = pd.DataFrame(synth_result.result_rows, columns=synth_result.column_names)
    except Exception:
        synth_df = pd.DataFrame(columns=_FEATURE_COLS)

    jsd_map = _compute_jsd(real_df, synth_df)

    features_drifted: list[dict[str, Any]] = []
    status = "ok"
    for name, jsd in jsd_map.items():
        if np.isnan(jsd):
            continue
        if jsd > _FAIL_JSD:
            features_drifted.append({"feature": name, "jsd": round(jsd, 4)})
            status = "fail"
        elif jsd >= _WARN_JSD and status != "fail":
            features_drifted.append({"feature": name, "jsd": round(jsd, 4)})
            status = "warn"

    valid = [v for v in jsd_map.values() if not np.isnan(v)]
    max_jsd = round(max(valid, default=0.0), 4)
    checked_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    try:
        client.insert(
            "analytics.drift_log",
            [[datetime.now(timezone.utc).replace(tzinfo=None), len(features_drifted), max_jsd, status]],
            column_names=["checked_at", "features_drifted", "max_jsd", "status"],
        )
    except Exception:
        pass

    return {
        "checked_at": checked_at,
        "status": status,
        "max_jsd": max_jsd,
        "features_drifted": features_drifted,
        "all_feature_jsd": {k: round(v, 4) for k, v in jsd_map.items() if not np.isnan(v)},
    }


def render_model_health_sidebar(client) -> None:
    """Render the Model Health section inside st.sidebar — call from app.py."""
    import streamlit as st

    st.sidebar.header("Model Health")

    if st.sidebar.button("Run Drift Check", key="drift_btn"):
        with st.sidebar:
            with st.spinner("Computing drift…"):
                try:
                    report = run_drift_check(client)
                    st.session_state["drift_report"] = report
                except Exception as exc:
                    st.error(f"Drift check failed: {exc}")

    report = st.session_state.get("drift_report")
    if report is None:
        st.sidebar.caption("No drift check run yet this session.")
        return

    status = report["status"]
    badge = {"ok": "🟢 OK", "warn": "🟡 WARN", "fail": "🔴 FAIL"}.get(status, status)
    st.sidebar.markdown(f"**Status:** {badge}  \n**Max JSD:** {report['max_jsd']}  \n**Checked:** {report['checked_at']}")

    if report["all_feature_jsd"]:
        jsd_df = pd.DataFrame(
            {"Feature": list(report["all_feature_jsd"].keys()),
             "JSD": list(report["all_feature_jsd"].values())}
        ).sort_values("JSD", ascending=False)
        st.sidebar.dataframe(jsd_df, use_container_width=True, hide_index=True)


def render_slow_query_sidebar(client) -> None:
    """Render the ClickHouse slow-query panel inside st.sidebar."""
    import streamlit as st

    st.sidebar.header("Slow Queries (> 500 ms)")

    if st.sidebar.button("Refresh", key="slow_query_refresh"):
        try:
            result = client.query(
                """
                SELECT
                    query_id,
                    substring(query, 1, 80)  AS query_preview,
                    query_duration_ms,
                    read_rows,
                    formatReadableSize(memory_usage) AS memory
                FROM system.query_log
                WHERE type = 'QueryFinish'
                  AND query_duration_ms > 500
                ORDER BY query_duration_ms DESC
                LIMIT 10
                """
            )
            st.session_state["slow_queries"] = pd.DataFrame(
                result.result_rows, columns=result.column_names
            )
        except Exception as exc:
            st.sidebar.error(f"Query log unavailable: {exc}")

    slow_df = st.session_state.get("slow_queries")
    if slow_df is not None and not slow_df.empty:
        st.sidebar.dataframe(slow_df, use_container_width=True, hide_index=True)
    elif slow_df is not None:
        st.sidebar.caption("No slow queries recorded.")
    else:
        st.sidebar.caption("Click Refresh to load slow query data.")
