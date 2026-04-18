# Schema v1.1 — E-commerce Events

This document describes the v1.1 additive schema extension to `analytics.click_events`. It adds
8 Nullable e-commerce columns, two sibling tables (`analytics.purchase_items`,
`analytics.orders`), and a zero-storage GA4 alias view (`analytics.click_events_ga4`). It
deliberately does **not** modify v1.0 schema objects, rebuild the base table, or change
`infra/clickhouse/sql/001_events_schema.sql`. All changes are isolated in
`infra/clickhouse/sql/002_ecommerce_schema.sql`.

Implements: SCHEMA-01, SCHEMA-02, SCHEMA-03 (see [REQUIREMENTS.md](../.planning/REQUIREMENTS.md)).

---

## New columns on `analytics.click_events`

Eight Nullable columns are appended after `event_payload` via `ADD COLUMN IF NOT EXISTS` (instant
metadata-only change; no data rewrite):

| Column | Type | Source shape | Example |
|---|---|---|---|
| `product_id` | `Nullable(String)` | flat or `properties.product_id` | `"SKU-100"` |
| `category` | `Nullable(String)` | flat or `properties.category` | `"electronics/headphones"` |
| `price` | `Nullable(Decimal(18,2))` | flat or `properties.price` | `99.99` |
| `quantity` | `Nullable(UInt32)` | flat or `properties.quantity` | `3` |
| `order_id` | `Nullable(String)` | flat or `properties.order_id` | `"ord-12345"` |
| `cart_value` | `Nullable(Decimal(18,2))` | flat or `properties.cart_value` | `139.49` |
| `search_query` | `Nullable(String)` | `properties.query` (or GA4 `search_term` fallback) | `"wireless"` |
| `results_count` | `Nullable(UInt32)` | flat or `properties.results_count` | `42` |

All columns are `Nullable`. v1.0 events (click, scroll, pageview, session_start) continue
inserting unchanged with NULLs in these fields. The materialized view extracts from both flat
top-level JSON keys and nested `properties` JSON, matching the v1.0 fallback pattern.

---

## Sibling tables (NOT projections)

> **Why sibling materialized views instead of projections?**
> The v1.1 roadmap originally described a `products[]` ARRAY JOIN projection and a
> `ReplacingMergeTree(event_time)` projection keyed on `order_id`. Pre-planning research proved
> both are technically impossible in ClickHouse:
> - Projections cannot use `ARRAY JOIN` — see
>   [`.planning/phases/05-ecommerce-event-schema/05-RESEARCH.md`](../.planning/phases/05-ecommerce-event-schema/05-RESEARCH.md)
>   §4 and GitHub [ClickHouse #98953](https://github.com/ClickHouse/ClickHouse/issues/98953).
> - Projections inherit the base table's storage engine; they cannot declare
>   `ENGINE = ReplacingMergeTree(...)` — see
>   [`.planning/phases/05-ecommerce-event-schema/05-RESEARCH.md`](../.planning/phases/05-ecommerce-event-schema/05-RESEARCH.md)
>   §7.3 and GitHub [ClickHouse #24778](https://github.com/ClickHouse/ClickHouse/issues/24778),
>   [#46968](https://github.com/ClickHouse/ClickHouse/issues/46968).
>
> The functional outcomes the roadmap intended (per-line-item queries, server-side purchase dedup)
> are preserved by writing two secondary materialized views that read from the same
> `analytics.events_queue` Kafka source and fan out into dedicated sibling tables described below.

### `analytics.purchase_items`

Engine: `MergeTree`, ordered by `(order_id, product_id, event_time)`.

Populated by `analytics.purchase_items_mv`, which `arrayJoin`s
`JSONExtractArrayRaw(properties, 'products')` to explode each purchase event into one row per
line item.

Columns: `event_id`, `event_time`, `order_id`, `anonymous_user_id`, `session_id`, `product_id`,
`sku`, `name`, `category`, `price`, `quantity`, `position`, `currency`.

**Use for:** "how many of product X sold?", category mix per order, per-line SKU queries.

### `analytics.orders`

Engine: `ReplacingMergeTree(event_time)`, keyed on `order_id`.

Populated by `analytics.orders_mv`, which writes one row per `purchase` / `Order Completed`
event. Duplicate `order_id` rows (from network retries or back-button reloads) are collapsed
during background merges; latest `event_time` wins.

Columns: `order_id`, `event_time`, `anonymous_user_id`, `session_id`, `total`, `revenue`, `tax`,
`shipping`, `discount`, `currency`, `coupon`, `products_json`.

**Query tip:** use `SELECT ... FROM analytics.orders FINAL` or `argMax(col, event_time)` to
force query-time dedup — background merge is asynchronous.

---

## Main MV update

`analytics.events_mv` is updated in-place via `ALTER TABLE analytics.events_mv MODIFY QUERY`.
This is the correct atomic MV query replacement for ClickHouse 24.8 (`CREATE OR REPLACE
MATERIALIZED VIEW` is not supported in this version). The MV object, internal storage, and Kafka
consumer group offsets on `analytics.events_queue` are all preserved — no ingest gap.

The updated SELECT adds the 8 new e-commerce columns using the same flat-then-`properties`
fallback pattern as v1.0. Historical rows already in `click_events` will have NULL in the new
columns — this is expected behavior; the MV is not applied retroactively (see RESEARCH.md §8.5).

---

## GA4 alias view `analytics.click_events_ga4`

A zero-storage, read-time-only remapping view that exposes GA4 field names alongside the native
RudderStack/Segment V2 column names stored in `click_events`. No data is written; no insert
overhead.

| v1.1 column | GA4 alias |
|---|---|
| `product_id` | `item_id` |
| `category` | `item_category` |
| `order_id` | `transaction_id` |
| `search_query` | `search_term` |

Note: GA4's `items[]` array is not exposed on this view. Consumers that need per-item data
should query `analytics.purchase_items` directly.

---

## Running the migration

```bash
make schema-v11
```

- **Idempotent:** safe to re-run (`ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`,
  `CREATE MATERIALIZED VIEW IF NOT EXISTS`, `ALTER TABLE … MODIFY QUERY`, `CREATE OR REPLACE`).
- Does **not** drop or rebuild existing v1.0 objects.
- Does **not** modify `infra/clickhouse/sql/001_events_schema.sql`.
- Underlying SQL: [`infra/clickhouse/sql/002_ecommerce_schema.sql`](../infra/clickhouse/sql/002_ecommerce_schema.sql).

---

## Verifying the migration

```bash
make smoke-test-v11
```

Drives 4 events (flat shape, nested `properties` shape, purchase with line items, duplicate
purchase) through the real pipeline and asserts: 8 new columns populate correctly, per-line-item
fan-out in `purchase_items` works, `order_id` dedup in `orders` works, GA4 aliases exist on
`click_events_ga4`. Script: [`scripts/smoke-test-v11.sh`](../scripts/smoke-test-v11.sh).

---

## Related references

- Roadmap — [`.planning/ROADMAP.md`](../.planning/ROADMAP.md) (Phase 5 entry)
- Requirements — [`.planning/REQUIREMENTS.md`](../.planning/REQUIREMENTS.md) (SCHEMA-01..03)
- Research (full rationale, pitfalls, ClickHouse citations) — [`.planning/phases/05-ecommerce-event-schema/05-RESEARCH.md`](../.planning/phases/05-ecommerce-event-schema/05-RESEARCH.md)
- Migration SQL — [`infra/clickhouse/sql/002_ecommerce_schema.sql`](../infra/clickhouse/sql/002_ecommerce_schema.sql)
