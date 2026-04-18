---
phase: 05-ecommerce-event-schema
plan: 01
subsystem: database
tags: [clickhouse, sql, migration, materialized-view, kafka, mergetree, ecommerce, schema]

# Dependency graph
requires:
  - phase: 01-04
    provides: "001_events_schema.sql v1.0 schema (click_events, events_queue, events_mv)"
provides:
  - "8 Nullable e-commerce columns on analytics.click_events (product_id, category, price, quantity, order_id, cart_value, search_query, results_count)"
  - "analytics.purchase_items flat MergeTree for per-line-item purchase data"
  - "analytics.orders ReplacingMergeTree(event_time) for order dedup keyed on order_id"
  - "analytics.purchase_items_mv secondary MV — ARRAY JOIN exploder for products[]"
  - "analytics.orders_mv secondary MV — writes to orders for purchase dedup"
  - "analytics.click_events_ga4 VIEW with GA4 aliases (item_id, item_category, transaction_id, search_term)"
  - "make schema-v11 Makefile target for idempotent v1.1 migration"
affects:
  - "Phase 6 (E-commerce Tracker API) — inserts purchase events to events_queue; expects all 8 columns populated by events_mv"
  - "Phase 7 (Retailrocket Import) — queries click_events and purchase_items columns"
  - "Phase 8 (Dashboard Panels) — queries click_events_ga4 and purchase_items for e-commerce stats"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Additive ALTER TABLE ADD COLUMN IF NOT EXISTS for live-table schema extension (no downtime)"
    - "ALTER TABLE mv_name MODIFY QUERY for atomic MV query swap in ClickHouse 24.8 (no ingest gap)"
    - "Secondary materialized views as sibling tables for ARRAY JOIN and ReplacingMergeTree dedup (not projections)"
    - "IF NOT EXISTS / OR REPLACE guards for fully idempotent multi-run SQL migration files"
    - "CREATE OR REPLACE VIEW for zero-storage read-time alias remapping (GA4 compatibility layer)"

key-files:
  created:
    - infra/clickhouse/sql/002_ecommerce_schema.sql
  modified:
    - Makefile

key-decisions:
  - "ALTER TABLE MODIFY QUERY used instead of CREATE OR REPLACE MATERIALIZED VIEW (not supported in ClickHouse 24.8)"
  - "Secondary MVs (not projections) for products[] ARRAY JOIN and order_id dedup — projections cannot use ARRAY JOIN or different engines"
  - "Separate schema-v11 make target (not folded into existing schema:) to keep v1.0 smoke test intact"
  - "No LowCardinality wrappers on new Nullable columns to avoid ALTER-time block-structure mismatch bugs (pre-24.8)"
  - "JSONExtract Float64 then CAST to Decimal(18,2) for price/cart_value (no JSONExtractDecimal function exists)"

patterns-established:
  - "Migration files numbered sequentially (001_, 002_) — each additive, never modifying prior files"
  - "Flat-then-properties fallback pattern for JSON extraction (same as v1.0): if(flat != '', flat, props) for strings, coalesce for numerics"

# Metrics
duration: 5min
completed: 2026-04-18
---

# Phase 5 Plan 1: E-commerce Schema Migration Summary

**Additive ClickHouse v1.1 schema: 8 Nullable e-commerce columns, purchase_items MergeTree, orders ReplacingMergeTree dedup, secondary MVs for ARRAY JOIN and dedup, GA4 alias view — all idempotent via ALTER TABLE / IF NOT EXISTS guards**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-18T23:21:02Z
- **Completed:** 2026-04-18T23:26:18Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `infra/clickhouse/sql/002_ecommerce_schema.sql` authored with all 6 SQL artifacts in correct ordering (ALTER before MV swap)
- `make schema-v11` applies the migration idempotently; third-run verified as no-op
- All 8 Nullable e-commerce columns confirmed in `system.columns` with exact types (Nullable(String), Nullable(Decimal(18,2)), Nullable(UInt32))
- `analytics.orders` (ReplacingMergeTree), `analytics.purchase_items` (MergeTree), three MVs, and GA4 view all verified in `system.tables`
- v1.0 `make smoke-test` still passes (no regression); `001_events_schema.sql` byte-identical (git diff --exit-code exit 0)

## Task Commits

Each task was committed atomically:

1. **Task 1: Author 002_ecommerce_schema.sql** - `864a5c0` (feat)
2. **Task 2: Add schema-v11 Makefile target** - `e43b786` (feat)
3. **Bug fix: ALTER TABLE MODIFY QUERY syntax** - `9cb525e` (fix — deviation Rule 1)

**Plan metadata:** (created below)

## Files Created/Modified

- `infra/clickhouse/sql/002_ecommerce_schema.sql` — v1.1 additive migration: ALTER TABLE (8 columns), CREATE TABLE purchase_items, CREATE TABLE orders, ALTER TABLE events_mv MODIFY QUERY, CREATE MV purchase_items_mv, CREATE MV orders_mv, CREATE OR REPLACE VIEW click_events_ga4
- `Makefile` — Added `schema-v11` target and `.PHONY` declaration; existing `schema:` target unchanged

## Six SQL Artifacts in 002_ecommerce_schema.sql

| # | Artifact | Type | Idempotency guard |
|---|----------|------|-------------------|
| 1 | `ALTER TABLE analytics.click_events` (8 cols) | DDL | `ADD COLUMN IF NOT EXISTS` |
| 2 | `CREATE TABLE analytics.purchase_items` | MergeTree | `IF NOT EXISTS` |
| 3 | `CREATE TABLE analytics.orders` | ReplacingMergeTree(event_time) | `IF NOT EXISTS` |
| 4 | `ALTER TABLE analytics.events_mv MODIFY QUERY` | MV update | always re-applies (idempotent) |
| 5 | `CREATE MATERIALIZED VIEW analytics.purchase_items_mv` | Secondary MV | `IF NOT EXISTS` |
| 6 | `CREATE MATERIALIZED VIEW analytics.orders_mv` | Secondary MV | `IF NOT EXISTS` |
| 7 | `CREATE OR REPLACE VIEW analytics.click_events_ga4` | Alias view | `OR REPLACE` |

## Column Types Actually Present After Migration

Query: `SELECT name, type FROM system.columns WHERE database='analytics' AND table='click_events' AND name IN (...) ORDER BY name`

| Column | Type |
|--------|------|
| cart_value | Nullable(Decimal(18, 2)) |
| category | Nullable(String) |
| order_id | Nullable(String) |
| price | Nullable(Decimal(18, 2)) |
| product_id | Nullable(String) |
| quantity | Nullable(UInt32) |
| results_count | Nullable(UInt32) |
| search_query | Nullable(String) |

## Idempotent Second-Run Test

`make schema-v11` was run three times total (once fresh, twice more as no-op verification). All three runs returned: `Schema applied successfully from infra/clickhouse/sql/002_ecommerce_schema.sql` with exit code 0, no errors, no data loss.

## Decisions Made

1. **ALTER TABLE MODIFY QUERY instead of CREATE OR REPLACE MATERIALIZED VIEW** — ClickHouse 24.8 does not support `CREATE OR REPLACE MATERIALIZED VIEW` syntax (only VIEW/TABLE/DICTIONARY/FUNCTION are valid OR REPLACE targets). `ALTER TABLE mv_name MODIFY QUERY` achieves identical semantics: atomic definition update, offset preservation, no ingest gap.

2. **Secondary MVs instead of projections** — confirmed research finding: projections cannot use ARRAY JOIN (GitHub #98953) and cannot declare a different engine (ReplacingMergeTree). Both requirements need secondary MVs writing to sibling tables.

3. **Separate `schema-v11` target** — keeping `make schema` pointing solely at `001_events_schema.sql` preserves the v1.0 smoke test path unchanged and isolates v1.1 migration to a clean entry point.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] CREATE OR REPLACE MATERIALIZED VIEW not supported in ClickHouse 24.8**

- **Found during:** Task 1 verification (`make schema-v11` first run)
- **Issue:** `CREATE OR REPLACE MATERIALIZED VIEW analytics.events_mv` raised `Code: 62 SYNTAX_ERROR`. ClickHouse 24.8 only supports `CREATE OR REPLACE` for TABLE, VIEW, DICTIONARY, FUNCTION — not MATERIALIZED VIEW.
- **Fix:** Replaced `CREATE OR REPLACE MATERIALIZED VIEW analytics.events_mv TO analytics.click_events AS` with `ALTER TABLE analytics.events_mv MODIFY QUERY`. This is the correct atomic MV query replacement for ClickHouse 24.8 — it rewrites the SELECT definition in-place, preserving the MV object, internal storage, and Kafka consumer group offsets.
- **Files modified:** `infra/clickhouse/sql/002_ecommerce_schema.sql`
- **Verification:** `make schema-v11` ran cleanly three times; `events_mv` confirmed as MaterializedView in `system.tables`; smoke test passed
- **Committed in:** `9cb525e` (fix commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Required syntax correction for deployed ClickHouse version. Semantics are identical — atomic MV update with preserved offsets. No scope creep.

## Issues Encountered

- `events_mv` was inadvertently modified during syntax investigation (a test `ALTER TABLE MODIFY QUERY` with a trivial SELECT ran). Restored by running `make schema` which uses the v1.0 drop-and-recreate pattern. Final `make schema-v11` re-applied the correct full query. No data was lost (dev environment, no live traffic).

## User Setup Required

None — no external service configuration required. `make schema-v11` is fully automated.

## Next Phase Readiness

- Phase 6 (E-commerce Tracker API): `analytics.click_events` has all 8 e-commerce columns; `events_mv` will extract them from incoming events. Tracker can begin sending `product_id`, `category`, `price`, `quantity`, `order_id`, `cart_value`, `search_query`, `results_count` in either flat top-level keys or nested `properties`.
- Phase 7 (Retailrocket Import): `analytics.purchase_items` and `analytics.orders` tables exist with correct schemas. Import MVs are wired to `events_queue`.
- Phase 8 (Dashboard Panels): `analytics.click_events_ga4` view exposes `item_id`, `item_category`, `transaction_id`, `search_term` for GA4-shaped queries.
- No blockers for Phases 6, 7, 8 (can run in parallel per roadmap).
- Note: Historical v1.0 rows in `click_events` will have NULL in all 8 new columns — this is expected behavior (MV is not applied retroactively).

---
*Phase: 05-ecommerce-event-schema*
*Completed: 2026-04-18*
