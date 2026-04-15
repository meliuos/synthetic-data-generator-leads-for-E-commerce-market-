"""ClickHouse helpers for Phase 4 heatmap aggregation.

This module is designed to be imported by ``dashboard/app.py`` so the UI layer
can request binned, heatmap-ready dataframes without writing SQL inline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Tuple


ALLOWED_EVENT_TYPES = {"click", "scroll", "mousemove"}


@dataclass(frozen=True)
class HeatmapQueryConfig:
    """Typed options for building a heatmap aggregation query."""

    url_filter: str
    event_type: str
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    viewport_width: Optional[int] = None
    viewport_height: Optional[int] = None
    device_type: Optional[str] = None
    min_count: int = 1


def _validate_event_type(event_type: str) -> str:
    normalized = event_type.strip().lower()
    if normalized not in ALLOWED_EVENT_TYPES:
        allowed = ", ".join(sorted(ALLOWED_EVENT_TYPES))
        raise ValueError(f"Unsupported event_type '{event_type}'. Allowed: {allowed}")
    return normalized


def _escape_like_value(value: str) -> str:
    """Escape SQL LIKE metacharacters while preserving '*' user wildcard support."""
    escaped = value.replace("\\", "\\\\")
    escaped = escaped.replace("%", r"\%")
    escaped = escaped.replace("_", r"\_")
    return escaped


def _build_url_predicate(url_filter: str) -> Tuple[str, Dict[str, Any]]:
    normalized = (url_filter or "").strip()
    if not normalized:
        raise ValueError("url_filter is required")

    if "*" in normalized:
        like_pattern = _escape_like_value(normalized).replace("*", "%")
        return "page_url LIKE %(page_url_like)s ESCAPE '\\\\'", {"page_url_like": like_pattern}

    return "page_url = %(page_url_exact)s", {"page_url_exact": normalized}


def build_heatmap_aggregate_query(config: HeatmapQueryConfig) -> Tuple[str, Dict[str, Any]]:
    """Build a parameterized ClickHouse SQL query for 5% heatmap bins."""
    event_type = _validate_event_type(config.event_type)
    url_predicate, params = _build_url_predicate(config.url_filter)

    predicates = [
        url_predicate,
        "event_type = %(event_type)s",
    ]

    params["event_type"] = event_type
    params["min_count"] = max(1, int(config.min_count))

    if config.start_time is not None:
        predicates.append("event_time >= %(start_time)s")
        params["start_time"] = config.start_time

    if config.end_time is not None:
        predicates.append("event_time <= %(end_time)s")
        params["end_time"] = config.end_time

    if config.viewport_width is not None:
        predicates.append("viewport_width = %(viewport_width)s")
        params["viewport_width"] = int(config.viewport_width)

    if config.viewport_height is not None:
        predicates.append("viewport_height = %(viewport_height)s")
        params["viewport_height"] = int(config.viewport_height)

    if config.device_type is not None:
        predicates.append("device_type = %(device_type)s")
        params["device_type"] = config.device_type

    # Scroll events do not always include x/y coordinates, so map to a vertical
    # lane (x=50) and use scroll_pct as y when required.
    base_x_expr = "if(event_type = 'scroll', 50.0, toFloat64(x_pct))"
    base_y_expr = "if(event_type = 'scroll', toFloat64(scroll_pct), toFloat64(y_pct))"

    predicates.append(f"{base_y_expr} IS NOT NULL")
    if event_type != "scroll":
        predicates.append(f"{base_x_expr} IS NOT NULL")

    where_sql = "\n        AND ".join(predicates)

    sql = f"""
    SELECT
        round({base_x_expr} / 5) * 5 AS x_bin_pct,
        round({base_y_expr} / 5) * 5 AS y_bin_pct,
        count() AS event_count,
        min(event_time) AS first_event_time,
        max(event_time) AS last_event_time
    FROM analytics.click_events
    WHERE {where_sql}
    GROUP BY x_bin_pct, y_bin_pct
    HAVING event_count >= %(min_count)s
    ORDER BY event_count DESC, y_bin_pct ASC, x_bin_pct ASC
    """.strip()

    return sql, params


def fetch_heatmap_aggregates(client: Any, config: HeatmapQueryConfig):
    """Execute aggregation query and return a pandas-like dataframe.

    The client is expected to be a ``clickhouse_connect`` client instance that
    implements ``query_df(sql, parameters=...)``.
    """
    sql, params = build_heatmap_aggregate_query(config)
    return client.query_df(sql, parameters=params)


def fetch_heatmap_aggregates_for(
    client: Any,
    *,
    url_filter: str,
    event_type: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    viewport_width: Optional[int] = None,
    viewport_height: Optional[int] = None,
    device_type: Optional[str] = None,
    min_count: int = 1,
):
    """Convenience wrapper around ``HeatmapQueryConfig`` for dashboard callers."""
    config = HeatmapQueryConfig(
        url_filter=url_filter,
        event_type=event_type,
        start_time=start_time,
        end_time=end_time,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        device_type=device_type,
        min_count=min_count,
    )
    return fetch_heatmap_aggregates(client, config)


__all__ = [
    "ALLOWED_EVENT_TYPES",
    "HeatmapQueryConfig",
    "build_heatmap_aggregate_query",
    "fetch_heatmap_aggregates",
    "fetch_heatmap_aggregates_for",
]
