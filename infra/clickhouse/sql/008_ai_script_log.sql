-- Phase 15 — AI Script Log
-- Records every Claude API call with token usage and cost for cost tracking
-- and cache-hit monitoring. ORDER BY (tier, generated_at) supports per-tier
-- cost roll-ups and time-series queries without a full-scan.

CREATE TABLE IF NOT EXISTS analytics.ai_script_log
(
    lead_id               String,
    tier                  LowCardinality(String),
    model                 String,
    prompt_tokens         UInt32,
    cache_creation_tokens UInt32,
    cache_read_tokens     UInt32,
    output_tokens         UInt32,
    cost_usd              Float32,
    generated_at          DateTime DEFAULT now()
)
ENGINE = MergeTree()
ORDER BY (tier, generated_at)
SETTINGS index_granularity = 8192;
