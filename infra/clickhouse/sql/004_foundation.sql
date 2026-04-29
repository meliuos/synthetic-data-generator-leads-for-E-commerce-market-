-- =============================================================================
-- Phase 9: Lead Scoring Data Foundation
-- File:    infra/clickhouse/sql/004_phase9_foundation.sql
-- Applies: v1.2 — Lead Scoring & Identification
-- Safe to run multiple times (all statements are idempotent via CREATE OR REPLACE VIEW).
-- DO NOT modify prior migration files.
-- =============================================================================
--
-- Creates four read-time views:
--   1. analytics.unified_events            — cross-source raw event view
--   2. analytics.live_session_features     — per-session features from click_events
--   3. analytics.retailrocket_session_features — per-visitor-day features from retailrocket_raw
--   4. analytics.session_features          — UNION ALL of 2 and 3 (consumed by v1.2 scoring)
--
-- Design decisions:
--   - All views are read-time (not MVs or materialized tables). This keeps the
--     data always fresh and avoids AggregatingMergeTree complexity. At academic
--     demo scale this is appropriate; Phase 11 can introduce a MergeTree cache
--     if query latency becomes an issue.
--   - Retailrocket has no session_id concept. A day-visitor key is synthesised:
--     concat(toString(visitor_id), '_', toString(toDate(event_time))).
--   - Retailrocket event vocabulary is normalised to live tracker vocabulary in
--     unified_events: 'view' → 'product_view', 'addtocart' → 'add_to_cart',
--     'transaction' → 'purchase'. session_features uses the original vocabulary
--     directly with conditional aggregation per-source.
--   - NULL vs 0 is preserved in session_features: a NULL max_scroll_pct means
--     no scroll data (Retailrocket source or session with no scroll events) — not
--     "scrolled to 0%". LightGBM handles NULLs natively; do NOT fill with 0.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- VIEW 1: analytics.unified_events
-- Minimal common schema across live tracker and Retailrocket events.
-- Columns: event_id, event_time, event_type (normalised), page_url,
--          anonymous_user_id, session_id, product_id, source.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.unified_events AS

SELECT
    event_id,
    event_time,
    event_type,
    toNullable(page_url)            AS page_url,
    toNullable(anonymous_user_id)   AS anonymous_user_id,
    toNullable(session_id)          AS session_id,
    product_id,                      -- already Nullable(String) from v1.1 schema
    'live'                          AS source
FROM analytics.click_events

UNION ALL

SELECT
    CAST(row_hash AS String)        AS event_id,
    event_time,
    -- Normalise Retailrocket vocabulary to live tracker vocabulary so downstream
    -- code can use a single event_type vocabulary.
    CAST(
        multiIf(
            event_type = 'view',        'product_view',
            event_type = 'addtocart',   'add_to_cart',
            event_type = 'transaction', 'purchase',
            event_type                  -- pass through unknown types unchanged
        ) AS LowCardinality(String)
    )                               AS event_type,
    CAST(NULL AS Nullable(String))  AS page_url,
    toNullable(toString(visitor_id)) AS anonymous_user_id,
    -- Synthesise a session key: visitor + calendar day
    toNullable(
        concat(toString(visitor_id), '_', toString(toDate(event_time)))
    )                               AS session_id,
    toNullable(toString(item_id))   AS product_id,
    'retailrocket'                  AS source
FROM retailrocket_raw.events;

-- ---------------------------------------------------------------------------
-- VIEW 2: analytics.live_session_features
-- Per-session behavioral feature vector computed over analytics.click_events.
-- Groups by (session_id, anonymous_user_id); filters out sentinel session IDs.
--
-- Column semantics:
--   page_views              — count of 'page_view' events in session
--   product_views           — count of 'product_view' events
--   add_to_cart_count       — count of 'add_to_cart' events
--   purchase_count          — count of 'purchase' events
--   search_count            — count of 'search' events
--   max_scroll_pct          — max scroll depth seen in session (NULL = no scroll events)
--   session_duration_seconds — wall-clock span from first to last event
--   distinct_products_viewed — distinct non-NULL product_ids touched in session
--   cart_abandoned          — 1 if added to cart but never purchased; 0 otherwise
--   first_event_at          — timestamp of earliest event in session
--   last_event_at           — timestamp of latest event in session
--   source                  — always 'live'
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.live_session_features AS
SELECT
    session_id,
    anonymous_user_id,

    -- funnel depth counters
    countIf(event_type = 'page_view')     AS page_views,
    countIf(event_type = 'product_view')  AS product_views,
    countIf(event_type = 'add_to_cart')   AS add_to_cart_count,
    countIf(event_type = 'purchase')      AS purchase_count,
    countIf(event_type = 'search')        AS search_count,

    -- scroll engagement: NULL when session has no scroll events
    -- maxIf on Nullable(Float32) returns NULL when no rows match the condition
    -- (ClickHouse 24.x behaviour, consistent with heatmap_queries.py usage).
    maxIf(scroll_pct, event_type = 'scroll' AND scroll_pct IS NOT NULL) AS max_scroll_pct,

    -- session span (0 for single-event sessions)
    toUInt32(greatest(0, dateDiff('second', min(event_time), max(event_time)))) AS session_duration_seconds,

    -- distinct products the session interacted with (NULLs excluded by uniqExactIf)
    toUInt64(uniqExactIf(product_id, product_id IS NOT NULL)) AS distinct_products_viewed,

    -- cart abandonment: added to cart in this session but never completed purchase
    toUInt8(if(
        countIf(event_type = 'add_to_cart') > 0 AND countIf(event_type = 'purchase') = 0,
        1, 0
    )) AS cart_abandoned,

    min(event_time) AS first_event_at,
    max(event_time) AS last_event_at,
    'live'          AS source

FROM analytics.click_events
WHERE session_id NOT IN ('', 'unknown_session')
  AND anonymous_user_id != ''
GROUP BY session_id, anonymous_user_id;

-- ---------------------------------------------------------------------------
-- VIEW 3: analytics.retailrocket_session_features
-- Per-visitor-day behavioral feature vector computed over retailrocket_raw.events.
-- Session key = visitor_id + calendar day (day-window session approximation).
--
-- Vocabulary differences vs live (intentionally NOT imputed):
--   page_views   = 0 — Retailrocket tracks item interactions, not page loads
--   search_count = 0 — Retailrocket has no search events
--   max_scroll_pct = NULL — no scroll data exists in Retailrocket
--
-- Source vocabulary: 'view' (product view), 'addtocart', 'transaction'.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.retailrocket_session_features AS
WITH
    concat(toString(visitor_id), '_', toString(toDate(event_time))) AS session_id,
    toString(visitor_id) AS anonymous_user_id
SELECT
    session_id,
    anonymous_user_id,

    -- Retailrocket has no page_view event type; leave as 0, not NULL,
    -- so the column type matches live_session_features (UInt64).
    toUInt64(0)                              AS page_views,
    countIf(event_type = 'view')             AS product_views,
    countIf(event_type = 'addtocart')        AS add_to_cart_count,
    countIf(event_type = 'transaction')      AS purchase_count,
    toUInt64(0)                              AS search_count,

    -- No scroll data in Retailrocket; explicit NULL typed to match live column.
    CAST(NULL AS Nullable(Float32))          AS max_scroll_pct,

    toUInt32(greatest(0, dateDiff('second', min(event_time), max(event_time)))) AS session_duration_seconds,

    -- All Retailrocket items have item_id (UInt64, non-nullable).
    toUInt64(uniqExact(item_id))             AS distinct_products_viewed,

    toUInt8(if(
        countIf(event_type = 'addtocart') > 0 AND countIf(event_type = 'transaction') = 0,
        1, 0
    ))                                       AS cart_abandoned,

    min(event_time) AS first_event_at,
    max(event_time) AS last_event_at,
    'retailrocket'  AS source

FROM retailrocket_raw.events
GROUP BY session_id, anonymous_user_id;

-- ---------------------------------------------------------------------------
-- VIEW 4: analytics.session_features
-- Unified session feature table — UNION ALL of live and Retailrocket sources.
-- This is the primary input for Phase 10 (rule-based scoring) and Phase 11 (ML).
--
-- Column types align between sub-views (verified at definition time):
--   String     : session_id, anonymous_user_id, source
--   UInt64     : page_views, product_views, add_to_cart_count, purchase_count,
--                search_count, distinct_products_viewed
--   Nullable(Float32) : max_scroll_pct
--   UInt32     : session_duration_seconds
--   UInt8      : cart_abandoned
--   DateTime64 : first_event_at, last_event_at
--
-- Usage:
--   SELECT * FROM analytics.session_features WHERE source = 'retailrocket' LIMIT 10;
--   SELECT * FROM analytics.session_features WHERE source = 'live' LIMIT 10;
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW analytics.session_features AS
SELECT * FROM analytics.live_session_features
UNION ALL
SELECT * FROM analytics.retailrocket_session_features;
