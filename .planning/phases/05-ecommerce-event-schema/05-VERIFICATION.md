---
phase: 05-ecommerce-event-schema
verified: 2026-04-19T00:00:00Z
status: passed
score: 7/7 must-haves verified
---

# Phase 5: E-commerce Event Schema — Verification Report

**Phase Goal:** The `analytics.click_events` table can accept e-commerce events additively — new typed `Nullable` columns for `product_id`, `category`, `price`, `quantity`, `order_id`, `cart_value`, `search_query`, `results_count`, a materialized-view update that extracts them from both flat and nested `properties` JSON shapes, a `purchase_items` sibling table with ARRAY JOIN fan-out, and an `orders` ReplacingMergeTree(event_time) sibling table for server-side purchase dedup — all without touching or rewriting existing v1.0 events.

**Verified:** 2026-04-19
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Projection Substitution Note

The ROADMAP described two "projections" (ARRAY JOIN projection + ReplacingMergeTree projection). Research in `05-RESEARCH.md` §4 and §7.3 proved both are technically impossible in ClickHouse: projections cannot use ARRAY JOIN (GitHub #98953) and cannot declare a different engine (GitHub #24778, #46968). The implementation correctly substitutes two sibling materialized views (`purchase_items_mv` writing to `analytics.purchase_items` MergeTree, `orders_mv` writing to `analytics.orders` ReplacingMergeTree(event_time)). This substitution is accepted as equivalent — it preserves both functional outcomes. A `CREATE PROJECTION` statement in the code would be a bug; none is present.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `make schema-v11` is idempotent — second run exits 0, row count unchanged | VERIFIED | Two consecutive runs both returned "Schema applied successfully … EXIT:0"; click_events count stayed at 116 |
| 2 | 8 new Nullable columns exist on `analytics.click_events` with correct types | VERIFIED | Live `system.columns` query returned all 8 with exact types: `Nullable(String)` x4, `Nullable(Decimal(18, 2))` x2, `Nullable(UInt32)` x2 |
| 3 | All v1.0 columns intact and no existing columns removed or retyped | VERIFIED | Full column list shows 17 v1.0 columns (event_id through event_payload) in original positions; git diff confirms 001_events_schema.sql is byte-identical |
| 4 | `analytics.orders` is ReplacingMergeTree(event_time) keyed on order_id and deduplicates | VERIFIED | system.tables: engine=ReplacingMergeTree, engine_full confirms `ReplacingMergeTree(event_time) … ORDER BY order_id`; Assertion 5 of smoke test: orders FINAL count=1 for duplicate purchase |
| 5 | `analytics.purchase_items` provides per-line-item fan-out from products[] | VERIFIED | system.tables: engine=MergeTree, ORDER BY (order_id, product_id, event_time); Assertion 4: count=4 (2 purchase events × 2 line items), SKU-100 and SKU-200 both present |
| 6 | `analytics.events_mv` extracts e-commerce fields from both flat and nested JSON | VERIFIED | Assertion 2 (flat product_view): product_id=SKU-100, category=electronics/headphones, price=99.99 PASS; Assertion 3 (nested add_to_cart): product_id=SKU-200, quantity=3, price=19.5 PASS |
| 7 | `make smoke-test` (v1.0) continues to pass — no regression | VERIFIED | `make smoke-test` returned "PASS: event ingested in <=5s … EXIT:0" after v1.1 schema is applied |

**Score:** 7/7 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `infra/clickhouse/sql/002_ecommerce_schema.sql` | 6+ SQL artifacts, idempotent guards | VERIFIED | 271 lines; 7 artifacts (ALTER+2 tables+MODIFY QUERY+2 MVs+1 view); all IF NOT EXISTS / OR REPLACE guarded |
| `infra/clickhouse/sql/001_events_schema.sql` | Byte-identical to v1.0 | VERIFIED | `git diff HEAD -- 001_events_schema.sql` returns no diff; not touched in any phase 5 commit |
| `analytics.click_events` (live) | 8 Nullable columns appended | VERIFIED | system.columns live query confirms all 8 with exact types |
| `analytics.purchase_items` (live) | MergeTree, ORDER BY (order_id, product_id, event_time) | VERIFIED | engine_full: `MergeTree PARTITION BY toYYYYMM(event_time) ORDER BY (order_id, product_id, event_time)` |
| `analytics.orders` (live) | ReplacingMergeTree(event_time), ORDER BY order_id | VERIFIED | engine_full: `ReplacingMergeTree(event_time) PARTITION BY toYYYYMM(event_time) ORDER BY order_id` |
| `analytics.events_mv` (live) | MaterializedView with v1.1 e-commerce extractions | VERIFIED | system.tables engine=MaterializedView; MODIFY QUERY applied; Assertions 2+3 confirm flat and nested extraction |
| `analytics.purchase_items_mv` (live) | MaterializedView ARRAY JOIN fan-out | VERIFIED | system.tables confirms MaterializedView; Assertion 4 confirms 4-row fan-out |
| `analytics.orders_mv` (live) | MaterializedView writing to orders | VERIFIED | system.tables confirms MaterializedView; Assertion 5 confirms dedup |
| `analytics.click_events_ga4` (live) | View with GA4 aliases | VERIFIED | system.tables engine=View; Assertion 6: item_id=SKU-100, item_category=electronics/headphones |
| `Makefile` | schema-v11 and smoke-test-v11 targets | VERIFIED | Both targets in .PHONY and with recipes; schema-v11 passes 002 file to apply-schema.sh; schema: target unchanged |
| `scripts/smoke-test-v11.sh` | 6-assertion end-to-end test, exit 0 | VERIFIED | 326 lines; all 6 assertions passed live; epoch SESSION_ID for idempotent reruns |
| `docs/schema-v1.1.md` | 8-section developer reference with substitution rationale | VERIFIED | 148 lines; substitution paragraph with RESEARCH.md §4/§7.3 and GitHub #98953/#24778/#46968 |
| `README.md` | Pointer to schema-v1.1.md | VERIFIED | Line 58: bullet linking docs/schema-v1.1.md with make schema-v11 / smoke-test-v11 |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `make schema-v11` | `002_ecommerce_schema.sql` | `apply-schema.sh $1` | VERIFIED | apply-schema.sh takes SQL file as `$1`, defaults to 001; schema-v11 passes 002 |
| `events_mv` MODIFY QUERY | `analytics.click_events` 8 new columns | `ALTER TABLE … MODIFY QUERY` | VERIFIED | MV SELECT includes all 8 e-commerce expressions; flat+props fallback pattern |
| `purchase_items_mv` | `analytics.purchase_items` | `TO analytics.purchase_items` | VERIFIED | Confirmed in SQL; live Assertion 4 passes with 4-row fan-out |
| `orders_mv` | `analytics.orders` | `TO analytics.orders` | VERIFIED | Confirmed in SQL; live Assertion 5 passes with FINAL dedup to count=1 |
| `click_events_ga4` view | `analytics.click_events` | `FROM analytics.click_events` | VERIFIED | View SELECT aliases product_id→item_id, category→item_category, order_id→transaction_id, search_query→search_term |
| `make schema` | `001_events_schema.sql` (unchanged) | `apply-schema.sh` (no arg) | VERIFIED | apply-schema.sh defaults to 001 when no arg; 001 is byte-identical |

---

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| SCHEMA-01: 8 Nullable e-commerce columns on click_events | SATISFIED | Live system.columns confirms all 8; smoke test Assertion 1 PASS (product_id=2, category=2, price=2, quantity=1, order_id=2) |
| SCHEMA-02: events_mv extracts from flat + nested JSON shapes | SATISFIED | Assertions 2 (flat) and 3 (nested) both PASS in live smoke run |
| SCHEMA-03: purchase_items fan-out + orders dedup | SATISFIED | Assertion 4 (purchase_items count=4) and Assertion 5 (orders FINAL count=1) both PASS |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | — | — | — |

**Forbidden pattern checks:**
- `CREATE PROJECTION` in 002_ecommerce_schema.sql: NOT PRESENT (correct — substituted by sibling MVs)
- `DROP … events_mv` or `DROP … events_queue` in 002_ecommerce_schema.sql: NOT PRESENT (correct — v1.0 objects preserved)
- TODO/FIXME/placeholder in any delivered file: none found

---

## Human Verification Required

None. All success criteria were verified programmatically against a live running stack.

---

## Success Criteria Checklist

| Criterion | Method | Result |
|-----------|--------|--------|
| 1. `make schema-v11` on existing data completes without error, row count before = after | Live run + count query | PASS — EXIT:0; count=116 before and after |
| 2. Second back-to-back `make schema-v11` is idempotent, no ADD COLUMN failures, EXIT:0 | Live second run | PASS — "Schema applied successfully" EXIT:0 |
| 3. v1.0-shape events still succeed post-migration, new columns read NULL | v1.0 smoke test pass | PASS — `make smoke-test` EXIT:0; click table has 116 v1.0 rows with NULL in e-commerce columns |
| 4. DESCRIBE analytics.click_events lists 8 new Nullable columns, all v1.0 columns present | system.columns query | PASS — 25 total columns: 17 v1.0 + 8 new Nullable |
| 5. `analytics.orders` ReplacingMergeTree(event_time) sibling table exists and deduplicates by order_id under FINAL | system.tables + Assertion 5 | PASS — engine confirmed; FINAL dedup count=1 for duplicate purchase |

---

## Gaps Summary

No gaps. All 7 observable truths are verified, all required artifacts exist, are substantive, and are wired correctly. The live stack confirmed end-to-end behavior through a complete smoke run.

---

_Verified: 2026-04-19_
_Verifier: Claude (gsd-verifier)_
