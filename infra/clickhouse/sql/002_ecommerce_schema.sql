-- =============================================================================
-- v1.1 E-commerce Schema Migration
-- File:    infra/clickhouse/sql/002_ecommerce_schema.sql
-- Applies: SCHEMA-01, SCHEMA-02, SCHEMA-03
-- Safe to run multiple times (fully idempotent).
-- DO NOT modify 001_events_schema.sql — all v1.1 changes are here.
-- =============================================================================
-- ORDERING NOTE (RESEARCH.md §8.1):
--   ALTER TABLE must execute BEFORE CREATE OR REPLACE MATERIALIZED VIEW.
--   If the columns do not exist when the new MV is installed, ClickHouse
--   raises "Cannot insert NULL to non-Nullable column".
-- =============================================================================

-- ---------------------------------------------------------------------------
-- ARTIFACT 1: Add 8 Nullable e-commerce columns to analytics.click_events
-- (SCHEMA-01)
-- ADD COLUMN IF NOT EXISTS → instant metadata-only change, no data rewrite.
-- No LowCardinality wrappers on new Nullable columns (RESEARCH.md §3 pitfall).
-- ---------------------------------------------------------------------------
ALTER TABLE analytics.click_events
    ADD COLUMN IF NOT EXISTS product_id    Nullable(String)         AFTER event_payload,
    ADD COLUMN IF NOT EXISTS category      Nullable(String)         AFTER product_id,
    ADD COLUMN IF NOT EXISTS price         Nullable(Decimal(18,2))  AFTER category,
    ADD COLUMN IF NOT EXISTS quantity      Nullable(UInt32)         AFTER price,
    ADD COLUMN IF NOT EXISTS order_id      Nullable(String)         AFTER quantity,
    ADD COLUMN IF NOT EXISTS cart_value    Nullable(Decimal(18,2))  AFTER order_id,
    ADD COLUMN IF NOT EXISTS search_query  Nullable(String)         AFTER cart_value,
    ADD COLUMN IF NOT EXISTS results_count Nullable(UInt32)         AFTER search_query;

-- ---------------------------------------------------------------------------
-- ARTIFACT 2: Sibling flat table for per-line-item purchase data
-- (SCHEMA-03 — secondary MV target)
-- MergeTree keyed on (order_id, product_id, event_time).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.purchase_items
(
    event_id          String,
    event_time        DateTime64(3, 'UTC'),
    order_id          String,
    anonymous_user_id String,
    session_id        String,
    product_id        String,
    sku               Nullable(String),
    name              Nullable(String),
    category          Nullable(String),
    price             Nullable(Decimal(18,2)),
    quantity          Nullable(UInt32),
    position          Nullable(UInt32),
    currency          Nullable(String)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (order_id, product_id, event_time);

-- ---------------------------------------------------------------------------
-- ARTIFACT 3: Sibling dedup table for purchase orders
-- (SCHEMA-03 — ReplacingMergeTree dedup, NOT a projection)
-- ReplacingMergeTree(event_time) keyed on order_id — latest event_time wins
-- during background merges. Use SELECT … FINAL for point-in-time dedup.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analytics.orders
(
    order_id          String,
    event_time        DateTime64(3, 'UTC'),
    anonymous_user_id String,
    session_id        String,
    total             Nullable(Decimal(18,2)),
    revenue           Nullable(Decimal(18,2)),
    tax               Nullable(Decimal(18,2)),
    shipping          Nullable(Decimal(18,2)),
    discount          Nullable(Decimal(18,2)),
    currency          Nullable(String),
    coupon            Nullable(String),
    products_json     String   -- raw products array JSON, preserved for debugging
)
ENGINE = ReplacingMergeTree(event_time)
PARTITION BY toYYYYMM(event_time)
ORDER BY order_id;

-- ---------------------------------------------------------------------------
-- ARTIFACT 4: Updated main MV — atomic in-place query replacement, no ingest gap
-- (SCHEMA-02)
-- ClickHouse 24.8 does not support CREATE OR REPLACE MATERIALIZED VIEW;
-- the correct atomic MV update is ALTER TABLE ... MODIFY QUERY.
-- This rewrites only the SELECT definition — the MV object, its internal
-- storage, and the Kafka consumer group offset on events_queue are all
-- preserved. Second run: MODIFY QUERY is always idempotent (re-applying the
-- same query is a no-op at the query-plan level).
-- The WITH block lines 47-79 of 001_events_schema.sql are reproduced VERBATIM
-- for all v1.0 fields; the 8 new e-commerce extractions are appended after.
-- ---------------------------------------------------------------------------
ALTER TABLE analytics.events_mv MODIFY QUERY
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
    ifNull(JSONExtractString(raw_message, 'event_payload'), '') AS flat_event_payload,
    -- v1.1 e-commerce extractions (SCHEMA-02, RESEARCH.md §3)
    ifNull(JSONExtractString(raw_message,    'product_id'),   '') AS flat_product_id,
    ifNull(JSONExtractString(properties_raw, 'product_id'),   '') AS props_product_id,
    ifNull(JSONExtractString(raw_message,    'category'),     '') AS flat_category,
    ifNull(JSONExtractString(properties_raw, 'category'),     '') AS props_category,
    JSONExtract(raw_message,    'price',     'Nullable(Float64)') AS flat_price,
    JSONExtract(properties_raw, 'price',     'Nullable(Float64)') AS props_price,
    JSONExtract(raw_message,    'quantity',  'Nullable(UInt32)')  AS flat_quantity,
    JSONExtract(properties_raw, 'quantity',  'Nullable(UInt32)')  AS props_quantity,
    ifNull(JSONExtractString(raw_message,    'order_id'),     '') AS flat_order_id,
    ifNull(JSONExtractString(properties_raw, 'order_id'),     '') AS props_order_id,
    JSONExtract(raw_message,    'cart_value','Nullable(Float64)') AS flat_cart_value,
    JSONExtract(properties_raw, 'cart_value','Nullable(Float64)') AS props_cart_value,
    -- search_query: RudderStack/Segment V2 uses 'query'; GA4 uses 'search_term' in properties
    ifNull(JSONExtractString(raw_message,    'query'),        '') AS flat_query,
    ifNull(JSONExtractString(properties_raw, 'query'),        '') AS props_query,
    ifNull(JSONExtractString(properties_raw, 'search_term'),  '') AS props_search_term,
    JSONExtract(raw_message,    'results_count','Nullable(UInt32)') AS flat_results_count,
    JSONExtract(properties_raw, 'results_count','Nullable(UInt32)') AS props_results_count
SELECT
    -- v1.0 fields (VERBATIM from 001_events_schema.sql lines 81-97)
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
    if(flat_event_payload != '', flat_event_payload, raw_message) AS event_payload,
    -- v1.1 e-commerce fields (SCHEMA-02)
    nullIf(if(flat_product_id != '', flat_product_id, props_product_id), '')  AS product_id,
    nullIf(if(flat_category   != '', flat_category,   props_category),   '')  AS category,
    CAST(coalesce(flat_price,      props_price)      AS Nullable(Decimal(18,2))) AS price,
    coalesce(flat_quantity,   props_quantity)                                  AS quantity,
    nullIf(if(flat_order_id   != '', flat_order_id,   props_order_id),   '')  AS order_id,
    CAST(coalesce(flat_cart_value, props_cart_value)  AS Nullable(Decimal(18,2))) AS cart_value,
    nullIf(if(flat_query != '', flat_query,
              if(props_query != '', props_query, props_search_term)), '')       AS search_query,
    coalesce(flat_results_count, props_results_count)                          AS results_count
FROM analytics.events_queue;

-- ---------------------------------------------------------------------------
-- ARTIFACT 5: Secondary MV — explodes products[] into per-line-item rows
-- (SCHEMA-03)
-- Reads from analytics.events_queue (same Kafka source as events_mv).
-- arrayJoin guard ensures non-purchase events never match the WHERE clause
-- produce zero rows (guard only fires on rows that passed the WHERE).
-- IF NOT EXISTS: second run is a no-op.
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.purchase_items_mv
TO analytics.purchase_items
AS
WITH
    ifNull(JSONExtractRaw(raw_message, 'properties'), '{}')  AS props,
    JSONExtractArrayRaw(props, 'products')                   AS products_arr,
    arrayJoin(if(notEmpty(products_arr), products_arr, ['{}'])) AS item_raw
SELECT
    ifNull(JSONExtractString(raw_message, 'messageId'),
           toString(generateUUIDv4()))                          AS event_id,
    ifNull(parseDateTime64BestEffortOrNull(
        ifNull(JSONExtractString(raw_message, 'timestamp'), ''), 3, 'UTC'),
        now64(3))                                               AS event_time,
    ifNull(JSONExtractString(props, 'order_id'), '')            AS order_id,
    ifNull(JSONExtractString(raw_message, 'anonymousId'), '')   AS anonymous_user_id,
    ifNull(JSONExtractString(raw_message, 'session_id'), '')    AS session_id,
    ifNull(JSONExtractString(item_raw, 'product_id'), '')       AS product_id,
    nullIf(JSONExtractString(item_raw, 'sku'), '')              AS sku,
    nullIf(JSONExtractString(item_raw, 'name'), '')             AS name,
    nullIf(JSONExtractString(item_raw, 'category'), '')         AS category,
    CAST(JSONExtract(item_raw, 'price', 'Nullable(Float64)')
         AS Nullable(Decimal(18,2)))                            AS price,
    JSONExtract(item_raw, 'quantity', 'Nullable(UInt32)')       AS quantity,
    JSONExtract(item_raw, 'position', 'Nullable(UInt32)')       AS position,
    nullIf(JSONExtractString(props, 'currency'), '')            AS currency
FROM analytics.events_queue
WHERE ifNull(JSONExtractString(raw_message, 'type'),  '') = 'purchase'
   OR ifNull(JSONExtractString(raw_message, 'event'), '') = 'Order Completed';

-- ---------------------------------------------------------------------------
-- ARTIFACT 6: Secondary MV — deduplicates purchase events into analytics.orders
-- (SCHEMA-03)
-- ReplacingMergeTree(event_time) on analytics.orders collapses duplicate
-- order_id rows during background merges; use SELECT … FINAL for exact dedup.
-- IF NOT EXISTS: second run is a no-op.
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.orders_mv
TO analytics.orders
AS
WITH
    ifNull(JSONExtractRaw(raw_message, 'properties'), '{}') AS props
SELECT
    ifNull(JSONExtractString(props, 'order_id'), '')           AS order_id,
    ifNull(parseDateTime64BestEffortOrNull(
        ifNull(JSONExtractString(raw_message, 'timestamp'), ''), 3, 'UTC'),
        now64(3))                                              AS event_time,
    ifNull(JSONExtractString(raw_message, 'anonymousId'), '')  AS anonymous_user_id,
    ifNull(JSONExtractString(raw_message, 'session_id'), '')   AS session_id,
    CAST(JSONExtract(props, 'total',    'Nullable(Float64)') AS Nullable(Decimal(18,2))) AS total,
    CAST(JSONExtract(props, 'revenue',  'Nullable(Float64)') AS Nullable(Decimal(18,2))) AS revenue,
    CAST(JSONExtract(props, 'tax',      'Nullable(Float64)') AS Nullable(Decimal(18,2))) AS tax,
    CAST(JSONExtract(props, 'shipping', 'Nullable(Float64)') AS Nullable(Decimal(18,2))) AS shipping,
    CAST(JSONExtract(props, 'discount', 'Nullable(Float64)') AS Nullable(Decimal(18,2))) AS discount,
    nullIf(JSONExtractString(props, 'currency'), '')           AS currency,
    nullIf(JSONExtractString(props, 'coupon'), '')             AS coupon,
    ifNull(JSONExtractRaw(props, 'products'), '[]')            AS products_json
FROM analytics.events_queue
WHERE ifNull(JSONExtractString(raw_message, 'type'),  '') = 'purchase'
   OR ifNull(JSONExtractString(raw_message, 'event'), '') = 'Order Completed';

-- ---------------------------------------------------------------------------
-- ARTIFACT 7: GA4 alias VIEW (zero storage, read-time remapping)
-- (SCHEMA-02 — GA4 compatibility layer)
-- CREATE OR REPLACE VIEW: second run replaces the view atomically.
-- Exposes item_id, item_category, transaction_id, search_term as GA4 aliases.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.click_events_ga4 AS
SELECT
    event_id,
    event_time,
    received_at,
    event_type,
    page_url,
    session_id,
    anonymous_user_id,
    event_payload,
    -- GA4 aliases
    product_id    AS item_id,
    category      AS item_category,
    price,
    quantity,
    order_id      AS transaction_id,
    cart_value,
    search_query  AS search_term,
    results_count
FROM analytics.click_events;
