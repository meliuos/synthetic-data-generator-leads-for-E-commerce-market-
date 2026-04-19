-- =============================================================================
-- v1.1 Retailrocket Raw Dataset Schema
-- File:    infra/clickhouse/sql/003_retailrocket_schema.sql
-- Applies: DATA-02, DATA-04, DATA-05
-- Safe to run multiple times (idempotent DDL).
-- =============================================================================

CREATE DATABASE IF NOT EXISTS retailrocket_raw;

CREATE TABLE IF NOT EXISTS retailrocket_raw.events
(
    event_time DateTime64(3, 'UTC'),
    visitor_id UInt64,
    item_id UInt64,
    event_type LowCardinality(String),
    transaction_id Nullable(UInt64),
    row_hash FixedString(64),
    load_batch_id FixedString(16),
    source_file LowCardinality(String),
    source_row_num UInt32,
    ingested_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(event_time)
ORDER BY (visitor_id, event_time, item_id, event_type, row_hash)
SETTINGS non_replicated_deduplication_window = 1000;

CREATE TABLE IF NOT EXISTS retailrocket_raw.item_properties
(
    event_time DateTime64(3, 'UTC'),
    item_id UInt64,
    property String,
    value String,
    row_hash FixedString(64),
    load_batch_id FixedString(16),
    source_file LowCardinality(String),
    source_row_num UInt32,
    ingested_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(ingested_at)
PARTITION BY toYYYYMM(event_time)
ORDER BY (item_id, property, event_time, row_hash)
SETTINGS non_replicated_deduplication_window = 1000;

CREATE TABLE IF NOT EXISTS retailrocket_raw.category_tree
(
    category_id UInt64,
    parent_id Nullable(UInt64),
    row_hash FixedString(64),
    load_batch_id FixedString(16),
    source_file LowCardinality(String),
    source_row_num UInt32,
    ingested_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(ingested_at)
ORDER BY (category_id, row_hash)
SETTINGS non_replicated_deduplication_window = 1000;

CREATE OR REPLACE VIEW retailrocket_raw.item_latest AS
SELECT
    item_id,
    toUInt64OrNull(argMaxIf(value, event_time, property = 'categoryid')) AS category_id,
    argMaxIf(value, event_time, property = 'available') AS available
FROM retailrocket_raw.item_properties
GROUP BY item_id;
