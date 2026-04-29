---
phase: 9
plan: 1
status: complete
completed: 2026-04-29
files_modified:
  - infra/clickhouse/sql/004_phase9_foundation.sql
  - scripts/verify_features.sql
  - Makefile
---

## What Was Done

Implemented all four read-time ClickHouse views that form the data layer for v1.2 lead scoring.

### analytics.unified_events
Read-time UNION ALL across `analytics.click_events` (live tracker) and `retailrocket_raw.events`
(Retailrocket dataset). Retailrocket event vocabulary is normalised to the live tracker vocabulary:
`view → product_view`, `addtocart → add_to_cart`, `transaction → purchase`. A `source` discriminator
column (`'live'` | `'retailrocket'`) is appended. Retailrocket `visitor_id` (UInt64) is cast to
String for `anonymous_user_id`; a day-visitor key is synthesised for `session_id`.

### analytics.live_session_features
GROUP BY `(session_id, anonymous_user_id)` over `analytics.click_events`, computing 11 behavioral
signals: `page_views`, `product_views`, `add_to_cart_count`, `purchase_count`, `search_count`,
`max_scroll_pct` (Nullable — NULL when session has no scroll events), `session_duration_seconds`,
`distinct_products_viewed`, `cart_abandoned`, `first_event_at`, `last_event_at`.

Filters: `session_id NOT IN ('', 'unknown_session') AND anonymous_user_id != ''` — excludes
pipeline sentinel values that would corrupt GROUP BY cardinality.

### analytics.retailrocket_session_features
GROUP BY synthesised `(visitor_id, toDate(event_time))` over `retailrocket_raw.events`. Same 11
columns with explicit NULL/zero for features that do not exist in Retailrocket:
- `page_views = 0`, `search_count = 0` — typed UInt64 to match live side
- `max_scroll_pct = CAST(NULL AS Nullable(Float32))` — typed Nullable(Float32) to match live side

### analytics.session_features
`SELECT * FROM analytics.live_session_features UNION ALL SELECT * FROM analytics.retailrocket_session_features`

### Makefile
`make schema-v12` — applies `004_phase9_foundation.sql`
`make smoke-test-v12` — runs `scripts/verify_features.sql` (7 checks)

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Read-time VIEWs, not materialized | Always-fresh data; no background jobs; correct at this scale; Phase 11 can cache if latency becomes an issue |
| Day-visitor session for Retailrocket | Closest approximation to a real session given the available data; day boundary is a natural session break for e-commerce |
| NULL vs 0 for missing features | NULLs preserve the semantic distinction "feature doesn't exist for this source" vs "feature was observed with value 0". LightGBM handles NULLs natively — do not fill |
| `uniqExactIf(product_id, product_id IS NOT NULL)` | `uniqExact` counts NULL as a distinct value; the `If` suffix excludes them |
| `maxIf(scroll_pct, event_type = 'scroll' AND scroll_pct IS NOT NULL)` | Returns NULL when no scroll events in session (ClickHouse 24.x Nullable aggregate behaviour, consistent with existing `heatmap_queries.py` usage) |

## What This Unlocks

- Phase 10 (Rule-based Lead Scoring) can now read from `analytics.session_features` to compute
  scores against the full behavioral signal vector.
- Phase 11 (ML Lead Scoring) can pull `analytics.session_features` as the training dataset
  (Retailrocket rows + live rows) for feature extraction.
