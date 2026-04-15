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

DROP VIEW IF EXISTS analytics.events_mv;
DROP TABLE IF EXISTS analytics.events_queue;

CREATE TABLE IF NOT EXISTS analytics.events_queue
(
    raw_message String
)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'redpanda:9092',
    kafka_topic_list = 'lead-events',
    kafka_group_name = 'click-events-consumer',
    kafka_format = 'JSONAsString',
    kafka_num_consumers = 1,
    kafka_handle_error_mode = 'stream';

CREATE MATERIALIZED VIEW analytics.events_mv
TO analytics.click_events
AS
WITH
    ifNull(JSONExtractRaw(raw_message, 'properties'), '{}') AS properties_raw,
    ifNull(JSONExtractString(raw_message, 'event_id'), '') AS flat_event_id,
    ifNull(JSONExtractString(raw_message, 'messageId'), '') AS rudder_message_id,
    ifNull(JSONExtractString(raw_message, 'event_type'), '') AS flat_event_type,
    ifNull(JSONExtractString(raw_message, 'event'), '') AS rudder_event_type,
    ifNull(JSONExtractString(raw_message, 'page_url'), '') AS flat_page_url,
    ifNull(JSONExtractString(properties_raw, 'page_url'), '') AS props_page_url,
    ifNull(JSONExtractString(raw_message, 'event_time'), '') AS flat_event_time,
    ifNull(JSONExtractString(raw_message, 'timestamp'), '') AS rudder_event_time,
    ifNull(JSONExtractString(raw_message, 'referrer'), '') AS flat_referrer,
    ifNull(JSONExtractString(properties_raw, 'referrer'), '') AS props_referrer,
    ifNull(JSONExtractString(raw_message, 'element_selector'), '') AS flat_element_selector,
    ifNull(JSONExtractString(properties_raw, 'element_selector'), '') AS props_element_selector,
    ifNull(JSONExtractString(raw_message, 'element_tag'), '') AS flat_element_tag,
    ifNull(JSONExtractString(properties_raw, 'element_tag'), '') AS props_element_tag,
    ifNull(JSONExtractString(raw_message, 'device_type'), '') AS flat_device_type,
    ifNull(JSONExtractString(properties_raw, 'device_type'), '') AS props_device_type,
    ifNull(JSONExtractString(raw_message, 'session_id'), '') AS flat_session_id,
    ifNull(JSONExtractString(properties_raw, 'session_id'), '') AS props_session_id,
    ifNull(JSONExtractString(raw_message, 'anonymous_user_id'), '') AS flat_anonymous_id,
    ifNull(JSONExtractString(raw_message, 'anonymousId'), '') AS rudder_anonymous_id,
    ifNull(JSONExtractString(raw_message, 'userId'), '') AS rudder_user_id,
    JSONExtract(raw_message, 'x_pct', 'Nullable(Float64)') AS flat_x_pct,
    JSONExtract(properties_raw, 'x_pct', 'Nullable(Float64)') AS props_x_pct,
    JSONExtract(raw_message, 'y_pct', 'Nullable(Float64)') AS flat_y_pct,
    JSONExtract(properties_raw, 'y_pct', 'Nullable(Float64)') AS props_y_pct,
    JSONExtract(raw_message, 'scroll_pct', 'Nullable(Float64)') AS flat_scroll_pct,
    JSONExtract(properties_raw, 'scroll_pct', 'Nullable(Float64)') AS props_scroll_pct,
    JSONExtract(raw_message, 'viewport_width', 'Nullable(UInt16)') AS flat_viewport_width,
    JSONExtract(properties_raw, 'viewport_width', 'Nullable(UInt16)') AS props_viewport_width,
    JSONExtract(raw_message, 'viewport_height', 'Nullable(UInt16)') AS flat_viewport_height,
    JSONExtract(properties_raw, 'viewport_height', 'Nullable(UInt16)') AS props_viewport_height,
    ifNull(JSONExtractString(raw_message, 'event_payload'), '') AS flat_event_payload
SELECT
    if(flat_event_id != '', flat_event_id, if(rudder_message_id != '', rudder_message_id, toString(generateUUIDv4()))) AS event_id,
    ifNull(parseDateTime64BestEffortOrNull(if(flat_event_time != '', flat_event_time, rudder_event_time), 3, 'UTC'), now64(3)) AS event_time,
    now64(3) AS received_at,
    if(flat_event_type != '', flat_event_type, rudder_event_type) AS event_type,
    if(flat_page_url != '', flat_page_url, props_page_url) AS page_url,
    if(flat_referrer != '', flat_referrer, nullIf(props_referrer, '')) AS referrer,
    CAST(coalesce(flat_x_pct, props_x_pct) AS Nullable(Float32)) AS x_pct,
    CAST(coalesce(flat_y_pct, props_y_pct) AS Nullable(Float32)) AS y_pct,
    CAST(coalesce(flat_scroll_pct, props_scroll_pct) AS Nullable(Float32)) AS scroll_pct,
    if(flat_element_selector != '', flat_element_selector, nullIf(props_element_selector, '')) AS element_selector,
    if(flat_element_tag != '', flat_element_tag, nullIf(props_element_tag, '')) AS element_tag,
    if(flat_device_type != '', flat_device_type, if(props_device_type != '', props_device_type, 'unknown')) AS device_type,
    coalesce(flat_viewport_width, props_viewport_width) AS viewport_width,
    coalesce(flat_viewport_height, props_viewport_height) AS viewport_height,
    if(flat_session_id != '', flat_session_id, if(props_session_id != '', props_session_id, if(rudder_anonymous_id != '', rudder_anonymous_id, 'unknown_session'))) AS session_id,
    if(flat_anonymous_id != '', flat_anonymous_id, if(rudder_anonymous_id != '', rudder_anonymous_id, rudder_user_id)) AS anonymous_user_id,
    if(flat_event_payload != '', flat_event_payload, raw_message) AS event_payload
FROM analytics.events_queue;
