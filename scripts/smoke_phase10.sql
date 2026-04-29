-- Phase 10 smoke test: analytics.lead_scores_rule_based
-- Run via: make smoke-test-phase10
-- All queries must return rows without error.

-- 1. Tier distribution across both sources
SELECT
    source,
    score_tier,
    count()            AS sessions,
    round(avg(lead_score), 1) AS avg_score,
    min(lead_score)    AS min_score,
    max(lead_score)    AS max_score
FROM analytics.lead_scores_rule_based
GROUP BY source, score_tier
ORDER BY source, score_tier;

-- 2. Top 10 ranked leads (the Phase 12 use-case query)
SELECT
    anonymous_user_id,
    lead_score,
    score_tier,
    source,
    rule_add_to_cart,
    rule_purchase,
    rule_browsing_depth,
    rule_search_intent,
    rule_scroll_engagement,
    rule_bouncer
FROM analytics.lead_scores_rule_based
ORDER BY lead_score DESC
LIMIT 10;

-- 3. Hot leads exist (expect at least one row)
SELECT count() AS hot_count
FROM analytics.lead_scores_rule_based
WHERE score_tier = 'hot';

-- 4. Score boundaries respected: no score outside [0, 100]
SELECT count() AS out_of_range
FROM analytics.lead_scores_rule_based
WHERE lead_score < 0 OR lead_score > 100;

-- 5. Retailrocket sessions: bouncer never fires (page_views=0, not 1)
SELECT count() AS rr_bouncer_fires
FROM analytics.lead_scores_rule_based
WHERE source = 'retailrocket' AND rule_bouncer = 1;

-- 6. Rule contribution totals across all sessions
SELECT
    sum(rule_add_to_cart)       AS cart_sessions,
    sum(rule_purchase)          AS purchase_sessions,
    sum(rule_browsing_depth)    AS deep_browsing_sessions,
    sum(rule_search_intent)     AS search_sessions,
    sum(rule_scroll_engagement) AS scroll_engaged_sessions,
    sum(rule_bouncer)           AS bouncer_sessions
FROM analytics.lead_scores_rule_based;
