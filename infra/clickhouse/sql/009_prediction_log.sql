-- Phase 17 — Product Prediction Log
-- Records every predict_for_product() call for audit trail and analytics.
-- ORDER BY (category, predicted_at) supports per-category trend queries
-- and time-series roll-ups without a full-scan.

CREATE TABLE IF NOT EXISTS analytics.prediction_log
(
    product_name        String,
    category            String,
    price               Float32,
    keywords            String,
    n_sessions_sampled  UInt32,
    conversion_rate_pct Float32,
    tier_hot_pct        Float32,
    tier_warm_pct       Float32,
    tier_cold_pct       Float32,
    used_conditional    UInt8,
    predicted_at        DateTime DEFAULT now()
)
ENGINE = MergeTree()
ORDER BY (category, predicted_at)
SETTINGS index_granularity = 8192;
