-- Phase 20-01: Drift log table — one row per drift check run.
-- Enables trending: is model drift getting worse over time?

CREATE TABLE IF NOT EXISTS analytics.drift_log
(
    checked_at         DateTime,
    features_drifted   UInt8,
    max_jsd            Float32,
    status             LowCardinality(String)
)
ENGINE = MergeTree()
ORDER BY checked_at;
