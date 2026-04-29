-- Phase 11 smoke test: analytics.lead_scores_ml
-- Run via: make smoke-test-phase11
-- Expects at least one scored session to be present.
-- Run scripts/score_sessions.py first if the table is empty.

-- 1. Row count and score range per source
SELECT
    source,
    count()                      AS scored_sessions,
    round(avg(ml_lead_score), 4) AS avg_score,
    round(min(ml_lead_score), 4) AS min_score,
    round(max(ml_lead_score), 4) AS max_score,
    max(scored_at)               AS last_scored_at
FROM analytics.lead_scores_ml FINAL
GROUP BY source
ORDER BY source;

-- 2. Scores are in [0, 1]
SELECT count() AS out_of_range
FROM analytics.lead_scores_ml FINAL
WHERE ml_lead_score < 0 OR ml_lead_score > 1;

-- 3. Top 10 ML leads
SELECT
    anonymous_user_id,
    source,
    round(ml_lead_score * 100, 1) AS ml_score_pct,
    model_version,
    scored_at
FROM analytics.lead_scores_ml FINAL
ORDER BY ml_lead_score DESC
LIMIT 10;

-- 4. Join ML scores with rule-based scores for the same sessions
SELECT
    r.anonymous_user_id,
    r.source,
    r.lead_score          AS rule_score,
    r.score_tier          AS rule_tier,
    round(m.ml_lead_score * 100, 1) AS ml_score_pct
FROM analytics.lead_scores_rule_based AS r
INNER JOIN analytics.lead_scores_ml FINAL AS m
    ON r.session_id = m.session_id
ORDER BY m.ml_lead_score DESC
LIMIT 10;
