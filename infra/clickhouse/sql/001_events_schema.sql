CREATE DATABASE IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.click_events
(
    event_id String,
    event_time DateTime64(3, 'UTC'),
    received_at DateTime64(3, 'UTC') DEFAULT now64(3),
    event_type LowCardinality(String),
    page_url String,
    referrer Nullable(String),
    x_pct Nullable(Float32),
    y_pct Nullable(Float32),
    scroll_pct Nullable(Float32),
    element_selector Nullable(String),
    element_tag Nullable(String),
    device_type LowCardinality(String),
    viewport_width Nullable(UInt16),
    viewport_height Nullable(UInt16),
    session_id String,
    anonymous_user_id String,
    event_payload String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (page_url, event_type, toDate(event_time));

CREATE TABLE IF NOT EXISTS analytics.events_queue
(
    event_id String,
    event_time DateTime64(3, 'UTC'),
    event_type String,
    page_url String,
    referrer Nullable(String),
    x_pct Nullable(Float32),
    y_pct Nullable(Float32),
    scroll_pct Nullable(Float32),
    element_selector Nullable(String),
    element_tag Nullable(String),
    device_type String,
    viewport_width Nullable(UInt16),
    viewport_height Nullable(UInt16),
    session_id String,
    anonymous_user_id String,
    event_payload String
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'redpanda:9092',
    kafka_topic_list = 'lead-events',
    kafka_group_name = 'click-events-consumer',
    kafka_format = 'JSONEachRow',
    kafka_num_consumers = 1,
    kafka_handle_error_mode = 'stream';

DROP VIEW IF EXISTS analytics.events_mv;

CREATE MATERIALIZED VIEW analytics.events_mv
TO analytics.click_events
AS
SELECT
    event_id,
    event_time,
    now64(3) AS received_at,
    event_type,
    page_url,
    referrer,
    x_pct,
    y_pct,
    scroll_pct,
    element_selector,
    element_tag,
    if(device_type = '', 'unknown', device_type) AS device_type,
    viewport_width,
    viewport_height,
    session_id,
    anonymous_user_id,
    event_payload
FROM analytics.events_queue;
