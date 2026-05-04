"""ClickHouse helpers for Phase 4 heatmap aggregation.

This module is designed to be imported by ``dashboard/app.py`` so the UI layer
can request binned, heatmap-ready dataframes without writing SQL inline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Mapping, Optional, Tuple

from heatmap_filters import build_url_predicate


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


def build_heatmap_aggregate_query(config: HeatmapQueryConfig) -> Tuple[str, Dict[str, Any]]:
    """Build a parameterized ClickHouse SQL query for 5% heatmap bins."""
    event_type = _validate_event_type(config.event_type)
    url_predicate, params = build_url_predicate(config.url_filter)

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


def build_session_stats_query(url_filter: str) -> Tuple[str, Dict[str, Any]]:
    """Build a parameterized ClickHouse SQL query for session-level stats."""
    url_predicate, params = build_url_predicate(url_filter)

    sql = f"""
    WITH scoped_events AS (
        SELECT
            session_id,
            event_type,
            scroll_pct
        FROM analytics.click_events
        WHERE {url_predicate}
            AND session_id IS NOT NULL
            AND session_id != ''
    ),
    session_rollup AS (
        SELECT
            session_id,
            countIf(event_type = 'page_view') AS page_view_count,
            maxIf(scroll_pct, event_type = 'scroll' AND scroll_pct IS NOT NULL) AS max_scroll_pct
        FROM scoped_events
        GROUP BY session_id
    ),
    events_agg AS (
        SELECT count() AS total_events
        FROM scoped_events
    )
    SELECT
        count() AS total_sessions,
        round(ifNull(avg(ifNull(max_scroll_pct, 0.0)), 0.0), 2) AS avg_scroll_depth_pct,
        round(
            if(count() = 0, 0.0, (countIf(page_view_count = 1) * 100.0) / count()),
            2
        ) AS bounce_rate_pct,
        (SELECT total_events FROM events_agg) AS total_events
    FROM session_rollup
    """.strip()

    return sql, params


def fetch_session_stats(client: Any, url_filter: str):
    """Execute the session stats aggregation and return one-row dataframe."""
    sql, params = build_session_stats_query(url_filter)
    return client.query_df(sql, parameters=params)


def build_click_ranking_query(url_filter: str, limit: int = 10) -> Tuple[str, Dict[str, Any]]:
    """Build a parameterized ClickHouse SQL query for top-clicked selectors."""
    url_predicate, params = build_url_predicate(url_filter)
    params["limit"] = max(1, int(limit))

    sql = f"""
    SELECT
        element_selector,
        count() AS click_count
    FROM analytics.click_events
    WHERE {url_predicate}
        AND event_type = 'click'
        AND element_selector IS NOT NULL
        AND element_selector != ''
    GROUP BY element_selector
    ORDER BY click_count DESC, element_selector ASC
    LIMIT %(limit)s
    """.strip()

    return sql, params


def fetch_click_ranking(client: Any, url_filter: str, limit: int = 10):
    """Execute click ranking aggregation and return up-to-limit rows."""
    sql, params = build_click_ranking_query(url_filter=url_filter, limit=limit)
    return client.query_df(sql, parameters=params)


def build_lead_funnel_query() -> Tuple[str, Dict[str, Any]]:
    """Build a parameterized ClickHouse SQL query for lead distribution."""
    sql = """
    SELECT
        score_tier,
        count() AS session_count
    FROM analytics.lead_scores_rule_based
    GROUP BY score_tier
    ORDER BY session_count DESC
    """.strip()
    return sql, {}


def fetch_lead_funnel(client: Any):
    """Execute lead funnel aggregation and return distribution rows."""
    sql, params = build_lead_funnel_query()
    return client.query_df(sql, parameters=params)


def build_top_leads_query(limit: int = 50) -> Tuple[str, Dict[str, Any]]:
    """Build a parameterized ClickHouse SQL query for top N leads."""
    sql = """
    SELECT
        ml.session_id AS session_id,
        ml.anonymous_user_id AS anonymous_user_id,
        ml.source AS source,
        round(ml.ml_lead_score * 100, 2) AS ml_score_pct,
        rb.lead_score AS rule_score,
        rb.score_tier AS score_tier,
        rb.first_event_at AS first_event_at,
        rb.last_event_at AS last_event_at,
        rb.rule_add_to_cart AS rule_add_to_cart,
        rb.rule_purchase AS rule_purchase,
        rb.rule_browsing_depth AS rule_browsing_depth,
        rb.rule_search_intent AS rule_search_intent,
        rb.rule_scroll_engagement AS rule_scroll_engagement,
        rb.rule_bouncer AS rule_bouncer
    FROM analytics.lead_scores_ml AS ml FINAL
    JOIN analytics.lead_scores_rule_based AS rb
        ON ml.session_id = rb.session_id
        AND ml.anonymous_user_id = rb.anonymous_user_id
        AND ml.source = rb.source
    ORDER BY ml.ml_lead_score DESC
    LIMIT %(limit)s
    """.strip()
    return sql, {"limit": max(1, int(limit))}


def fetch_top_leads(client: Any, limit: int = 50):
    """Execute top leads query and return up-to-limit rows."""
    sql, params = build_top_leads_query(limit=limit)
    return client.query_df(sql, parameters=params)


__all__ = [
    "ALLOWED_EVENT_TYPES",
    "HeatmapQueryConfig",
    "build_heatmap_aggregate_query",
    "build_session_stats_query",
    "build_click_ranking_query",
    "fetch_heatmap_aggregates",
    "fetch_heatmap_aggregates_for",
    "fetch_session_stats",
    "fetch_click_ranking",
    "build_lead_funnel_query",
    "fetch_lead_funnel",
    "build_top_leads_query",
    "fetch_top_leads",
]
