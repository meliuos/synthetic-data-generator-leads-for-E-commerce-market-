-- Phase 10: Rule-Based Lead Scoring Engine
-- Creates analytics.lead_scores_rule_based as a read-time VIEW over analytics.session_features.
--
-- Rule table (must stay in sync with src/scoring/rules.py _RULES):
--   add_to_cart      +30   add_to_cart_count > 0
--   purchase         +20   purchase_count > 0
--   browsing_depth   +15   distinct_products_viewed >= 3
--   search_intent    +10   search_count > 0
--   scroll_engagement+10   max_scroll_pct > 70  (NULL → no scroll → does NOT fire)
--   bouncer          -10   page_views=1 AND all e-com counts=0
--
-- Score: clamped sum of fired rule deltas, [0, 100].
-- Tier: hot ≥ 60, warm ≥ 30, cold < 30  (TIER_HOT_MIN / TIER_WARM_MIN in rules.py).
--
-- scroll_engagement: ifNull(max_scroll_pct, 0.0) maps NULL → 0.0 which never exceeds 70,
-- so the Python "None does NOT fire" behaviour is preserved without a separate IS NOT NULL guard.

CREATE OR REPLACE VIEW analytics.lead_scores_rule_based AS
WITH
    -- Rule flags (0/1)
    toUInt8(add_to_cart_count > 0)                                     AS rule_add_to_cart,
    toUInt8(purchase_count > 0)                                        AS rule_purchase,
    toUInt8(distinct_products_viewed >= 3)                             AS rule_browsing_depth,
    toUInt8(search_count > 0)                                          AS rule_search_intent,
    toUInt8(ifNull(max_scroll_pct, 0.0) > 70.0)                        AS rule_scroll_engagement,
    toUInt8(
        page_views = 1
        AND add_to_cart_count = 0
        AND purchase_count    = 0
        AND search_count      = 0
        AND product_views     = 0
    )                                                                  AS rule_bouncer,

    -- Raw score (unbounded integer sum of deltas)
    toInt32(
          if(rule_add_to_cart      = 1,  30, 0)
        + if(rule_purchase         = 1,  20, 0)
        + if(rule_browsing_depth   = 1,  15, 0)
        + if(rule_search_intent    = 1,  10, 0)
        + if(rule_scroll_engagement= 1,  10, 0)
        + if(rule_bouncer          = 1, -10, 0)
    )                                                                  AS raw_score,

    -- Clamped lead score [0, 100]
    toInt32(greatest(0, least(100, raw_score)))                        AS lead_score

SELECT
    session_id,
    anonymous_user_id,
    source,
    first_event_at,
    last_event_at,
    lead_score,
    CAST(
        if(lead_score >= 60, 'hot', if(lead_score >= 30, 'warm', 'cold'))
        AS LowCardinality(String)
    )                                                                  AS score_tier,
    -- Exploded rule flags for Phase 12 interpretability panel
    rule_add_to_cart,
    rule_purchase,
    rule_browsing_depth,
    rule_search_intent,
    rule_scroll_engagement,
    rule_bouncer
FROM analytics.session_features;
