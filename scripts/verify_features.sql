-- =============================================================================
-- Phase 9 Smoke / Verification Queries
-- File:    scripts/verify_features.sql
-- Run via: make smoke-test-v12
--
-- Each SELECT is a named check. All queries must return rows without error.
-- Expected values are annotated in comments where predictable.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- CHECK 1: unified_events — both sources visible
-- Expected: two rows ('live' and 'retailrocket'), each with count > 0.
-- ---------------------------------------------------------------------------
SELECT
    'unified_events_by_source' AS check_name,
    source,
    count()                    AS event_count
FROM analytics.unified_events
GROUP BY source
ORDER BY source;

-- ---------------------------------------------------------------------------
-- CHECK 2: unified_events — normalised event_type vocabulary
-- 'product_view', 'add_to_cart', 'purchase' must appear in Retailrocket rows.
-- No row should have raw Retailrocket labels ('view', 'addtocart', 'transaction')
-- when filtered to the 'retailrocket' source.
-- ---------------------------------------------------------------------------
SELECT
    'unified_events_rr_normalised_vocab' AS check_name,
    event_type,
    count()                              AS event_count
FROM analytics.unified_events
WHERE source = 'retailrocket'
GROUP BY event_type
ORDER BY event_count DESC
LIMIT 10;

-- ---------------------------------------------------------------------------
-- CHECK 3: session_features — row counts by source
-- Expected: two rows, each count > 0.
-- Retailrocket should have ~1.4M distinct visitor-day sessions.
-- Live sessions depend on traffic; may be 0 in a fresh environment.
-- ---------------------------------------------------------------------------
SELECT
    'session_features_by_source' AS check_name,
    source,
    count()                      AS session_count
FROM analytics.session_features
GROUP BY source
ORDER BY source;

-- ---------------------------------------------------------------------------
-- CHECK 4: live_session_features — feature completeness
-- Confirms the live view is queryable and returns meaningful metrics.
-- All counts are informational; no hard thresholds (live data volume varies).
-- ---------------------------------------------------------------------------
SELECT
    'live_session_feature_coverage' AS check_name,
    count()                         AS total_sessions,
    countIf(page_views > 0)         AS sessions_with_page_views,
    countIf(product_views > 0)      AS sessions_with_product_views,
    countIf(add_to_cart_count > 0)  AS sessions_with_cart,
    countIf(purchase_count > 0)     AS sessions_with_purchase,
    countIf(search_count > 0)       AS sessions_with_search,
    countIf(max_scroll_pct IS NOT NULL) AS sessions_with_scroll,
    countIf(cart_abandoned = 1)     AS cart_abandoners
FROM analytics.live_session_features;

-- ---------------------------------------------------------------------------
-- CHECK 5: retailrocket_session_features — feature completeness
-- view, addtocart, and transaction counters must be non-zero across the corpus.
-- max_scroll_pct must be NULL for ALL rows (no scroll data in Retailrocket).
-- page_views and search_count must be 0 for ALL rows.
-- ---------------------------------------------------------------------------
SELECT
    'rr_session_feature_coverage'   AS check_name,
    count()                         AS total_sessions,
    countIf(product_views > 0)      AS sessions_with_product_views,
    countIf(add_to_cart_count > 0)  AS sessions_with_cart,
    countIf(purchase_count > 0)     AS sessions_with_purchase,
    countIf(cart_abandoned = 1)     AS cart_abandoners,
    -- these must equal total_sessions (enforced invariants)
    countIf(page_views = 0)         AS page_views_always_zero,
    countIf(search_count = 0)       AS search_count_always_zero,
    countIf(max_scroll_pct IS NULL) AS max_scroll_always_null
FROM analytics.retailrocket_session_features;

-- ---------------------------------------------------------------------------
-- CHECK 6: session_features — cross-source feature averages
-- Informational — allows a quick sanity check that Retailrocket conversion
-- rates match the known source distribution (~0.82% of sessions have a purchase).
-- ---------------------------------------------------------------------------
SELECT
    'session_feature_averages'            AS check_name,
    source,
    round(avg(product_views), 2)          AS avg_product_views,
    round(avg(add_to_cart_count), 4)      AS avg_add_to_cart,
    round(avg(purchase_count), 4)         AS avg_purchase,
    round(avg(cart_abandoned), 4)         AS avg_cart_abandoned_rate,
    round(avg(session_duration_seconds), 0) AS avg_duration_seconds
FROM analytics.session_features
GROUP BY source
ORDER BY source;

-- ---------------------------------------------------------------------------
-- CHECK 7: unified_events — product_id populated for e-commerce events
-- For Retailrocket source, product_id (mapped from item_id) must always be
-- non-NULL. For live source, product_id is non-NULL only on e-commerce events.
-- ---------------------------------------------------------------------------
SELECT
    'unified_events_product_id_coverage' AS check_name,
    source,
    event_type,
    countIf(product_id IS NOT NULL)      AS with_product_id,
    countIf(product_id IS NULL)          AS without_product_id,
    count()                              AS total
FROM analytics.unified_events
WHERE event_type IN ('product_view', 'add_to_cart', 'purchase')
GROUP BY source, event_type
ORDER BY source, event_type;
