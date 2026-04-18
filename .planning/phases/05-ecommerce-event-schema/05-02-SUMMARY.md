---
phase: 05-ecommerce-event-schema
plan: 02
subsystem: testing
tags: [clickhouse, kafka, redpanda, bash, smoke-test, ecommerce, materialized-view, mergetree, ga4]

# Dependency graph
requires:
  - phase: 05-01
    provides: "002_ecommerce_schema.sql — 8 Nullable e-commerce columns, purchase_items, orders, purchase_items_mv, orders_mv, click_events_ga4 view"
provides:
  - "scripts/smoke-test-v11.sh — end-to-end v1.1 schema verification (4 events, 6 assertion blocks)"
  - "make smoke-test-v11 Makefile target"
affects:
  - "Phase 6 (E-commerce Tracker API) — smoke test serves as acceptance test for events produced by the tracker"
  - "Phase 7 (Retailrocket Import) — smoke pattern establishes the idempotent per-run session_id approach"
  - "Phase 8 (Dashboard Panels) — confirms GA4 alias columns are queryable"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-milestone smoke test pattern: smoke-test-vX.Y.sh + Makefile target per milestone, never modifying prior version's test"
    - "Epoch-based SESSION_ID (ecom-smoke-<epoch>) for idempotent reruns without manual cleanup"
    - "Bounded deadline poll (deadline=$((SECONDS + N))) for materialized view flush wait — no infinite loops"
    - "Dual-timestamp events: event_time for events_mv (flat click_events path), timestamp for secondary MVs (purchase_items_mv, orders_mv)"

key-files:
  created:
    - scripts/smoke-test-v11.sh
  modified:
    - Makefile

key-decisions:
  - "Event B (add_to_cart) must include 'category' in properties to satisfy Assertion 1 c_category>=2 — plan's event payload omitted it"
  - "Each milestone gets its own smoke-test-vX.Y.sh + Makefile target — prior-version targets never modified"
  - "Dual-timestamp field strategy: purchase events carry both 'event_time' (for events_mv) and 'timestamp' (for secondary MVs purchase_items_mv/orders_mv)"

patterns-established:
  - "Smoke test per milestone: isolates version contracts, enables non-regression checks across versions"
  - "6-assertion block structure: coverage → flat → nested → fan-out → dedup → alias-view"

# Metrics
duration: 8min
completed: 2026-04-19
---

# Phase 5 Plan 2: v1.1 E-commerce Schema Smoke Test Summary

**End-to-end v1.1 schema verification script: 4 events (product_view flat, add_to_cart nested, purchase + duplicate) drive all 6 assertion blocks (SCHEMA-01/02/03 + GA4 alias view) through real Redpanda → ClickHouse pipeline**

## Performance

- **Duration:** 8 min
- **Started:** 2026-04-19T01:03:09Z
- **Completed:** 2026-04-19T01:11:00Z
- **Tasks:** 2 (+ 1 auto-fix)
- **Files modified:** 2

## Accomplishments

- `scripts/smoke-test-v11.sh` authored: produces 4 events, asserts 6 outcomes, uses bounded 10s deadline poll, zero PROJECTION references
- `make smoke-test-v11` target wired in Makefile; v1.0 `smoke-test:` target byte-identical
- End-to-end run verified: all 6 assertions pass; idempotent rerun confirmed (fresh SESSION_ID per epoch)
- v1.0 `make smoke-test` confirmed passing after v1.1 schema applied (no regression)

## Task Commits

Each task was committed atomically:

1. **Task 1: Author scripts/smoke-test-v11.sh** - `da208ca` (feat)
2. **Task 2: Wire make smoke-test-v11 target in Makefile** - `12118db` (feat)
3. **Bug fix: Add category to Event B properties** - `1423414` (fix — deviation Rule 1)

**Plan metadata:** (created after this section)

## Four Test Events Produced

| Event | event_type | Shape | Key fields set |
|-------|-----------|-------|----------------|
| A | product_view | Flat (top-level keys) | product_id, category, price at top level |
| B | add_to_cart | Nested (properties wrapper) | product_id, category, quantity, price in properties |
| C | purchase | Nested with products[] | properties.order_id, products[2 items], total; 'timestamp' field for secondary MV event_time |
| D | purchase (duplicate) | Same as C, different event_id/timestamp+50ms | Proves ReplacingMergeTree dedup: later event_time wins |

## Six Assertion Blocks

| # | Assertion | Tables queried | What it proves |
|---|-----------|---------------|----------------|
| 1 | SCHEMA-01 coverage | `analytics.click_events` | All 8 new columns populated: c_product_id≥2, c_category≥2, c_price≥2, c_quantity≥1, c_order_id≥2 |
| 2 | SCHEMA-02 flat | `analytics.click_events` WHERE event_type='product_view' | product_id='SKU-100', category='electronics/headphones', price=99.99 extracted from flat top-level keys |
| 3 | SCHEMA-02 nested | `analytics.click_events` WHERE event_type='add_to_cart' | product_id='SKU-200', quantity=3, price=19.50 extracted via properties fallback |
| 4 | SCHEMA-03 fan-out | `analytics.purchase_items` WHERE order_id=$ORDER_ID | count()=4 (2 dup events × 2 line items); groupArray contains SKU-100 and SKU-200 |
| 5 | SCHEMA-03 dedup | `analytics.orders FINAL` WHERE order_id=$ORDER_ID | count()=1 — FINAL forces query-time ReplacingMergeTree dedup; without FINAL count=2 |
| 6 | GA4 alias view | `analytics.click_events_ga4` WHERE event_type='product_view' | item_id='SKU-100', item_category='electronics/headphones'; column names item_id/transaction_id/search_term confirmed present |

## Runtime Observed

One end-to-end run: events land in `analytics.click_events` within 1–2 seconds; `purchase_items` and `orders` within 3–4 seconds. Total wall time from produce to all 6 assertions: ~5–6 seconds (well within the 10s deadline).

## v1.0 Regression Confirmation

`make smoke-test` (v1.0) passed after applying both `make schema` and `make schema-v11`. The additive ALTER TABLE columns and new secondary MVs do not affect the v1.0 insert path or the single-event click assertion. `scripts/smoke-test.sh` and the `smoke-test:` Makefile recipe are byte-identical.

## Pattern Established

Each milestone ships its own `smoke-test-vX.Y.sh` + Makefile target:

- `make smoke-test` → `scripts/smoke-test.sh` (v1.0, never modified)
- `make smoke-test-v11` → `scripts/smoke-test-v11.sh` (v1.1, added here)

Future milestones (v1.2 etc.) add new targets without touching prior ones. Running all smoke targets sequentially provides full multi-version regression coverage.

## Files Created/Modified

- `scripts/smoke-test-v11.sh` — End-to-end v1.1 smoke: 4 events, 6 assertion blocks, bounded poll, SESSION_ID=ecom-smoke-\<epoch\>
- `Makefile` — Added `smoke-test-v11` to `.PHONY` line and target recipe; existing `smoke-test:` recipe unchanged

## Decisions Made

1. **Dual-timestamp field strategy** — Purchase events carry both `event_time` (read by `events_mv` for `click_events`) and `timestamp` (read by `purchase_items_mv` and `orders_mv` for secondary tables). Both secondary MVs parse event_time from `raw_message.timestamp` (RudderStack/Segment V2 field), not `event_time`. Events without `timestamp` fall back to `now64(3)` in the secondary MVs.

2. **Event B must include category in properties** — The plan's Assertion 1 requires `c_category >= 2`, but the plan's Event B payload only specified `product_id`, `quantity`, `price` in properties. Without `category` in Event B, only Event A (flat product_view) would set category in click_events (c_category=1). Added `"category":"electronics/cables"` to Event B's properties to satisfy the assertion. This is the correct semantic: an add_to_cart event should carry the category of the item being carted.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Event B missing 'category' in properties caused Assertion 1 to fail**

- **Found during:** Task 1 end-to-end verification run
- **Issue:** Plan's Assertion 1 requires `c_category >= 2`. The plan's Event B payload (`add_to_cart` with `properties: {product_id, quantity, price}`) omitted `category`. Only Event A (flat product_view) set `category` in `click_events`, giving `c_category=1`. The assertion failed.
- **Fix:** Added `"category":"electronics/cables"` to Event B's `properties` block. Semantically correct: an add_to_cart event should declare the category of the carted item.
- **Files modified:** `scripts/smoke-test-v11.sh`
- **Verification:** Re-ran `make smoke-test-v11`; Assertion 1 now returns `c_category=2` and passes.
- **Committed in:** `1423414` (fix commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Event payload correction needed for assertion to pass. Semantically correct addition. No scope creep.

## Issues Encountered

None — aside from the Event B category fix above, the script ran correctly on first attempt after the fix.

## User Setup Required

None — no external service configuration required. `make smoke-test-v11` is fully automated.

## Next Phase Readiness

- Phase 5 has 1 remaining plan (05-03) — developer reference docs. Non-blocking.
- Phase 6 (E-commerce Tracker API): `make smoke-test-v11` is now the acceptance test to run after tracker events are wired up. The 4 event shapes (flat product_view, nested add_to_cart, purchase with products[]) are the exact shapes the tracker must emit.
- Phase 7 (Retailrocket Import): `analytics.purchase_items` and `analytics.orders` tables confirmed working via live assertions.
- Phase 8 (Dashboard Panels): `analytics.click_events_ga4` view confirmed queryable with `item_id`, `item_category`, `transaction_id`, `search_term` column names.

---
*Phase: 05-ecommerce-event-schema*
*Completed: 2026-04-19*
