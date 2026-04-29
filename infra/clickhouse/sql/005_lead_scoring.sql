-- =============================================================================
-- Phase 10: Rule-Based Lead Scoring Engine
-- File:    infra/clickhouse/sql/005_lead_scoring.sql
-- Applies: v1.2 — Lead Scoring & Identification
-- Safe to run multiple times (all statements are idempotent via CREATE OR REPLACE VIEW).
-- DO NOT modify prior migration files.
-- =============================================================================
--
-- Creates one read-time view:
--   1. analytics.lead_scores_rule_based — rule-based score + tier over session_features
--
-- Design decisions:
--   - Rules are data, not code. The six-entry rule table is mirrored exactly in
--     src/scoring/rules.py _RULES. Any change to a delta or threshold must be
--     applied in both places simultaneously.
--   - WITH alias chaining (rule flags → raw_score → lead_score) keeps the SELECT
--     clause flat and avoids repeating the score expression for tier derivation.
--     ClickHouse 24.x evaluates WITH aliases in declaration order; later aliases
--     may reference earlier ones.
--   - scroll_engagement uses ifNull(max_scroll_pct, 0.0) rather than a separate
--     IS NOT NULL guard. NULL maps to 0.0 which is always below the 70.0 threshold,
--     preserving the Python semantic: None → rule does NOT fire.
--   - Bouncer predicate requires page_views = 1. Retailrocket sessions have
--     page_views = 0 (structural absence, not NULL) so bouncer naturally never
--     fires for that source — no special-casing required.
--   - Six rule_* flag columns (UInt8) are exposed in the SELECT for the Phase 12
--     interpretability panel: the dashboard can show exactly which signals drove
--     each session's score without recomputing the predicates client-side.
--   - Maximum achievable score = 85 (sum of all positive deltas). The [0, 100]
--     clamp exists to accommodate future rule additions without API breakage.
--
-- Tier thresholds (must match TIER_HOT_MIN / TIER_WARM_MIN in src/scoring/rules.py):
--   hot  >= 60
--   warm >= 30
--   cold  < 30
--
-- Rule table:
--   add_to_cart       +30   add_to_cart_count > 0
--   purchase          +20   purchase_count > 0
--   browsing_depth    +15   distinct_products_viewed >= 3
--   search_intent     +10   search_count > 0
--   scroll_engagement +10   max_scroll_pct > 70 (NULL does NOT fire)
--   bouncer           -10   page_views=1 AND all e-com counts=0
-- =============================================================================

-- ---------------------------------------------------------------------------
-- VIEW 1: analytics.lead_scores_rule_based
-- Per-session rule-based lead score over analytics.session_features.
-- Columns: session_id, anonymous_user_id, source, first_event_at, last_event_at,
--          lead_score, score_tier, rule_add_to_cart, rule_purchase,
--          rule_browsing_depth, rule_search_intent, rule_scroll_engagement,
--          rule_bouncer.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.lead_scores_rule_based AS
WITH
    -- -----------------------------------------------------------------------
    -- Rule flags — each resolves to UInt8 (0 or 1).
    -- Evaluated independently; multiple rules can fire in the same session.
    -- -----------------------------------------------------------------------
    toUInt8(add_to_cart_count > 0)               AS rule_add_to_cart,
    toUInt8(purchase_count > 0)                  AS rule_purchase,
    toUInt8(distinct_products_viewed >= 3)        AS rule_browsing_depth,
    toUInt8(search_count > 0)                    AS rule_search_intent,
    -- ifNull maps NULL to 0.0 (below threshold); preserves None-doesn't-fire semantic.
    toUInt8(ifNull(max_scroll_pct, 0.0) > 70.0)  AS rule_scroll_engagement,
    toUInt8(
        page_views        = 1
        AND add_to_cart_count = 0
        AND purchase_count    = 0
        AND search_count      = 0
        AND product_views     = 0
    )                                            AS rule_bouncer,

    -- -----------------------------------------------------------------------
    -- Raw score — sum of all fired rule deltas (unbounded integer).
    -- -----------------------------------------------------------------------
    toInt32(
          if(rule_add_to_cart       = 1,  30, 0)
        + if(rule_purchase          = 1,  20, 0)
        + if(rule_browsing_depth    = 1,  15, 0)
        + if(rule_search_intent     = 1,  10, 0)
        + if(rule_scroll_engagement = 1,  10, 0)
        + if(rule_bouncer           = 1, -10, 0)
    )                                            AS raw_score,

    -- -----------------------------------------------------------------------
    -- Clamped lead score — guaranteed [0, 100].
    -- -----------------------------------------------------------------------
    toInt32(greatest(0, least(100, raw_score)))   AS lead_score

SELECT
    session_id,
    anonymous_user_id,
    source,
    first_event_at,
    last_event_at,
    lead_score,
    -- Tier label derived from clamped score, not raw_score.
    CAST(
        if(lead_score >= 60, 'hot', if(lead_score >= 30, 'warm', 'cold'))
        AS LowCardinality(String)
    )                                            AS score_tier,
    -- Exploded rule flags for Phase 12 interpretability panel.
    rule_add_to_cart,
    rule_purchase,
    rule_browsing_depth,
    rule_search_intent,
    rule_scroll_engagement,
    rule_bouncer
FROM analytics.session_features;
