"""
Lead profiler — Phase 15.

Assembles a structured behavioral context dict for a given anonymous_user_id
by joining ClickHouse tables. The context is fed to prompt_builder and then
to the Claude API. No PII — only anonymous_user_id is used.
"""

from __future__ import annotations

import os
from datetime import timezone
from typing import Any


class LeadNotFoundError(Exception):
    """Raised when anonymous_user_id has no ML scores in lead_scores_ml."""


def _ch_client():
    try:
        import clickhouse_connect
    except ImportError as exc:
        raise ImportError(
            "clickhouse-connect is required. "
            "Install it with: pip install -r requirements-ai.txt"
        ) from exc

    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        username=os.getenv("CLICKHOUSE_USER", "analytics"),
        password=os.getenv("CLICKHOUSE_PASSWORD", "analytics_password"),
        database=os.getenv("CLICKHOUSE_DATABASE", "analytics"),
    )


def fetch_lead_context(anonymous_user_id: str) -> dict[str, Any]:
    """
    Build a structured context dict for the given lead.

    Joins:
      - analytics.lead_scores_ml FINAL      (ml_lead_score, model_version)
      - analytics.lead_scores_rule_based     (rule score, score_tier)
      - analytics.session_features           (behavioral aggregates)
      - analytics.purchase_items             (category exposure)

    Returns a dict suitable for Jinja2 template rendering and JSON serialisation.

    Raises
    ------
    LeadNotFoundError
        When the user has no ML score record.
    """
    ch = _ch_client()

    # --- ML + rule score --------------------------------------------------
    score_result = ch.query(
        """
        SELECT
            ml.anonymous_user_id,
            ml.ml_lead_score,
            ml.model_version,
            any(rb.lead_score)  AS rule_lead_score,
            any(rb.score_tier)  AS score_tier
        FROM analytics.lead_scores_ml AS ml FINAL
        LEFT JOIN analytics.lead_scores_rule_based AS rb FINAL
            ON ml.anonymous_user_id = rb.anonymous_user_id
        WHERE ml.anonymous_user_id = {uid:String}
        GROUP BY ml.anonymous_user_id, ml.ml_lead_score, ml.model_version
        LIMIT 1
        """,
        parameters={"uid": anonymous_user_id},
    )

    if not score_result.result_rows:
        raise LeadNotFoundError(
            f"No ML score found for anonymous_user_id={anonymous_user_id!r}. "
            "Run 'make score-sessions' to populate scores."
        )

    row = dict(zip(score_result.column_names, score_result.result_rows[0]))
    ml_lead_score = float(row["ml_lead_score"])
    rule_lead_score = int(row.get("rule_lead_score") or 0)
    score_tier = str(row.get("score_tier") or _tier_from_score(ml_lead_score * 100))

    # --- Session aggregates -----------------------------------------------
    sess_result = ch.query(
        """
        SELECT
            count()                           AS session_count,
            sum(add_to_cart_count)            AS add_to_cart_count,
            max(cart_abandoned)               AS cart_abandoned,
            sum(search_count)                 AS search_count,
            avg(max_scroll_pct)               AS avg_scroll_pct,
            groupArray(10)(session_id)        AS session_ids,
            max(last_event_at)                AS last_active
        FROM analytics.session_features
        WHERE anonymous_user_id = {uid:String}
        """,
        parameters={"uid": anonymous_user_id},
    )

    sess = dict(zip(sess_result.column_names, sess_result.result_rows[0])) if sess_result.result_rows else {}

    # --- Viewed products from purchase_items + click_events ---------------
    prod_result = ch.query(
        """
        SELECT groupArray(20)(DISTINCT product_id) AS viewed_products,
               groupArray(10)(DISTINCT category)   AS top_categories
        FROM analytics.purchase_items
        WHERE anonymous_user_id = {uid:String}
          AND product_id != ''
        """,
        parameters={"uid": anonymous_user_id},
    )
    prod = dict(zip(prod_result.column_names, prod_result.result_rows[0])) if prod_result.result_rows else {}

    # Coerce last_active to ISO-8601 string
    last_active = sess.get("last_active")
    if hasattr(last_active, "isoformat"):
        last_active_str = last_active.astimezone(timezone.utc).isoformat()
    else:
        last_active_str = str(last_active) if last_active else None

    viewed = list(prod.get("viewed_products") or [])[:10]
    categories = [c for c in (prod.get("top_categories") or []) if c][:5]

    return {
        "anonymous_user_id": anonymous_user_id,
        "score_tier": score_tier,
        "ml_lead_score": round(ml_lead_score, 4),
        "rule_lead_score": rule_lead_score,
        "top_categories": categories,
        "viewed_products": viewed,
        "add_to_cart_count": int(sess.get("add_to_cart_count") or 0),
        "cart_abandoned": bool(sess.get("cart_abandoned") or False),
        "session_count": int(sess.get("session_count") or 0),
        "avg_scroll_pct": round(float(sess.get("avg_scroll_pct") or 0.0), 1),
        "search_count": int(sess.get("search_count") or 0),
        "last_active": last_active_str,
    }


def _tier_from_score(score_0_100: float) -> str:
    if score_0_100 >= 60:
        return "hot"
    if score_0_100 >= 30:
        return "warm"
    return "cold"
