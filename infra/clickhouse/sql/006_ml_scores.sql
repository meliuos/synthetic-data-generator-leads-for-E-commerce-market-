-- =============================================================================
-- Phase 11: ML Lead Scoring Model — Score Storage
-- File:    infra/clickhouse/sql/006_ml_scores.sql
-- Applies: v1.2 — Lead Scoring & Identification
-- Safe to run multiple times (CREATE TABLE IF NOT EXISTS; ALTER ADD COLUMN only
-- if column does not yet exist).
-- DO NOT modify prior migration files.
-- =============================================================================
--
-- Creates one MergeTree table:
--   1. analytics.lead_scores_ml — stores LightGBM predictions per session
--
-- Design decisions:
--   - ReplacingMergeTree(scored_at) deduplicates re-runs of score_sessions.py.
--     If the same (source, anonymous_user_id, session_id) is scored twice, the
--     row with the later scored_at wins after ClickHouse background merging.
--     Use FINAL in queries where you need exactly one row per session.
--   - ml_lead_score is Float32 [0, 1] — the raw probability output of the model.
--     The Phase 12 dashboard applies the same tier thresholds as rule-based scoring
--     after multiplying by 100, so the API contract stays consistent.
--   - model_version is a free-form string ('lgbm_v1', 'lgbm_v2', etc.) so that
--     multiple model versions can coexist in the table for A/B comparison.
--   - scored_at uses DEFAULT now() so the batch script does not need to supply it.
--   - ORDER BY (source, anonymous_user_id, session_id) matches the natural join key
--     when joining against analytics.session_features or lead_scores_rule_based.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- TABLE 1: analytics.lead_scores_ml
-- Per-session ML lead scores written by scripts/score_sessions.py.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.lead_scores_ml
(
    session_id          String,
    anonymous_user_id   String,
    source              LowCardinality(String),
    ml_lead_score       Float32,           -- calibrated probability [0, 1]
    model_version       String,            -- e.g. 'lgbm_v1'
    scored_at           DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(scored_at)
ORDER BY (source, anonymous_user_id, session_id);
