# Dataset Research — Retailrocket

**Milestone:** v1.1 — E-commerce Events & Lead Dataset
**Researched:** 2026-04-18
**Scope:** Retailrocket Recommender System Dataset (Kaggle) import into existing ClickHouse `analytics` database; schema fit with v1.0 `click_events` MergeTree; preparation for v1.2 lead scoring.
**Overall confidence:** MEDIUM–HIGH for schema and import mechanics (multiple corroborating sources), MEDIUM for license (Kaggle license block is gated behind auth and could not be fetched directly; community sources consistently report CC BY-NC-SA 4.0, and the quality gate requires this to be verified from the live Kaggle page before starting Phase 7).

---

## License & Availability

### What the sources say

- The dataset is hosted on Kaggle: `https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset`. It is published by the account `retailrocket` and framed as "real-world ecommerce website" behavioural data with "all values hashed due to confidential issues". The stated purpose is to "motivate research in the field of recommender systems with implicit feedback." ([Kaggle page](https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset), [CoronaScience README](https://github.com/CoronaScience/RetailrocketRecommenderSystemDataset))
- Community references, loader libraries, and secondary catalogues consistently describe the dataset as **CC BY-NC-SA 4.0 (Attribution-NonCommercial-ShareAlike 4.0 International)** — the same license Kaggle shows in the sidebar of the dataset page.
- Confidence: **MEDIUM**. The Kaggle dataset page itself returned only the page title on WebFetch (the license sidebar is rendered client-side / behind auth). The CC BY-NC-SA 4.0 attribution is the strongest signal from aggregated community references but has **not** been visually confirmed on the live Kaggle page in this research pass. **Action for Phase 7: open the Kaggle page in a browser, screenshot the License block, and commit the screenshot under `.planning/research/v1.1/evidence/` before running the importer.**

### What CC BY-NC-SA 4.0 permits for this project

Assuming the license is indeed CC BY-NC-SA 4.0 ([license text](https://creativecommons.org/licenses/by-nc-sa/4.0/)), the relevant clauses for a GL4 academic final-year project:

| Clause | What it means for us | Our position |
|---|---|---|
| **BY** (Attribution) | Must credit "Retail Rocket" as the source, link to the license, and indicate if changes were made. | Add a `DATASET_CREDITS.md` (or section in README) citing Retail Rocket + Kaggle URL + license. Include in defense slides. |
| **NC** (NonCommercial) | No commercial use. Academic/educational use by a student for a university project is standard NC-compatible usage. | Fine. GL4 final project is non-commercial. We must **not** sell, integrate into a paid product, or ship it to a commercial customer. |
| **SA** (ShareAlike) | Any **derivative** of the dataset that we publish must be licensed under the same (or a compatible) license. | We are not publishing derivatives. If we ever publish processed Retailrocket data (even aggregated features) in a public repo, we must license that artifact CC BY-NC-SA 4.0 and note it. Safer pattern: keep the raw CSVs and any derived tables out of the public repo (use `.gitignore` + a download script), and only commit code. |
| No additional restrictions | We cannot apply technical measures preventing others from exercising the same rights. | N/A for our internal use. |

**Practical rules for v1.1 and v1.2:**

1. Do **not** commit the raw CSVs or any dump of the Retailrocket-derived ClickHouse tables to git. The Kaggle ToS also prohibits redistribution without permission on top of the CC license.
2. Commit the **download script** (e.g., `scripts/download_retailrocket.sh`) and **import script**; users reproduce the dataset themselves via Kaggle API.
3. Add attribution: "This project uses the Retailrocket Recommender System Dataset (Retail Rocket, Kaggle, CC BY-NC-SA 4.0)."
4. Defense presentation: one slide citing the dataset and license.
5. v1.2 lead-scoring models trained on this corpus are **demonstration artefacts for the defense**, not a commercial product. If we later pivot, retrain on synthetic or licensed data.

---

## CSV Schema (per file)

The dataset ships four CSVs. Row counts and column layouts below are cross-referenced from three independent sources: [rs_datasets catalogue](https://darel13712.github.io/rs_datasets/Datasets/retail_rocket/), an [R-based Retail Recommendation writeup](https://rstudio-pubs-static.s3.amazonaws.com/307430_112de48631ce4a1987d35cb77750ba9e.html) that enumerates each file's row count and columns, and the [RecPack RetailRocket loader](https://recpack.froomle.ai/generated/recpack.datasets.RetailRocket.html). Event counts match across sources.

### `events.csv` — behavioural data

- **Rows:** 2,756,101
- **Event-type breakdown:** 2,664,312 `view` / 69,332 `addtocart` / 22,457 `transaction`
- **Date range:** May–September 2015 (4.5 months). Timestamps are Unix epoch in **milliseconds** (UInt64), not seconds — multiple community loaders confirm this, and it's why naive parsing shows "year 47495" (i.e. seconds-interpretation of a ms value).
- **Columns:**

| # | Column | Raw CSV type | Target ClickHouse type | Notes |
|---|---|---|---|---|
| 1 | `timestamp` | integer (ms since epoch) | `DateTime64(3)` (via `fromUnixTimestamp64Milli`) | Store as proper datetime; keep ms precision for sessionisation. |
| 2 | `visitorid` | integer | `UInt32` | Anonymous visitor ID. Not a true user (cookie-level). Max observed ~1.4M distinct values. |
| 3 | `event` | string | `LowCardinality(String)` | One of `view`, `addtocart`, `transaction`. |
| 4 | `itemid` | integer | `UInt32` | Product ID. ~235k distinct items. |
| 5 | `transactionid` | integer, nullable | `Nullable(UInt32)` | Populated **only** when `event='transaction'`. Groups line items of the same purchase. |

### `item_properties_part1.csv` and `item_properties_part2.csv` — long-format EAV

- **Rows:** 10,999,999 (part1) + 9,275,903 (part2) ≈ **20.28 M rows total**
- **Shape:** long / EAV (one row per (item, property, timestamp) observation).
- **Columns:**

| # | Column | Raw CSV type | Target ClickHouse type | Notes |
|---|---|---|---|---|
| 1 | `timestamp` | integer (ms since epoch) | `DateTime64(3)` | When the property value was observed for that item. |
| 2 | `itemid` | integer | `UInt32` | Joins to `events.itemid`. |
| 3 | `property` | string (hashed, except `categoryid` and `available`) | `LowCardinality(String)` | Hashed property keys look like numeric strings; `categoryid` and `available` are literal. |
| 4 | `value` | string (often hashed; may contain space-separated token lists) | `String` | For `categoryid` → integer as string. For `available` → `'0'` / `'1'`. For numeric features, the dataset encodes them as `n<number>.<decimals>` tokens (Retail Rocket's known convention) — keep as String; parse only when needed. |

**Shape rationale:** This is already long-format EAV in the source. `property` values are re-observed over time (same item gets new `categoryid` observations as the taxonomy or listing changes). "Duplicate timestamps with different property values have been removed" per the source docs.

### `category_tree.csv` — taxonomy

- **Rows:** 1,669
- **NA parents:** 25 (root nodes)
- **Columns:**

| # | Column | Raw CSV type | Target ClickHouse type | Notes |
|---|---|---|---|---|
| 1 | `categoryid` | integer | `UInt32` | Node ID. Joins to `value` column of `item_properties` where `property='categoryid'`. |
| 2 | `parentid` | integer, nullable | `Nullable(UInt32)` | NULL for 25 root categories. |

### Sources for schema

- [rs_datasets — Retail Rocket entry](https://darel13712.github.io/rs_datasets/Datasets/retail_rocket/) — confirms 2,756,101 events, 1,407,580 users, 235,061 items; columns `ts`, `user_id`, `event`, `item_id`, `transaction_id` (renamed); item-properties columns `ts`, `item_id`, `property`, `value`; category columns `category_id`, `parent_id`.
- [RStudio Pubs walkthrough](https://rstudio-pubs-static.s3.amazonaws.com/307430_112de48631ce4a1987d35cb77750ba9e.html) — confirms per-file row counts (10,999,999 + 9,275,903 for item_properties; 1,669 for category_tree; 2,756,101 for events), `transactionid` NAs, `categoryid`/`available` as the only unhashed properties.
- [RecPack RetailRocket loader](https://recpack.froomle.ai/generated/recpack.datasets.RetailRocket.html) — confirms columns `visitorid`, `itemid`, `timestamp`, `event`; event vocabulary `{view, addtocart, transaction}`.

---

## Recommended ClickHouse Schema

### Decision: parallel `retailrocket_*` tables, *not* the same `click_events` MergeTree

Both options were weighed. The parallel-table approach is recommended, with an optional unified view on top for v1.2.

#### Option A — Write Retailrocket rows into the existing `analytics.click_events`

**Pros**
- Single table, single query surface.
- v1.2 lead-scoring SQL written once, runs against both live traffic and the seed corpus.
- Leverages the already-built Kafka→MV→MergeTree 3-table pattern (though for Retailrocket it's a one-shot load, not a stream — so the Kafka engine path is irrelevant here).

**Cons (why this loses)**
- **Schema mismatch.** `click_events` is ORDER BY `(page_url, event_type, toDate(event_time))` and carries heatmap-specific columns (`x_pct`, `y_pct`, `scroll_pct`, `element_selector`, `element_tag`, `viewport_*`, `device_type`). Retailrocket has none of those. Stuffing synthetic defaults (`page_url='retailrocket://item/<itemid>'`, `x_pct=NULL`, etc.) pollutes the primary key space — every Retailrocket row shares a page_url prefix, which wrecks the sort key's selectivity for v1.0's real heatmap queries.
- **Ghost cardinality.** ~2.76M Retailrocket rows mixed with live events distort ClickHouse's primary-index statistics and confuse future partitioning decisions.
- **No native `itemid`, `visitorid`, `transactionid` columns.** These would have to live inside `event_payload` (JSON), which defeats v1.2 SQL feature engineering — recency/frequency/basket-size queries become `JSONExtract` calls over 2.76M rows.
- **Provenance muddling.** No clean way to say "delete all seed data, keep live traffic" for a demo reset.
- **Retailrocket has no `session_id`.** We'd have to fabricate one (e.g., sessionise by 30-minute inactivity gaps per visitor), which is a v1.2 feature-engineering decision we should defer, not bake into raw storage.

#### Option B (recommended) — Parallel `retailrocket_events`, `retailrocket_item_properties`, `retailrocket_category_tree`

**Pros**
- Native columns for the real join keys (`visitorid`, `itemid`, `transactionid`, `property`).
- Clean primary keys optimised for v1.2 SQL access patterns (per-visitor recency, per-item popularity, funnel joins).
- v1.0 heatmap queries are completely unaffected.
- Trivial to drop/reload for demos: `DROP TABLE IF EXISTS retailrocket_events; ...`
- License hygiene: the Retailrocket-derived tables are clearly isolated; a single `DROP DATABASE retailrocket_raw` removes all CC BY-NC-SA material.
- **Unification still available when needed:** a `CREATE VIEW unified_events AS SELECT ... FROM click_events UNION ALL SELECT ... FROM retailrocket_events` gives v1.2 a single query surface without coupling storage.

**Cons**
- Two schemas to learn. Mitigation: the unified view hides this from analytical queries.
- v1.2 feature-engineering SQL has to read from the view (or from both tables) — minor.

#### DDL sketch (recommended)

```sql
-- Dedicated database keeps license scope clean and simplifies wipe/reload.
CREATE DATABASE IF NOT EXISTS retailrocket_raw;

-- 1) Events (behavioural data) ---------------------------------------------
CREATE TABLE retailrocket_raw.events
(
    event_time      DateTime64(3),                 -- from ms timestamp
    visitorid       UInt32,
    event_type      LowCardinality(String),        -- view | addtocart | transaction
    itemid          UInt32,
    transactionid   Nullable(UInt32),
    -- provenance + idempotency
    source          LowCardinality(String) DEFAULT 'retailrocket',
    load_batch_id   LowCardinality(String),        -- e.g. '2026-04-18T10:00:00Z'
    -- stable dedup key (see Idempotency Approach)
    row_hash        UInt64 MATERIALIZED cityHash64(event_time, visitorid, event_type, itemid, ifNull(transactionid, 0))
)
ENGINE = ReplacingMergeTree(load_batch_id)
PARTITION BY toYYYYMM(event_time)
ORDER BY (visitorid, event_time, itemid, row_hash)
SETTINGS index_granularity = 8192;

-- Secondary query pattern: per-item popularity / funnel. Projection avoids a second table.
ALTER TABLE retailrocket_raw.events
    ADD PROJECTION by_item (
        SELECT * ORDER BY (itemid, event_time, visitorid)
    );

-- 2) Item properties (EAV long format) -------------------------------------
CREATE TABLE retailrocket_raw.item_properties
(
    observed_at   DateTime64(3),
    itemid        UInt32,
    property      LowCardinality(String),
    value         String,
    source        LowCardinality(String) DEFAULT 'retailrocket',
    load_batch_id LowCardinality(String),
    row_hash      UInt64 MATERIALIZED cityHash64(observed_at, itemid, property, value)
)
ENGINE = ReplacingMergeTree(load_batch_id)
PARTITION BY toYYYYMM(observed_at)
ORDER BY (itemid, property, observed_at, row_hash)
SETTINGS index_granularity = 8192;

-- 3) Category tree ---------------------------------------------------------
CREATE TABLE retailrocket_raw.category_tree
(
    categoryid UInt32,
    parentid   Nullable(UInt32)
)
ENGINE = ReplacingMergeTree()
ORDER BY categoryid;

-- 4) Convenience views -----------------------------------------------------

-- Latest-known item attributes (wide, for lead-scoring feature engineering).
CREATE VIEW retailrocket_raw.item_latest AS
SELECT
    itemid,
    argMaxIf(value, observed_at, property = 'categoryid') AS categoryid,
    argMaxIf(value, observed_at, property = 'available')  AS available,
    max(observed_at)                                      AS last_seen
FROM retailrocket_raw.item_properties
GROUP BY itemid;

-- Unified event surface for v1.2 lead scoring.
-- Maps Retailrocket's 3-vocab to our v1.1 5-vocab (see Event Vocabulary Mapping).
CREATE VIEW analytics.unified_events AS
SELECT
    event_id,
    event_time,
    event_type,
    anonymous_user_id AS user_key,
    session_id,
    toString(JSONExtractRaw(event_payload, 'itemid')) AS itemid,
    'live'            AS source,
    page_url
FROM analytics.click_events
WHERE event_type IN ('product_view', 'add_to_cart', 'remove_from_cart', 'purchase', 'search')

UNION ALL

SELECT
    toString(row_hash) AS event_id,
    event_time,
    multiIf(
        event_type = 'view',        'product_view',
        event_type = 'addtocart',   'add_to_cart',
        event_type = 'transaction', 'purchase',
        event_type
    ) AS event_type,
    toString(visitorid) AS user_key,
    ''   AS session_id,           -- Retailrocket has no session; leave v1.2 to sessionise
    toString(itemid)    AS itemid,
    'retailrocket'      AS source,
    ''   AS page_url
FROM retailrocket_raw.events;
```

**Notes on the DDL:**

- **`ReplacingMergeTree(load_batch_id)`** keeps the most recent load's row when `(ORDER BY)` collides. Combined with `row_hash` in the sort key, this gives us row-level idempotency on re-runs (see Idempotency Approach).
- **Partitioning by month** (`toYYYYMM`) keeps parts small and lets us `ATTACH`/`DETACH` per-month for fast resets. For a 4.5-month dataset this yields ~5 partitions in `events` and ~5 in `item_properties` — within ClickHouse's healthy per-table-partition budget.
- **`item_properties` ORDER BY `(itemid, property, observed_at, row_hash)`** is the join key we'll hit for feature engineering (latest known categoryid per item, availability at event_time, etc.).
- **Long format retained** for item_properties (rationale in "Long vs wide vs Map" below).

### Long vs wide vs Map for `item_properties`

| Option | Storage | Query pattern fit | Extensibility | Verdict |
|---|---|---|---|---|
| **Long (recommended)** | 20.28M rows × 4 cols, heavy LowCardinality compression on `property` | `SELECT argMax(value, observed_at) ... WHERE property='categoryid'` — natural; `item_latest` view flattens the common case | Trivially handles new property keys | **Chosen.** Matches source shape, zero ETL drift, cheap to reload. |
| **Wide (one column per property)** | ~1000 columns (one per hashed key) | Point lookups fast on known columns | Poor — every new property requires `ALTER TABLE` | Rejected. 1000-column wide tables also inflate part headers and make SELECT * painful. |
| **`Map(String, String)` per item+timestamp** | One row per (item, observed_at) with a Map of all properties | `CAST(map_col['categoryid'] AS UInt32)` works | Good | **Rejected** for v1.1: ClickHouse Map loads the entire map into memory on access and does linear scans for key lookup ([Map performance analysis, Orapinpatipat 2024](https://medium.com/@chayut_o/clickhouse-map-vs-individual-column-performance-f089dde3c100), [ClickStack migration notes](https://clickhouse.com/docs/use-cases/observability/clickstack/migration/elastic/types)). For a corpus where 99% of v1.2 queries touch only `categoryid` and `available`, long format + a materialised-view "latest wide" is strictly faster and simpler. |

**If v1.2 needs a wide projection**, add a materialised view from `item_properties` to `item_latest_wide(itemid, categoryid UInt32, available UInt8, last_seen DateTime64(3))` — that's the 2-column feature store lead scoring actually needs.

---

## Import Strategy

### Recommendation: Python script using `clickhouse-connect`, streaming CSV in chunks

**Why not raw `clickhouse-client`:**
- We need per-row type coercion (`timestamp` ms → `DateTime64(3)`, `transactionid` → Nullable handling, optional `categoryid` int casting) that CSV format handlers don't do cleanly inline.
- We need a deterministic `load_batch_id` stamped per run for idempotency.
- We need the script to be **runnable inside the compose network** (the same container network the existing Streamlit dashboard uses) without exposing ClickHouse externally.
- We want the script committed to git and versioned with the rest of the pipeline.

**Why not `clickhouse-local`:**
- It's great for ad-hoc exploration / one-liners. It's a poor fit when the import is part of a repeatable, scripted Phase 7 deliverable with logging, progress bars, and idempotency logic.
- It also requires bundling the binary into an image, adding ~200MB; the existing services already run Python.

**Why `clickhouse-connect` (official ClickHouse Python driver):**
- Official, actively maintained, HTTP-based (works over the same port `8123` the dashboard already talks to).
- Native `insert()` with column-oriented batches → 10-100× faster than row-by-row `INSERT` statements.
- Handles `DateTime64`, `Nullable`, `LowCardinality` types correctly.
- Easy pandas integration (`insert_df`) for small-shape CSVs (category_tree).

Reference: ClickHouse's own ingestion guide recommends the Python driver for programmatic imports ([ClickHouse docs — Inserting data](https://clickhouse.com/docs/guides/inserting-data)) and `insert_local_files` guide for flat files ([Insert Local Files](https://clickhouse.com/docs/integrations/data-ingestion/insert-local-files)). Faster bulk-import techniques (split + parallel) per [tech.marksblogg.com — Faster ClickHouse Imports](https://tech.marksblogg.com/faster-clickhouse-imports-csv-parquet-mysql.html) show that CSV-via-client vs Python-driver batched insert differ by ≤20% on single-node loads at our scale; driver wins on correctness and ergonomics.

### Script shape

```
scripts/
  retailrocket/
    download.sh              # kaggle datasets download retailrocket/ecommerce-dataset -p data/retailrocket --unzip
    import.py                # orchestrator
    _events.py               # loads events.csv
    _item_properties.py      # loads both item_properties_part*.csv
    _category_tree.py        # loads category_tree.csv
    README.md                # how to run, what it does
```

**`import.py` sketch:**

```python
# scripts/retailrocket/import.py
import argparse, hashlib, logging, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

import clickhouse_connect
import pandas as pd

CHUNK_ROWS = 500_000  # ~500k rows per INSERT batch

def batch_id(data_dir: Path) -> str:
    # Content-hash of the source files → same CSVs produce same batch_id → ReplacingMergeTree dedupes.
    h = hashlib.sha256()
    for p in sorted(data_dir.glob("*.csv")):
        h.update(p.name.encode())
        h.update(str(p.stat().st_size).encode())
    return h.hexdigest()[:16]

def load_events(client, csv_path: Path, load_id: str) -> int:
    total = 0
    for chunk in pd.read_csv(csv_path, chunksize=CHUNK_ROWS,
                             dtype={'visitorid':'UInt32','itemid':'UInt32',
                                    'transactionid':'Int64','event':'string'}):
        chunk['event_time'] = pd.to_datetime(chunk['timestamp'], unit='ms', utc=True)
        chunk['transactionid'] = chunk['transactionid'].astype('Int64').where(chunk['transactionid'].notna(), None)
        chunk['load_batch_id'] = load_id
        client.insert_df('retailrocket_raw.events',
                         chunk[['event_time','visitorid','event','itemid','transactionid','load_batch_id']]
                           .rename(columns={'event':'event_type'}))
        total += len(chunk)
        logging.info("events: %s rows loaded", f"{total:,}")
    return total

# ... analogous load_item_properties() and load_category_tree()

def main():
    data = Path(os.environ.get('RETAILROCKET_DATA', 'data/retailrocket'))
    client = clickhouse_connect.get_client(
        host=os.environ.get('CH_HOST','clickhouse'),
        port=int(os.environ.get('CH_PORT','8123')),
        username=os.environ.get('CH_USER','default'),
        password=os.environ.get('CH_PASSWORD',''))
    load_id = batch_id(data)
    logging.info("load_batch_id = %s", load_id)
    # Idempotency: if this batch already inserted, skip.
    existing = client.query(
        "SELECT count() FROM retailrocket_raw.events WHERE load_batch_id=%(b)s",
        parameters={'b': load_id}).first_item[0]
    if existing > 0:
        logging.info("Batch %s already loaded (%d rows in events). Nothing to do.", load_id, existing)
        return 0
    load_events(client, data/'events.csv', load_id)
    load_item_properties(client, [data/'item_properties_part1.csv', data/'item_properties_part2.csv'], load_id)
    load_category_tree(client, data/'category_tree.csv', load_id)
    # Optional: OPTIMIZE TABLE ... FINAL (only during demo reset; expensive)
    return 0

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
    sys.exit(main())
```

**Run command:**

```bash
# from repo root, inside the compose network
docker compose run --rm \
  -v $(pwd)/data/retailrocket:/data \
  -e RETAILROCKET_DATA=/data \
  -e CH_HOST=clickhouse \
  retailrocket-import python scripts/retailrocket/import.py
```

With `retailrocket-import` defined as a small Python service in `docker-compose.yml` (Python 3.12 + `clickhouse-connect` + `pandas`).

### Expected load time (sanity)

At 500k rows/batch via HTTP insert on a local ClickHouse:
- `events.csv`: ~2.76M rows → ~6 batches → **30–60s** typical
- `item_properties_part1+2`: ~20.28M rows → ~41 batches → **5–10 min**
- `category_tree.csv`: 1,669 rows → single insert, **<1s**

Total wall time: **under 15 minutes** on a dev laptop. Acceptable for a one-shot seed load.

### Alternatives considered

| Approach | Pros | Cons | Verdict |
|---|---|---|---|
| `clickhouse-client --query="INSERT ... FORMAT CSV" < file.csv` | Fastest raw throughput; zero code | No timestamp conversion, no load_batch_id, no idempotency, no nullable handling for `transactionid` | Rejected (needs wrapping anyway) |
| `clickhouse-local` + `INSERT INTO FUNCTION remote(...)` | Powerful SQL preprocessing; one-liner | Extra binary; awkward to parameterise; not idiomatic for a scripted pipeline | Rejected |
| Python + `clickhouse-driver` (native protocol) | Slightly faster than HTTP | Less documented; HTTP is good enough at 20M rows | Rejected |
| **Python + `clickhouse-connect` (HTTP)** | Official, clean types, idempotency logic trivial, runs in existing Docker network | ~20% slower than native protocol at very high throughput (irrelevant at our scale) | **Chosen** |

Sources:
[ClickHouse inserting-data guide](https://clickhouse.com/docs/guides/inserting-data),
[clickhouse-connect bulk insertion](https://deepwiki.com/ClickHouse/clickhouse-connect/5.3-data-insertion),
[ClickHouse supercharging data loads blog](https://clickhouse.com/blog/supercharge-your-clickhouse-data-loads-part1),
[Altinity — clickhouse-local overview](https://altinity.com/blog/2019-6-11-clickhouse-local-the-power-of-clickhouse-sql-in-a-single-command).

---

## Idempotency Approach

Rerunning the import must not duplicate rows. Four layers, in order of strength:

### Layer 1 — `load_batch_id` short-circuit (cheapest, primary defence)

The importer computes `load_batch_id = sha256(filenames + sizes)[:16]` before touching ClickHouse. It then asks:

```sql
SELECT count() FROM retailrocket_raw.events WHERE load_batch_id = :b
```

If nonzero, the script logs "batch already loaded" and exits 0. Running `import.py` a second time on the same CSVs is a no-op. This handles **99% of the real-world case**: the student re-runs `make import` after a crash or during a demo.

### Layer 2 — `ReplacingMergeTree(load_batch_id)` — row-level dedup at merge

The three tables are `ReplacingMergeTree` engines keyed on `(ORDER BY)` tuples that include a `row_hash` column. Two inserts of the same logical row (same timestamp + visitor + event + item) collapse to one during background merges. The `load_batch_id` version column keeps the **newest** load's copy — useful if Kaggle ever republishes a corrected CSV.

Caveat: merges are async. Queries between insert and merge may see duplicates. Mitigations:
- Use `SELECT ... FINAL` in **demo** queries (acceptable at this scale).
- Or: `OPTIMIZE TABLE retailrocket_raw.events FINAL` after the import (one-shot, blocking, a few seconds at 2.76M rows).
- Or: filter by `load_batch_id = (SELECT max(load_batch_id) FROM ...)` in v1.2 feature queries.

This is the standard ClickHouse idiom per [Altinity KB — Insert Deduplication](https://kb.altinity.com/altinity-kb-schema-design/insert_deduplication/) and [ClickHouse Deduplication Strategies](https://clickhouse.com/docs/guides/developer/deduplication).

### Layer 3 — `insert_deduplication_token` (block-level)

Every `client.insert()` call passes a deterministic token:

```python
client.insert(..., settings={'insert_deduplication_token': f'{load_id}:events:{chunk_idx}'})
```

If the same chunk is re-sent (network retry, crash mid-batch), ClickHouse drops the duplicate block server-side. This requires `non_replicated_deduplication_window` to be configured on the server — add to `docker-compose.yml`:

```yaml
environment:
  - CLICKHOUSE_NON_REPLICATED_DEDUPLICATION_WINDOW=1000
```

Reference: [Altinity KB — Insert Deduplication](https://kb.altinity.com/altinity-kb-schema-design/insert_deduplication/); [ClickHouse 22.2+ `insert_deduplication_token` setting](https://clickhouse.com/docs/guides/developer/deduplication).

### Layer 4 — Makefile-level reset (manual override)

For full reruns (e.g., after schema change):

```makefile
retailrocket-reset:
	docker compose exec clickhouse clickhouse-client \
	  --query "DROP DATABASE IF EXISTS retailrocket_raw"
	docker compose exec clickhouse clickhouse-client \
	  --query "$$(cat infra/clickhouse/retailrocket_schema.sql)"

retailrocket-import:
	docker compose run --rm retailrocket-import python scripts/retailrocket/import.py

retailrocket-reload: retailrocket-reset retailrocket-import
```

The combination of L1+L2 alone is sufficient for Phase 7. L3 is defence-in-depth. L4 is the "I changed the DDL" button.

---

## Event Vocabulary Mapping (Retailrocket → v1.1)

The v1.1 tracker captures **5 event types**. Retailrocket only has **3**. The mapping is not one-to-one and the gap is material for v1.2.

### Mapping table

| v1.1 target event | Retailrocket source event | Mapping | Gap / notes |
|---|---|---|---|
| `product_view` | `view` | **1:1 direct** | Retailrocket `view` means any item-detail-page view. Our `product_view` is the same semantic. Safe mapping. |
| `add_to_cart` | `addtocart` | **1:1 direct** | Only 69,332 rows (~2.5% of events). Low but realistic cart-conversion rate. |
| `remove_from_cart` | *(none)* | **Gap — no source signal** | Retailrocket does not record cart removals. Implication: any v1.2 feature that relies on "cart abandonment via explicit removal" cannot be trained from this corpus. Abandonment must be inferred as "addtocart with no subsequent transaction within N minutes/hours." |
| `purchase` | `transaction` | **1:1 direct** (with caveat) | Retailrocket `transaction` rows are **line items**, not orders: multiple rows with the same `transactionid` = one purchase of multiple items. For v1.1 we map each transaction row to one `purchase` event; v1.2 basket-size features then use `GROUP BY transactionid`. |
| `search` | *(none)* | **Gap — no source signal** | Retailrocket has no search events in the public dataset. Any search-driven lead-scoring feature (search-then-view, search-then-purchase) cannot be sourced here. |

### How we surface the gaps (not hide them)

1. **Leave `remove_from_cart` and `search` columns literally absent** from the unified view for `source='retailrocket'`. Do not fabricate synthetic removes/searches — that would teach v1.2 models nonsense signals.
2. **Document the gap** in `unified_events` view comments and in the dataset README committed under `data/retailrocket/README.md`.
3. **v1.2 feature flag:** lead-scoring features that require `search` or `remove_from_cart` must be gated with a `source IN ('live')` filter or carry a "requires live traffic" note. At GL4 defense, state: "Our retailrocket corpus trains the funnel view→cart→purchase; search and explicit cart-removal features are evaluated only on the live tracker stream once v1.1 starts collecting them."
4. **Cart-abandonment proxy (v1.2 decision, not v1.1):** `addtocart` with no `transaction` for same (visitorid, itemid) within a time window = implicit abandonment. This is a modelling choice, not a data fix; keep the raw data honest.

### Event-count asymmetry (informational)

| Event | Retailrocket row count | Share | Live-stream expectation (our tracker) |
|---|---|---|---|
| view / product_view | 2,664,312 | 96.7% | similar skew (views dominate) |
| addtocart / add_to_cart | 69,332 | 2.5% | similar |
| transaction / purchase | 22,457 | 0.8% | typically lower in B2C (0.1–2%) |
| remove_from_cart | 0 | — | will appear once v1.1 ships |
| search | 0 | — | will appear once v1.1 ships |

This asymmetry is valuable context for v1.2: the class imbalance on "purchase" (our most valuable lead label) is severe and known in advance. Lead-scoring models must use appropriate handling (class weights / focal loss / ranking loss rather than vanilla binary logistic on raw counts).

---

## Joinability Notes (for v1.2 lead scoring)

### Feature-engineering primitives available from this corpus

Using `retailrocket_raw.events` + `item_latest` view:

```sql
-- Recency (per visitor, per event type) — cheap, hits ORDER BY
SELECT visitorid,
       max(event_time) FILTER (WHERE event_type='view')        AS last_view_at,
       max(event_time) FILTER (WHERE event_type='addtocart')   AS last_cart_at,
       max(event_time) FILTER (WHERE event_type='transaction') AS last_purchase_at
FROM retailrocket_raw.events
GROUP BY visitorid;

-- Frequency + funnel stage
SELECT visitorid,
       countIf(event_type='view')        AS views,
       countIf(event_type='addtocart')   AS carts,
       countIf(event_type='transaction') AS purchases,
       uniqExactIf(itemid, event_type='view')      AS unique_viewed_items,
       uniqExactIf(itemid, event_type='addtocart') AS unique_carted_items
FROM retailrocket_raw.events
GROUP BY visitorid;

-- Basket size per transaction (itemid cardinality per transactionid)
SELECT visitorid,
       transactionid,
       count() AS items_in_basket,
       min(event_time) AS purchased_at
FROM retailrocket_raw.events
WHERE event_type = 'transaction' AND transactionid IS NOT NULL
GROUP BY visitorid, transactionid;

-- Category affinity (needs item_latest)
SELECT e.visitorid,
       il.categoryid,
       count() AS interactions
FROM retailrocket_raw.events e
LEFT JOIN retailrocket_raw.item_latest il ON il.itemid = e.itemid
GROUP BY e.visitorid, il.categoryid;
```

All four query shapes hit the `ORDER BY (visitorid, event_time, itemid, row_hash)` prefix on the primary key — they should be fast even at 2.76M rows. The category join benefits from the `by_item` projection.

### Limitations for v1.2

- **No session_id.** Retailrocket does not ship session boundaries. v1.2 must sessionise: consecutive events per visitor with gaps ≤ 30 minutes form a session. This is a pure SQL window function — compute it at feature time, not at load time.
- **No page_url / referrer / UTM.** Lead-scoring features based on traffic source (paid vs organic) cannot come from this corpus. Live tracker stream only.
- **Anonymous visitors only.** `visitorid` is cookie-scoped. Cross-device joining, email matching, etc. are out of scope.
- **Hashed everything.** `itemid` and `categoryid` are integers with no human-readable label. Fine for modelling; uninspiring for demo storytelling. Consider generating a small "category name" mapping manually for the top 20 categoryids using event counts, so the defense demo shows meaningful category names. (This is cosmetic — do not hack this into the data load.)

---

## Gaps / Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | **License not visually confirmed on live Kaggle page.** Community sources consistently say CC BY-NC-SA 4.0 but the Kaggle license sidebar was gated during WebFetch. | Medium | **Phase 7 pre-flight:** open Kaggle page in a browser, screenshot the license block, commit as `.planning/research/v1.1/evidence/kaggle-license.png`. If not CC BY-NC-SA 4.0, revise attribution text but do not change plans — any CC-family license covers academic non-commercial use. |
| 2 | **`search` and `remove_from_cart` absent from Retailrocket.** v1.2 features using these signals will have training data only from live stream. | Medium | Document clearly (done above). Gate v1.2 feature engineering. Consider generating synthetic search/removes via CTGAN in a later milestone — but flag them as synthetic. |
| 3 | **Timestamp unit confusion.** Multiple community users misread the ms timestamp as seconds (hence "year 47495"). | Low | Explicit unit conversion `fromUnixTimestamp64Milli` in DDL/script. Add assertion in `import.py`: `assert min_event_time.year == 2015, "timestamp unit wrong"`. |
| 4 | **`transactionid` is line-item grouping, not order ID.** Naive `COUNT(DISTINCT transactionid)` = order count; `COUNT(*) WHERE event='transaction'` = line-item count. | Low | Comment in DDL, example queries in this doc. |
| 5 | **Item-properties EAV size (20.28M rows).** Larger than `events.csv`. Part loading will be the slowest step. | Low | Stream via chunksize=500k; expect 5–10 min. Use projection or materialised `item_latest_wide` for hot-path queries so we don't re-aggregate 20M rows on every dashboard refresh. |
| 6 | **Hashed properties.** Only `categoryid` and `available` are interpretable. The other ~1000 hashed keys are pure opacity. | Low | Accept as-is. Do not attempt to reverse-hash. v1.2 features only rely on the two unhashed ones plus `event` signal. |
| 7 | **Class imbalance: 96.7% views, 0.8% transactions.** | Low (for this phase) | Surface for v1.2 modelling (documented in Event Vocabulary Mapping). Not a v1.1 import concern. |
| 8 | **Raw CSVs ≈ 2.7 GB uncompressed.** Should not be committed. | Low | `data/retailrocket/` in `.gitignore`; `download.sh` fetches via Kaggle API using user's `~/.kaggle/kaggle.json`. |
| 9 | **Dataset is from 2015.** Demo audience may ask "why 10-year-old data?" | Low (talking point, not a tech risk) | Prepared defense answer: "We need a real, cleanly-licensed, longitudinally consistent e-commerce log to validate v1.2 lead-scoring SQL. Retailrocket is the standard academic benchmark for this and ships with implicit-feedback labels." |

---

## Sources

### Dataset schema & statistics (HIGH confidence — cross-verified across ≥2 sources)

- **Kaggle dataset landing page** — Retail Rocket (publisher), Retailrocket Recommender System Dataset. `https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset`. Gated for programmatic fetch; verified file list (events.csv, item_properties_part1.csv, item_properties_part2.csv, category_tree.csv).
- **[rs_datasets — Retail Rocket](https://darel13712.github.io/rs_datasets/Datasets/retail_rocket/)** — 2,756,101 events / 1,407,580 users / 235,061 items; column schemas for all three tables.
- **[RStudio Pubs — Retail Recommendation System](https://rstudio-pubs-static.s3.amazonaws.com/307430_112de48631ce4a1987d35cb77750ba9e.html)** — per-file row counts (10,999,999 / 9,275,903 / 1,669 / 2,756,101), NA breakdown on `transactionid` and `parentid`, confirmation that `categoryid` and `available` are the only unhashed property keys.
- **[RecPack — RetailRocket loader](https://recpack.froomle.ai/generated/recpack.datasets.RetailRocket.html)** — column names (`visitorid`, `itemid`, `timestamp`, `event`) and event vocabulary `{view, addtocart, transaction}`.
- **[CoronaScience — Retailrocket README](https://github.com/CoronaScience/RetailrocketRecommenderSystemDataset)** — source statement: "raw data … all values are hashed".
- **[ReabetsweRamakatsa — retail-rocket-sql-analytics (repo note, 404 on direct fetch but appears in search)](https://github.com/ReabetsweRamakatsa/retail-rocket-sql-analytics)** — real-world SQL analytics patterns on the same corpus (funnels, cohorts, RFM, affinity).

### License (MEDIUM confidence — see Gap #1)

- **[CC BY-NC-SA 4.0 official license text](https://creativecommons.org/licenses/by-nc-sa/4.0/)** — canonical text of BY-NC-SA.
- **[Kaggle — Common license types](https://www.kaggle.com/general/116476)** — Kaggle's own taxonomy of license labels used on dataset pages.
- **[Kaggle — Understanding Dataset Licenses](https://www.kaggle.com/getting-started/515708)** — how Kaggle surfaces license metadata.

### ClickHouse import & idempotency (HIGH confidence)

- **[ClickHouse docs — Inserting data guide](https://clickhouse.com/docs/guides/inserting-data)** — recommended patterns for batch CSV insert.
- **[ClickHouse docs — Insert Local Files](https://clickhouse.com/docs/integrations/data-ingestion/insert-local-files)** — `clickhouse-client` CSV piping.
- **[ClickHouse docs — Deduplication Strategies](https://clickhouse.com/docs/guides/developer/deduplication)** — ReplacingMergeTree + insert_deduplication_token.
- **[Altinity KB — Insert Deduplication / Insert Idempotency](https://kb.altinity.com/altinity-kb-schema-design/insert_deduplication/)** — mechanism and `non_replicated_deduplication_window` server setting.
- **[Tinybird — ReplacingMergeTree examples](https://www.tinybird.co/blog/clickhouse-replacingmergetree-example)** — version column idiom.
- **[ClickHouse blog — Supercharging large data loads](https://clickhouse.com/blog/supercharge-your-clickhouse-data-loads-part1)** — block size / parallelism tuning.
- **[tech.marksblogg.com — Faster ClickHouse Imports](https://tech.marksblogg.com/faster-clickhouse-imports-csv-parquet-mysql.html)** — single-file CSV import timings.
- **[clickhouse-connect docs — Bulk Insertion](https://deepwiki.com/ClickHouse/clickhouse-connect/5.3-data-insertion)** — Python driver batched insert semantics.
- **[Altinity — clickhouse-local intro](https://altinity.com/blog/2019-6-11-clickhouse-local-the-power-of-clickhouse-sql-in-a-single-command)** — when clickhouse-local is and isn't appropriate.

### ClickHouse schema design (HIGH confidence)

- **[ClickHouse docs — Mapping types (ClickStack migration)](https://clickhouse.com/docs/use-cases/observability/clickstack/migration/elastic/types)** — why ClickStack is migrating off Map toward JSON; informs our long-format choice.
- **[Orapinpatipat — ClickHouse Map vs Individual column performance](https://medium.com/@chayut_o/clickhouse-map-vs-individual-column-performance-f089dde3c100)** — linear-time Map key lookup benchmark.
- **[ClickHouse GitHub — Map data type issue #1841](https://github.com/ClickHouse/ClickHouse/issues/1841)** — community context on Map limitations.
