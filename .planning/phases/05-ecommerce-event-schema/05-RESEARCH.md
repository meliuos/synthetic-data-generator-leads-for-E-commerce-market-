# Phase 5: E-commerce Event Schema — Research

**Researched:** 2026-04-18
**Domain:** ClickHouse schema migration, projection design, materialized view evolution
**Confidence:** HIGH

---

## Summary

Phase 5 extends `analytics.click_events` (a `MergeTree` table with a Kafka-engine queue and a materialized view, defined in `infra/clickhouse/sql/001_events_schema.sql`) by adding 8 Nullable e-commerce columns, updating the materialized view to extract them from JSON, and adding server-side purchase dedup.

The additive `ALTER TABLE … ADD COLUMN IF NOT EXISTS` pattern works correctly on live `MergeTree` tables — it changes only the table structure and existing rows immediately read the new columns as NULL. `make schema` calls `scripts/apply-schema.sh` which pipes the SQL file to `clickhouse-client --multiquery`; the idempotent `IF NOT EXISTS` guards on every statement make repeated runs safe.

**Critical roadmap correction required:** The roadmap specifies a `ReplacingMergeTree(event_time)` *projection* keyed on `order_id`. ClickHouse projections cannot use a different engine than the base table; they inherit `MergeTree` storage. `ReplacingMergeTree` dedup on `order_id` must be a **secondary materialized view → sibling `ReplacingMergeTree` table**, not a projection. Similarly, `products[]` ARRAY JOIN cannot be expressed in a projection reliably — it also needs a secondary MV. Both are well-established ClickHouse patterns.

**Primary recommendation:** Use three SQL artifacts: (1) `ALTER TABLE` for the 8 new Nullable columns, (2) `CREATE OR REPLACE MATERIALIZED VIEW` for the updated MV query, (3) two new secondary MVs — one ARRAY-JOINing into `analytics.purchase_items` (flat per-line-item `MergeTree`), one deduping into `analytics.orders` (`ReplacingMergeTree(event_time)` keyed on `order_id`).

---

## Exact Current Schema

**Source file:** `infra/clickhouse/sql/001_events_schema.sql` (complete file, lines 1–98)

### `analytics.click_events` (MergeTree target)

```sql
-- infra/clickhouse/sql/001_events_schema.sql:3-25
CREATE TABLE IF NOT EXISTS analytics.click_events
(
    event_id         String,
    event_time       DateTime64(3, 'UTC'),
    received_at      DateTime64(3, 'UTC') DEFAULT now64(3),
    event_type       LowCardinality(String),
    page_url         String,
    referrer         Nullable(String),
    x_pct            Nullable(Float32),
    y_pct            Nullable(Float32),
    scroll_pct       Nullable(Float32),
    element_selector Nullable(String),
    element_tag      Nullable(String),
    device_type      LowCardinality(String),
    viewport_width   Nullable(UInt16),
    viewport_height  Nullable(UInt16),
    session_id       String,
    anonymous_user_id String,
    event_payload    String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (page_url, event_type, toDate(event_time));
```

### `analytics.events_queue` (Kafka engine)

```sql
-- infra/clickhouse/sql/001_events_schema.sql:30-41
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
```

### `analytics.events_mv` (Materialized View)

The MV reads from `analytics.events_queue` and writes to `analytics.click_events` using a `WITH` block that extracts fields from both flat top-level keys and `properties` nested JSON (`infra/clickhouse/sql/001_events_schema.sql:43-98`). The extraction pattern is:
1. Extract `properties` JSON as raw string: `ifNull(JSONExtractRaw(raw_message, 'properties'), '{}') AS properties_raw`
2. For each field, extract from flat first, then from `properties_raw` as fallback via `COALESCE` / `if(flat != '', flat, props)`.
3. Numeric types use `JSONExtract(…, 'Nullable(Float64)')` with `CAST … AS Nullable(Float32)` in SELECT.
4. String types use `JSONExtractString` with empty-string sentinel checks.

**Key observation (infra/clickhouse/sql/001_events_schema.sql:27-28):** The v1.0 script does `DROP VIEW IF EXISTS analytics.events_mv; DROP TABLE IF EXISTS analytics.events_queue;` before re-creating them. This is the existing idempotency pattern — but it creates a brief ingest gap. Phase 5 must NOT copy this drop-and-recreate approach; it should use `CREATE OR REPLACE MATERIALIZED VIEW` for the MV and `ALTER TABLE … ADD COLUMN IF NOT EXISTS` for the table.

---

## Column Type Decisions

All 8 new columns must be `Nullable` so v1.0 rows continue inserting without touching the e-commerce fields.

| Column | Recommended Type | Rationale | Retailrocket compatibility |
|--------|-----------------|-----------|---------------------------|
| `product_id` | `Nullable(String)` | SKU-style IDs are strings; Retailrocket `itemid` is UInt32 — we cast to String at MV level to accommodate both | DATASET.md: `itemid UInt32` → `toString(itemid)` |
| `category` | `Nullable(String)` | NOT `LowCardinality(Nullable(String))` for a new Nullable column on an existing table — see pitfall below. Plain `Nullable(String)` is safe | EVENTS.md: `category` is free-form string |
| `price` | `Nullable(Decimal(18,2))` | Decimal(18,2) is exact for monetary values; avoids Float64 rounding errors (0.1+0.2 != 0.3). Decimal(18,2) maps to Decimal64 — hardware-native, no emulation overhead. Scale=2 covers 2 decimal places for all major currencies | DATASET.md: price not in Retailrocket events — N/A |
| `quantity` | `Nullable(UInt32)` | Non-negative integer; max 4.29B covers any realistic order quantity. Matches Retailrocket `itemid` UInt32 cardinality hint | DATASET.md: `addtocart` has no quantity — treat as UInt32 |
| `order_id` | `Nullable(String)` | String to accommodate alphanumeric order IDs; Retailrocket `transactionid` is UInt32 → cast to String in unified view | DATASET.md: `transactionid Nullable(UInt32)` |
| `cart_value` | `Nullable(Decimal(18,2))` | Same rationale as `price`; represents running cart total | N/A |
| `search_query` | `Nullable(String)` | Free-form text; no LowCardinality (high cardinality, unique queries) | N/A — no search in Retailrocket |
| `results_count` | `Nullable(UInt32)` | Non-negative integer count | N/A |

**Why NOT `LowCardinality` for `category`:** `LowCardinality(Nullable(String))` is supported syntax (Tinybird research, confirmed current as of v25.2), BUT adding it via `ALTER TABLE ADD COLUMN` on an existing table with active inserts has triggered block-structure mismatch bugs in ClickHouse versions pre-24.8 (GitHub issue #47537). Since the existing table uses plain `Nullable(String)` for `referrer` and `element_selector`, stay consistent. `category` has bounded cardinality but simplicity and safety win here.

**Why Decimal over Float64 for price/cart_value:** Decimal arithmetic is exact on add/subtract/multiply (no floating-point drift). Float64 is fine for ML features but wrong for revenue accounting. Decimal(18,2) is Decimal64 — same underlying 64-bit int storage, no performance penalty. Division produces scale overflow; use `CAST(price / quantity AS Decimal(18,2))` explicitly. (Source: ClickHouse Decimal docs, verified 2026-04-18.)

---

## JSON Extraction Strategy

The existing v1.0 MV pattern is the template. For each new e-commerce field, add two `WITH` aliases following the same flat-then-properties fallback:

```sql
-- In the WITH block (matching infra/clickhouse/sql/001_events_schema.sql:47-79 pattern):
ifNull(JSONExtractString(raw_message, 'product_id'), '')   AS flat_product_id,
ifNull(JSONExtractString(properties_raw, 'product_id'), '') AS props_product_id,

ifNull(JSONExtractString(raw_message, 'category'), '')     AS flat_category,
ifNull(JSONExtractString(properties_raw, 'category'), '')  AS props_category,

JSONExtract(raw_message,    'price',    'Nullable(Float64)') AS flat_price,
JSONExtract(properties_raw, 'price',    'Nullable(Float64)') AS props_price,

JSONExtract(raw_message,    'quantity', 'Nullable(UInt32)') AS flat_quantity,
JSONExtract(properties_raw, 'quantity', 'Nullable(UInt32)') AS props_quantity,

ifNull(JSONExtractString(raw_message, 'order_id'), '')       AS flat_order_id,
ifNull(JSONExtractString(properties_raw, 'order_id'), '')    AS props_order_id,

JSONExtract(raw_message,    'cart_value', 'Nullable(Float64)') AS flat_cart_value,
JSONExtract(properties_raw, 'cart_value', 'Nullable(Float64)') AS props_cart_value,

-- RudderStack/Segment V2 uses 'query'; GA4 uses 'search_term' — extract both, COALESCE
ifNull(JSONExtractString(raw_message,    'query'), '')        AS flat_query,
ifNull(JSONExtractString(properties_raw, 'query'), '')        AS props_query,
ifNull(JSONExtractString(properties_raw, 'search_term'), '')  AS props_search_term,

JSONExtract(raw_message,    'results_count', 'Nullable(UInt32)') AS flat_results_count,
JSONExtract(properties_raw, 'results_count', 'Nullable(UInt32)') AS props_results_count

-- In SELECT:
nullIf(if(flat_product_id != '', flat_product_id, props_product_id), '')  AS product_id,
nullIf(if(flat_category   != '', flat_category,   props_category),   '')  AS category,
CAST(coalesce(flat_price,       props_price)       AS Nullable(Decimal(18,2))) AS price,
coalesce(flat_quantity,    props_quantity)                                 AS quantity,
nullIf(if(flat_order_id   != '', flat_order_id,   props_order_id),   '')  AS order_id,
CAST(coalesce(flat_cart_value,  props_cart_value)  AS Nullable(Decimal(18,2))) AS cart_value,
nullIf(if(flat_query != '', flat_query,
          if(props_query != '', props_query, props_search_term)), '')       AS search_query,
coalesce(flat_results_count, props_results_count)                          AS results_count
```

**`products[]` array extraction in the MV:** The main `click_events` table does NOT store `products[]` as a typed Array column — the raw JSON stays in `event_payload`. The secondary MV `purchase_items_mv` reads from `events_queue`, filters for `purchase` events, and uses `JSONExtractArrayRaw` + `ARRAY JOIN` to explode the array into per-line-item rows in a separate flat table. This is deliberate: adding `Array(Tuple(...))` to `click_events` would break the ORDER BY sort-key assumptions and complicate v1.0 heatmap queries.

---

## products[] ARRAY JOIN — Correct Approach (Secondary MV, Not Projection)

**Roadmap says:** "products[] ARRAY JOIN projection"
**Verified reality:** ClickHouse projections do not reliably support ARRAY JOIN. Issue #98953 (open as of research date) confirms ARRAY JOIN in projection indexes is not supported. The Altinity KB explicitly states projections "do not support many features (like indexes and FINAL)." The `by_item` projection in DATASET.md (for `retailrocket_raw.events`) uses `SELECT * ORDER BY (itemid, event_time, visitorid)` — a plain ORDER BY projection, not an ARRAY JOIN.

**Correct implementation:**

```sql
-- Sibling flat table for per-line-item purchase data
CREATE TABLE IF NOT EXISTS analytics.purchase_items
(
    event_id         String,
    event_time       DateTime64(3, 'UTC'),
    order_id         String,
    anonymous_user_id String,
    session_id       String,
    -- Per-item fields from products[] array
    product_id       String,
    sku              Nullable(String),
    name             Nullable(String),
    category         Nullable(String),
    price            Nullable(Decimal(18,2)),
    quantity         Nullable(UInt32),
    position         Nullable(UInt32),
    currency         Nullable(String)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(event_time)
ORDER BY (order_id, product_id, event_time);

-- Secondary MV that explodes products[] from the Kafka queue
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.purchase_items_mv
TO analytics.purchase_items
AS
WITH
    ifNull(JSONExtractRaw(raw_message, 'properties'), '{}') AS props,
    JSONExtractArrayRaw(props, 'products')                  AS products_arr,
    arrayJoin(if(notEmpty(products_arr), products_arr, ['{}'])) AS item_raw
SELECT
    ifNull(JSONExtractString(raw_message, 'messageId'),
           toString(generateUUIDv4()))                         AS event_id,
    ifNull(parseDateTime64BestEffortOrNull(
        ifNull(JSONExtractString(raw_message, 'timestamp'), ''), 3, 'UTC'),
        now64(3))                                              AS event_time,
    ifNull(JSONExtractString(props, 'order_id'), '')           AS order_id,
    ifNull(JSONExtractString(raw_message, 'anonymousId'), '')  AS anonymous_user_id,
    ifNull(JSONExtractString(raw_message, 'session_id'), '')   AS session_id,
    ifNull(JSONExtractString(item_raw, 'product_id'), '')      AS product_id,
    nullIf(JSONExtractString(item_raw, 'sku'), '')             AS sku,
    nullIf(JSONExtractString(item_raw, 'name'), '')            AS name,
    nullIf(JSONExtractString(item_raw, 'category'), '')        AS category,
    CAST(JSONExtract(item_raw, 'price', 'Nullable(Float64)')
         AS Nullable(Decimal(18,2)))                           AS price,
    JSONExtract(item_raw, 'quantity', 'Nullable(UInt32)')      AS quantity,
    JSONExtract(item_raw, 'position', 'Nullable(UInt32)')      AS position,
    nullIf(JSONExtractString(props, 'currency'), '')           AS currency
FROM analytics.events_queue
WHERE ifNull(JSONExtractString(raw_message, 'type'), '') = 'purchase'
   OR ifNull(JSONExtractString(raw_message, 'event'), '') = 'Order Completed';
```

The `arrayJoin(if(notEmpty(...), ..., ['{}']))` guard ensures the MV emits exactly one row even for non-array events that accidentally match the WHERE clause.

---

## ReplacingMergeTree Dedup — Correct Approach (Sibling Table MV, Not Projection)

**Roadmap says:** "ReplacingMergeTree(event_time) projection keyed on order_id"
**Verified reality:** ClickHouse projections inherit the base table engine (MergeTree). They cannot declare `ENGINE = ReplacingMergeTree(...)`. GitHub issues #24778 and #46968 confirm projections on `ReplacingMergeTree` base tables have known inconsistency bugs; projections are not a dedup mechanism.

**Correct implementation:** A secondary MV writes `purchase`-type events into a dedicated `analytics.orders` table with `ReplacingMergeTree(event_time)` keyed on `order_id`. Duplicate `order_id`s from network retries or back-button reloads are collapsed during background merges, with the highest `event_time` winning (latest-wins semantics).

```sql
CREATE TABLE IF NOT EXISTS analytics.orders
(
    order_id         String,
    event_time       DateTime64(3, 'UTC'),
    anonymous_user_id String,
    session_id       String,
    total            Nullable(Decimal(18,2)),
    revenue          Nullable(Decimal(18,2)),
    tax              Nullable(Decimal(18,2)),
    shipping         Nullable(Decimal(18,2)),
    discount         Nullable(Decimal(18,2)),
    currency         Nullable(String),
    coupon           Nullable(String),
    products_json    String   -- raw products array, preserved for debugging
)
ENGINE = ReplacingMergeTree(event_time)
PARTITION BY toYYYYMM(event_time)
ORDER BY order_id;

CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.orders_mv
TO analytics.orders
AS
WITH
    ifNull(JSONExtractRaw(raw_message, 'properties'), '{}') AS props
SELECT
    ifNull(JSONExtractString(props, 'order_id'), '')          AS order_id,
    ifNull(parseDateTime64BestEffortOrNull(
        ifNull(JSONExtractString(raw_message, 'timestamp'), ''), 3, 'UTC'),
        now64(3))                                             AS event_time,
    ifNull(JSONExtractString(raw_message, 'anonymousId'), '') AS anonymous_user_id,
    ifNull(JSONExtractString(raw_message, 'session_id'), '')  AS session_id,
    CAST(JSONExtract(props, 'total',    'Nullable(Float64)') AS Nullable(Decimal(18,2))) AS total,
    CAST(JSONExtract(props, 'revenue',  'Nullable(Float64)') AS Nullable(Decimal(18,2))) AS revenue,
    CAST(JSONExtract(props, 'tax',      'Nullable(Float64)') AS Nullable(Decimal(18,2))) AS tax,
    CAST(JSONExtract(props, 'shipping', 'Nullable(Float64)') AS Nullable(Decimal(18,2))) AS shipping,
    CAST(JSONExtract(props, 'discount', 'Nullable(Float64)') AS Nullable(Decimal(18,2))) AS discount,
    nullIf(JSONExtractString(props, 'currency'), '')          AS currency,
    nullIf(JSONExtractString(props, 'coupon'), '')            AS coupon,
    ifNull(JSONExtractRaw(props, 'products'), '[]')           AS products_json
FROM analytics.events_queue
WHERE ifNull(JSONExtractString(raw_message, 'type'), '') = 'purchase'
   OR ifNull(JSONExtractString(raw_message, 'event'), '') = 'Order Completed';
```

**Querying deduplicated orders:** Use `SELECT … FROM analytics.orders FINAL` for exact dedup, or `GROUP BY order_id` with `argMax(total, event_time)` for performance-critical paths (FINAL is slower but safe at this scale).

---

## GA4 Alias Exposure — Companion VIEW (Not Computed Columns)

**Decision:** Use a `CREATE VIEW` (not `MATERIALIZED COLUMN` on the base table) for GA4 aliases. Rationale:
- Computed/MATERIALIZED columns add physical storage and slow down inserts on `click_events`.
- A VIEW is zero-storage, zero-write-overhead, and the GA4 alias remapping is a read-time concern.
- Only downstream consumers that explicitly need GA4 shape should query the view; v1.2 lead scoring queries directly against `click_events` columns using the RudderStack names.

```sql
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
    product_id        AS item_id,
    category          AS item_category,
    price,
    quantity,
    order_id          AS transaction_id,
    cart_value,
    search_query      AS search_term,
    results_count
FROM analytics.click_events;
```

For the `items[]` alias (GA4 uses `items[]` vs Segment's `products[]`), downstream consumers join against `analytics.purchase_items` and alias the result — no separate storage needed.

---

## Idempotent Migration Strategy

**The `make schema` target** calls `bash scripts/apply-schema.sh` which pipes `infra/clickhouse/sql/001_events_schema.sql` to `clickhouse-client --multiquery` (`scripts/apply-schema.sh:15`).

**Problem with current v1.0 script:** Lines 27-28 do `DROP VIEW IF EXISTS analytics.events_mv; DROP TABLE IF EXISTS analytics.events_queue;` before recreating. This causes a brief ingest gap every time `make schema` runs. For v1.1, the new schema file must NOT drop and recreate these objects.

**Recommended idempotent migration pattern for `002_ecommerce_schema.sql`:**

```sql
-- 1. Additive column additions (instantaneous, no data rewrite)
ALTER TABLE analytics.click_events
    ADD COLUMN IF NOT EXISTS product_id    Nullable(String)         AFTER event_payload,
    ADD COLUMN IF NOT EXISTS category      Nullable(String)         AFTER product_id,
    ADD COLUMN IF NOT EXISTS price         Nullable(Decimal(18,2))  AFTER category,
    ADD COLUMN IF NOT EXISTS quantity      Nullable(UInt32)         AFTER price,
    ADD COLUMN IF NOT EXISTS order_id      Nullable(String)         AFTER quantity,
    ADD COLUMN IF NOT EXISTS cart_value    Nullable(Decimal(18,2))  AFTER order_id,
    ADD COLUMN IF NOT EXISTS search_query  Nullable(String)         AFTER cart_value,
    ADD COLUMN IF NOT EXISTS results_count Nullable(UInt32)         AFTER search_query;

-- 2. Sibling tables (IF NOT EXISTS guards make this idempotent)
CREATE TABLE IF NOT EXISTS analytics.purchase_items ( … );
CREATE TABLE IF NOT EXISTS analytics.orders ( … );

-- 3. Replace the main MV query (atomic swap, no ingest gap)
CREATE OR REPLACE MATERIALIZED VIEW analytics.events_mv
TO analytics.click_events
AS … (updated SELECT with new e-commerce columns);

-- 4. Secondary MVs (IF NOT EXISTS guards)
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.purchase_items_mv
TO analytics.purchase_items AS …;

CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.orders_mv
TO analytics.orders AS …;

-- 5. GA4 alias view
CREATE OR REPLACE VIEW analytics.click_events_ga4 AS …;
```

**`apply-schema.sh` update:** The script currently takes a single SQL file argument (`SQL_FILE=${1:-infra/clickhouse/sql/001_events_schema.sql}`). The `make schema` target should be updated to run both files in sequence, or a new `make schema-v11` target added. Option B (new target) is safer — it does not risk breaking the existing v1.0 `make schema` smoke test.

**Second-run idempotency:** `ADD COLUMN IF NOT EXISTS` is a no-op on second run (confirmed: ClickHouse ALTER docs). `CREATE TABLE IF NOT EXISTS` is a no-op. `CREATE OR REPLACE` always replaces cleanly. `CREATE MATERIALIZED VIEW IF NOT EXISTS` skips on second run.

---

## Common Pitfalls

### Pitfall 1: `CREATE OR REPLACE` MV has a brief ingest gap
**What goes wrong:** `CREATE OR REPLACE MATERIALIZED VIEW` replaces the MV atomically at the metadata level. Events in the Kafka topic that arrive between the old MV's last read and the new MV's first read are processed correctly — the Kafka consumer (`events_queue`) keeps its offset independently. There is NO data gap for events already in Kafka. Events that arrived before the migration and were not yet consumed will be consumed by the new MV with the new SELECT, which is the desired behavior.
**How to avoid:** Apply the `ALTER TABLE ADD COLUMN` statements BEFORE `CREATE OR REPLACE` so the destination columns exist when the new MV begins writing.
**Warning sign:** `Cannot insert NULL to non-Nullable column` errors in ClickHouse logs — means ADD COLUMN ran after CREATE OR REPLACE.

### Pitfall 2: DROP + recreate the Kafka table kills in-flight messages
**What goes wrong:** v1.0's `DROP TABLE IF EXISTS analytics.events_queue` resets the Kafka consumer group offset. Any messages in the topic that haven't been consumed yet are skipped or reprocessed from the start depending on `auto.offset.reset`.
**How to avoid:** Never drop `events_queue` in `002_ecommerce_schema.sql`. The Kafka engine table is not modified by Phase 5.

### Pitfall 3: Projection MATERIALIZE blocks writes
**What goes wrong:** `ALTER TABLE … MATERIALIZE PROJECTION` is implemented as a mutation. On large tables it runs as a background merge mutation and can saturate I/O, slowing insert throughput. For `click_events` at typical dev-environment scale this is manageable, but for production it should be run at low-traffic hours.
**Note:** Phase 5 does NOT add any ORDER BY projections to `click_events` — the dedup and ARRAY JOIN work is done in secondary MVs. This pitfall applies if a future phase adds a projection for query acceleration.

### Pitfall 4: Decimal arithmetic in SELECT requires explicit CAST
**What goes wrong:** `JSONExtract` returns `Nullable(Float64)`. `CAST(… AS Nullable(Decimal(18,2)))` loses precision if the Float64 representation is imprecise (e.g., 24.99 stored as 24.989999…). At 2 decimal places this is acceptable for most prices, but it is a known limitation. Division operations (e.g., average price) produce `Decimal(18,2) / UInt32 = Decimal(18,6)` — the result scale expands.
**How to avoid:** Accept the Float64→Decimal conversion loss as inherent in JSON-sourced data. Do not attempt to store JSON strings as Decimal natively — there is no `JSONExtractDecimal` function; Float64 is the only numeric extraction type.

### Pitfall 5: `events_mv` MV query change does not backfill history
**What goes wrong:** `CREATE OR REPLACE MATERIALIZED VIEW` updates the MV query going forward. Historical rows already in `click_events` will have NULL in the new columns forever — the MV is not applied retroactively.
**How to avoid:** This is expected behavior. Document it: "E-commerce columns are populated only for events received after the Phase 5 schema migration. Historical v1.0 rows will have NULL in all 8 new columns." No action needed.

### Pitfall 6: `ORDER BY` columns cannot be dropped or retyped
**What goes wrong:** `click_events` ORDER BY is `(page_url, event_type, toDate(event_time))`. None of the 8 new columns are in the ORDER BY, so this is not a concern for Phase 5. But any attempt to `ALTER TABLE … MODIFY COLUMN event_type` (e.g., changing from `LowCardinality` to plain `String`) would require a table rebuild.
**How to avoid:** Only add new columns — never modify existing column types. Phase 5 adds columns AFTER `event_payload`, which is safe.

---

## Architecture Patterns

### Project Structure for Phase 5

```
infra/
└── clickhouse/
    └── sql/
        ├── 001_events_schema.sql    # v1.0 — DO NOT MODIFY
        └── 002_ecommerce_schema.sql # v1.1 Phase 5 — NEW
scripts/
└── apply-schema.sh                  # accepts SQL_FILE arg; update make schema target
Makefile                             # add schema-v11 target
```

### Pattern: Secondary MV for Derived Views

Instead of projections (which have severe limitations), Phase 5 uses three secondary MVs reading from the same `events_queue` Kafka table:

1. **`events_mv`** → `click_events` (existing, updated via `CREATE OR REPLACE`)
2. **`purchase_items_mv`** → `purchase_items` (new, ARRAY JOIN exploder)
3. **`orders_mv`** → `orders` (new, ReplacingMergeTree dedup)

All three MVs share the same Kafka source (`analytics.events_queue`). ClickHouse fans out writes from a single Kafka engine table to multiple MVs simultaneously.

### Pattern: GA4 Alias via View

```sql
CREATE OR REPLACE VIEW analytics.click_events_ga4 AS
SELECT product_id AS item_id, order_id AS transaction_id, search_query AS search_term, … 
FROM analytics.click_events;
```

Zero storage overhead. Consumers with GA4-shaped queries use `click_events_ga4`; RudderStack/Segment-shaped consumers use `click_events` directly.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Purchase dedup | Custom Python dedup layer | `ReplacingMergeTree(event_time)` in `analytics.orders` | Server-side, no extra service, standard ClickHouse idiom |
| Per-line-item flattening | `ARRAY JOIN` projection on `click_events` | Secondary MV → `analytics.purchase_items` | Projections don't support ARRAY JOIN reliably |
| GA4 alias remapping | Duplicate columns in `click_events` | `CREATE OR REPLACE VIEW analytics.click_events_ga4` | Zero storage, zero write overhead |
| Idempotent migrations | Custom "check-before-alter" scripts | `ADD COLUMN IF NOT EXISTS` + `CREATE OR REPLACE` + `CREATE … IF NOT EXISTS` | Native ClickHouse guards — atomic and safe |

---

## State of the Art

| Old Approach (v1.0 script) | Phase 5 Approach | Impact |
|---------------------------|------------------|--------|
| `DROP VIEW + DROP TABLE + CREATE` for idempotency | `ADD COLUMN IF NOT EXISTS` + `CREATE OR REPLACE` | No ingest gap, offset preserved |
| Single SQL file `001_events_schema.sql` | New `002_ecommerce_schema.sql` alongside v1.0 | v1.0 `make schema` unchanged; v1.1 runs new file |
| No purchase tracking | `analytics.orders` ReplacingMergeTree + `analytics.purchase_items` flat table | Server-side dedup and per-line-item queries |

---

## Open Questions

1. **`make schema` target wiring**
   - What we know: `make schema` calls `bash scripts/apply-schema.sh` which defaults to `001_events_schema.sql` (`Makefile:20`, `scripts/apply-schema.sh:4`).
   - What's unclear: Should Phase 5 add a `schema-v11` Make target that runs `002_ecommerce_schema.sql`, or should the existing `schema` target run all `*.sql` files in order?
   - Recommendation: Add a `schema-v11` target. Keeps v1.0 `make schema` intact for the smoke test. `make schema-v11` runs `002_ecommerce_schema.sql`. A top-level `schema-all` can chain both.

2. **`events_mv` and `events_queue` recreation in `001_events_schema.sql`**
   - What we know: `001_events_schema.sql:27-28` drops and recreates the MV and Kafka table unconditionally.
   - What's unclear: Do the v1.0 SUMMARY files document that `make schema` is safe to rerun against live data?
   - Recommendation: Phase 5 should NOT modify `001_events_schema.sql`. The new `002_ecommerce_schema.sql` uses only safe idempotent operations. The existing drop-recreate in v1.0 is a known wart — document it but don't fix it in Phase 5 scope.

---

## Sources

### Primary (HIGH confidence — directly read from codebase)
- `infra/clickhouse/sql/001_events_schema.sql` — complete v1.0 DDL (lines 1–98)
- `scripts/apply-schema.sh` — `make schema` implementation (lines 1–16)
- `Makefile` — `schema` target definition (line 20)
- `.planning/research/v1.1/EVENTS.md` — canonical event vocabulary, property shapes, dedup requirements
- `.planning/research/v1.1/DATASET.md` — Retailrocket column types, recommended DDL patterns, ReplacingMergeTree idempotency pattern
- `.planning/STATE.md` — locked decisions (additive ALTER, defence-in-depth dedup, GA4 alias via MV)

### Secondary (HIGH confidence — official docs verified 2026-04-18)
- [ClickHouse ALTER COLUMN docs](https://clickhouse.com/docs/sql-reference/statements/alter/column) — `ADD COLUMN IF NOT EXISTS` syntax, instant metadata-only change
- [ClickHouse ALTER VIEW docs](https://clickhouse.com/docs/sql-reference/statements/alter/view) — `MODIFY QUERY` limitations; `CREATE OR REPLACE` is the safe path
- [ClickHouse Decimal docs](https://clickhouse.com/docs/sql-reference/data-types/decimal) — arithmetic rules, overflow, CAST requirements
- [ClickHouse Projection docs](https://clickhouse.com/docs/sql-reference/statements/alter/projection) — `MATERIALIZE PROJECTION` is a mutation; projections require MergeTree base
- [ClickHouse ReplacingMergeTree docs](https://clickhouse.com/docs/engines/table-engines/mergetree-family/replacingmergetree) — version column syntax, dedup-on-merge semantics
- [oneuptime.com — How to Alter Materialized Views in ClickHouse (2026-03-31)](https://oneuptime.com/blog/post/2026-03-31-clickhouse-alter-materialized-views/view) — `CREATE OR REPLACE` atomic swap pattern
- [Altinity KB — Projections](https://kb.altinity.com/altinity-kb-queries-and-syntax/projections-examples/) — projections cannot use FINAL, don't support ARRAY JOIN
- [Tinybird — LowCardinality NULL behavior](https://www.tinybird.co/blog/tips-10-null-behavior-with-lowcardinality-columns) — `LowCardinality(Nullable(String))` correct nesting order

### Tertiary (MEDIUM confidence — GitHub issues, search-verified)
- [GitHub #98953 — ARRAY JOIN in projection indexes not supported](https://github.com/ClickHouse/ClickHouse/issues/98953)
- [GitHub #24778 — Projections inconsistent with ReplacingMergeTree](https://github.com/ClickHouse/ClickHouse/issues/24778)
- [GitHub #46968 — Projections not used in ReplacingMergeTree](https://github.com/ClickHouse/ClickHouse/issues/46968)

---

## Metadata

**Confidence breakdown:**
- Current schema (exact DDL): HIGH — read directly from `infra/clickhouse/sql/001_events_schema.sql`
- Column type decisions: HIGH — ClickHouse official docs + EVENTS.md + DATASET.md cross-referenced
- JSON extraction strategy: HIGH — directly mirrors existing v1.0 MV pattern
- products[] ARRAY JOIN via secondary MV: HIGH — official docs + confirmed GitHub issues on projection limitations
- ReplacingMergeTree via secondary MV: HIGH — confirmed projections cannot use different engines
- `CREATE OR REPLACE` MV swap: HIGH — official docs + recent blog post (2026-03-31)
- Idempotent migration pattern: HIGH — `IF NOT EXISTS` guards verified in official docs
- Pitfalls: HIGH — each grounded in specific ClickHouse behavior documentation

**Research date:** 2026-04-18
**Valid until:** 2026-05-18 (ClickHouse stable; projection limitations unlikely to change in 30 days)
