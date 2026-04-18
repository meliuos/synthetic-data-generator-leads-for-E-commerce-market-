# Roadmap: Lead Intelligence Platform — Event Tracking & Heatmap

## Overview

v1.0 shipped the heatmap core in five phases (Phase 5 dropped at pivot): Redpanda + ClickHouse backbone, vanilla-JS tracker with consent gate, Playwright screenshot service, and a Streamlit heatmap dashboard. v1.1 extends the platform toward lead generation by (a) adding typed e-commerce columns to ClickHouse without rebuilding the table, (b) exposing 5 new tracker methods for `product_view` / `add_to_cart` / `remove_from_cart` / `purchase` / `search` gated by the existing consent banner, (c) importing the Retailrocket open-source dataset into parallel ClickHouse tables so downstream lead-scoring work has a real corpus, and (d) landing the two still-useful dashboard panels rolled over from dropped Phase 5 (session stats + click ranking). Each phase remains independently verifiable and the new scope is additive to v1.0 — nothing that shipped gets rewritten.

## Milestones

- Shipped **v1.0 Heatmap Core** — Phases 1–4 (shipped 2026-04-16; Phase 5 dropped)
- Active **v1.1 E-commerce Events & Lead Dataset** — Phases 5–8 (in progress)

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

### v1.0 (shipped)

- [x] **Phase 1: Streaming and Storage Backbone** - Redpanda + ClickHouse running locally, 3-table schema locked, ORDER BY finalized
- [x] **Phase 2: JS Tracker and Event Ingestion Pipeline** - Browser snippet captures events, RudderStack routes them, rows appear in ClickHouse within seconds
- [x] **Phase 3: Screenshot Capture Service** - Playwright service captures full-page screenshots at desktop and mobile viewports, stored on disk
- [x] **Phase 4: Heatmap Computation and Core Dashboard** - Streamlit dashboard renders click/scroll/hover heatmaps as Plotly overlays on screenshots with URL filter and type switcher
- [~] **Phase 5: Analytics Features** - Dropped — rolled into v1.1 (see MILESTONES.md)

### v1.1 (active)

- [x] **Phase 5: E-commerce Event Schema** - Additive ClickHouse schema extension with typed e-commerce columns, updated materialized view, `products[]` ARRAY JOIN projection, and `ReplacingMergeTree` orders dedup projection
- [ ] **Phase 6: E-commerce Tracker API** - 5 new tracker methods (`productView`, `addToCart`, `removeFromCart`, `purchase`, `search`) inheriting consent gate, plus a demo-shop test SPA that exercises every method
- [ ] **Phase 7: Retailrocket Import** - Download + import scripts that idempotently load events, item_properties (long EAV), and category_tree into parallel `retailrocket_raw.*` tables, verified by a smoke query
- [ ] **Phase 8: Rolled-over Dashboard Panels** - Session stats panel and click ranking panel added to the existing Streamlit dashboard using the v1.0 `heatmap_queries.py` aggregation pattern

## Phase Details

### Phase 1: Streaming and Storage Backbone
**Goal**: The full storage infrastructure is running locally and can accept events — pipeline decisions that cannot be changed after data flows are locked permanently.
**Depends on**: Nothing (first phase)
**Requirements**: PIPE-01, PIPE-02, PIPE-03, PIPE-04, PIPE-05
**Success Criteria** (what must be TRUE):
  1. `docker compose up` starts Redpanda, ClickHouse, RudderStack data plane, and Streamlit with no errors
  2. A JSON message manually produced to the Redpanda topic appears as a row in the `click_events` MergeTree table within 5 seconds
  3. The MergeTree ORDER BY is `(page_url, event_type, toDate(event_time))` and the schema stores `x_pct`, `y_pct`, `element_selector`, `device_type`, `session_id`, `anonymous_user_id` (hashed) — no raw PII columns exist
  4. ClickHouse async_insert is configured so the Kafka engine does not hammer with per-row inserts
**Plans**: 3 plans

Plans:
- [x] 01-01: Docker Compose stack (Redpanda + ClickHouse + RudderStack data plane)
- [x] 01-02: ClickHouse 3-table schema (Kafka queue + Materialized View + MergeTree target)
- [x] 01-03: End-to-end smoke test (manual produce → row in MergeTree)

### Phase 2: JS Tracker and Event Ingestion Pipeline
**Goal**: A JavaScript snippet embedded in any page captures all required event types with correct document-relative coordinates and GDPR consent gating, and delivers them into ClickHouse through RudderStack and Redpanda.
**Depends on**: Phase 1
**Requirements**: TRACK-01, TRACK-02, TRACK-03, TRACK-04, TRACK-05, TRACK-06, TRACK-07
**Success Criteria** (what must be TRUE):
  1. Clicking anywhere on a test page after scrolling 500 px stores a row with `x_pct`/`y_pct` values that match the document-relative position (not viewport-relative), visible in ClickHouse within 5 seconds
  2. Scrolling to 75% of a test page stores a scroll_depth event with `scroll_pct = 75` for that session and URL
  3. Mouse movement events arrive throttled — no more than 10 events per second per session appear in ClickHouse
  4. Navigating between SPA routes triggers a new page_view event for each route change without a full page reload
  5. No events appear in ClickHouse until the cookie consent banner has been accepted by the user
**Plans**: 4 plans

Plans:
- [x] 02-01: JS tracker with click, scroll, mousemove, page_view capture and document-relative coordinate normalization
- [x] 02-02: RudderStack SDK integration and Kafka destination verification against Redpanda
- [x] 02-03: Cookie consent gate with vanilla-cookieconsent v3.1.0 (GDPR compliance)
- [x] 02-04: End-to-end browser validation (click/scroll/navigate → ClickHouse row verification)

### Phase 3: Screenshot Capture Service
**Goal**: A standalone Playwright service captures full-page screenshots at desktop and mobile viewports for any registered URL, stores them on disk, and makes them refreshable from the dashboard.
**Depends on**: Phase 1 (shared Docker volume and Compose stack)
**Requirements**: SHOT-01, SHOT-02
**Success Criteria** (what must be TRUE):
  1. Calling the screenshot service for a given URL produces two PNG files — one at 1440px viewport width and one at 390px — stored at a predictable path derived from the URL and viewport
  2. The captured screenshot's full document height matches `document.body.scrollHeight` reported by the JS snippet for the same page (within 5%)
  3. Screenshots can be refreshed on demand from the dashboard without restarting the service
**Plans**: 2 plans

Plans:
- [x] 03-01: Playwright async screenshot service (1440px + 390px, URL+viewport hash caching, Docker container)
- [x] 03-02: Dashboard refresh trigger and shared volume wiring

### Phase 4: Heatmap Computation and Core Dashboard
**Goal**: A Streamlit dashboard loads a page screenshot and overlays a Plotly heatmap computed entirely in ClickHouse, with controls to switch heatmap type and filter by URL.
**Depends on**: Phase 2 (events in ClickHouse), Phase 3 (screenshots on disk)
**Requirements**: HEAT-01, HEAT-02, HEAT-03, DASH-01, DASH-02
**Success Criteria** (what must be TRUE):
  1. Selecting a page URL in the dashboard renders a click heatmap as a Plotly color intensity overlay on the correct page screenshot, with brighter regions where more clicks occurred
  2. Switching to scroll depth view renders horizontal gradient bands on the same screenshot reflecting the distribution of max scroll depth across sessions
  3. Switching to hover/movement view renders a heatmap from throttled mousemove events on the same screenshot
  4. Entering a URL pattern with a wildcard (e.g. `/product/*`) aggregates events from all matching pages into a single heatmap
  5. All heatmap data is aggregated in ClickHouse using 5% grid binning before reaching Python — no raw event rows are fetched to the dashboard process
**Plans**: 4 plans

Plans:
- [x] 04-01: ClickHouse binning queries (5% buckets, 20x20 grid, parameterized by URL, event type, viewport)
- [x] 04-02: Streamlit app scaffold + screenshot loader + Plotly heatmap overlay
- [x] 04-03: URL filter with wildcard support + heatmap type switcher
- [x] 04-04: Scroll depth heatmap and hover heatmap views

### Phase 5 (v1.0): Analytics Features — DROPPED
**Status**: Dropped — rolled into v1.1 (see MILESTONES.md)
**Reason**: Live feed and page-flow Sankey don't serve lead intelligence; session stats and click ranking are preserved and re-scheduled as v1.1 Phase 8.
**Original requirements** (now deprecated or rolled over):
  - ~~DASH-03 Live event feed~~ — dropped
  - ~~DASH-04 Click ranking~~ → rolled over as **STATS-02** in v1.1 Phase 8
  - ~~DASH-05 Page flow Sankey~~ — dropped
  - ~~DASH-06 Session stats~~ → rolled over as **STATS-01** in v1.1 Phase 8

## v1.1 Phases

The v1.1 milestone reuses integer phase numbering 5-8 (continuing from the dropped v1.0 Phase 5). The 18 v1.1 requirements map as follows: Phase 5 → SCHEMA-01..03; Phase 6 → ECOM-01..07; Phase 7 → DATA-01..06; Phase 8 → STATS-01..02. All phases follow the same ROADMAP format used in v1.0 (Goal / Depends on / Requirements / Success Criteria / Plans).

**Parallelism:** Phases 6 and 7 can run in parallel once Phase 5 ships (tracker work and dataset import touch disjoint code paths; both consume the Phase 5 schema/column vocabulary). Phase 8 depends only on Phase 5 and can run in parallel with 6 and 7 as well.

### Phase 5: E-commerce Event Schema
**Goal**: The `analytics.click_events` table can accept e-commerce events additively — new typed `Nullable` columns for `product_id`, `category`, `price`, `quantity`, `order_id`, `cart_value`, `search_query`, `results_count`, a materialized-view update that extracts them from both flat and nested `properties` JSON shapes, a `products[]` ARRAY JOIN projection for per-line-item queries, and a `ReplacingMergeTree(event_time)` projection keyed on `order_id` for server-side purchase dedup — all without touching or rewriting existing v1.0 events.
**Depends on**: Phase 1 (v1.0 schema must exist to extend it)
**Requirements**: SCHEMA-01, SCHEMA-02, SCHEMA-03
**Notes for implementers**:
  - Event vocabulary is fixed upstream (see `.planning/research/v1.1/EVENTS.md`): tracker emits RudderStack/Segment V2 shape (`product_id`, `products[]`, `order_id`, `query`); the materialized view exposes GA4 aliases (`item_id`, `items[]`, `transaction_id`, `search_term`) as computed columns or a companion view so downstream GA4-shaped consumers can still query.
  - Purchase dedup is defence-in-depth: tracker uses `localStorage` seen-set (Phase 6), the `ReplacingMergeTree(event_time)` projection on `order_id` is this phase's server-side layer. Both must exist; neither replaces the other.
  - Retailrocket rows do **not** land in `click_events`. The vocabulary here nevertheless matches Retailrocket's columns (so Phase 7's parallel tables use compatible types), see DATASET.md.
  - `cart_id` open question: resolved — **tracker-maintained** (localStorage per session), per EVENTS.md recommendation. The schema stores `cart_value` as the running aggregate; `cart_id` itself lives in `event_payload` JSON (no need for a dedicated column at v1.1 scale).
**Success Criteria** (what must be TRUE):
  1. Running `make schema` on a database that already has v1.0 data completes without error and without rebuilding `click_events`; a row count query before and after returns the same number
  2. Running `make schema` a second time back-to-back is idempotent — no `ADD COLUMN` failures, no materialized view drops, exit 0 both times
  3. After the schema update, `INSERT`ing a v1.0-shape event (no e-commerce fields) still succeeds and all new columns read back `NULL`
  4. `DESCRIBE analytics.click_events` lists the 8 new columns, all `Nullable`, in addition to every v1.0 column (no v1.0 columns removed or retyped)
  5. A projection on the table (inspected via `SELECT * FROM system.projections WHERE table = 'click_events'`) exists for `order_id`-keyed `ReplacingMergeTree(event_time)` dedup
**Plans**: 3 plans

Plans:
- [x] 05-01: v1.1 additive schema migration (002_ecommerce_schema.sql + make schema-v11)
- [x] 05-02: End-to-end smoke test (scripts/smoke-test-v11.sh + make smoke-test-v11)
- [x] 05-03: Developer-facing schema documentation (docs/schema-v1.1.md + README pointer)

### Phase 6: E-commerce Tracker API
**Goal**: The JS tracker exposes 5 new public methods — `productView`, `addToCart`, `removeFromCart`, `purchase`, `search` — that normalize inputs into RudderStack/Segment V2 property shape, inherit the v1.0 consent gate (no emission before opt-in), dedup `purchase` via `localStorage` seen-set on `order_id`, and are exercised end-to-end by an upgraded demo-shop SPA that replaces the existing `src/test-spa-page.html` with product cards, cart controls, a checkout button, and a search bar.
**Depends on**: Phase 5 (schema must exist before the tracker writes e-commerce columns)
**Requirements**: ECOM-01, ECOM-02, ECOM-03, ECOM-04, ECOM-05, ECOM-06, ECOM-07
**Notes for implementers**:
  - Extend `src/tracker/events.js`, `src/tracker/constants.js`, and `src/tracker/index.js` following the existing v1.0 queue-and-flush pattern; do not introduce a new delivery path or a second SDK.
  - Single `purchase` event per order with a `products[]` array (not one event per line item). Server-side expansion to per-line-item rows happens in Phase 5's ARRAY JOIN projection.
  - `cart_id` is tracker-maintained in `localStorage` per cart session and rotated after a successful `purchase` emit (open question resolved — tracker-side).
  - `search` fires on submit only (Enter / button click), never on `input` keystrokes. Document this in the tracker README.
  - Coerce `price` to Number, `quantity` to Integer at the tracker boundary; reject events that coerce to NaN with `console.warn`.
  - `currency` is required on all monetary events; `init()` accepts a `defaultCurrency` config so host sites set it once.
  - The demo shop must be static HTML+JS (no build step) so the existing `docker compose` serve-static pattern still works.
**Success Criteria** (what must be TRUE):
  1. Clicking "Add to Cart" on a product card in the demo SPA at `src/test-spa-page.html` produces an `add_to_cart` row in `analytics.click_events` with non-null `product_id`, `quantity`, and `price` within 5 seconds (with consent accepted)
  2. Clicking "Checkout" with 2 items in the cart produces exactly one `purchase` row with non-null `order_id`, `cart_value` set to the sum of line items, and `event_payload` containing a `products` array of length 2; refreshing the confirmation page a second time does NOT produce a second row (localStorage dedup)
  3. Submitting a query in the demo shop's search bar produces exactly one `search` row per submit with `search_query` and `results_count` populated; typing without submitting produces zero rows
  4. With the cookie consent banner rejected, clicking Add-to-Cart / Checkout / Search / visiting a product card produces zero rows in ClickHouse across all 5 e-commerce event types (consent gate inherited)
  5. The demo SPA contains at minimum 3 product cards, a visible cart with add/remove affordances, a search bar, and a checkout button — every one of the 5 tracker methods can be exercised without opening DevTools
**Plans**: TBD

Plans:
- [ ] 06-01: TBD (to be decomposed by `/gsd:plan-phase 6`)

### Phase 7: Retailrocket Import
**Goal**: The Retailrocket open-source dataset (events.csv + item_properties_part1.csv + item_properties_part2.csv + category_tree.csv) loads idempotently into a parallel `analytics.retailrocket_*` table set (separate from live `click_events`), via a committed download script (`scripts/download_retailrocket.sh` using the Kaggle API with user-local `~/.kaggle/kaggle.json`) and an import script that uses ClickHouse `insert_deduplication_token` keyed on per-file-chunk hashes for server-side idempotency — no raw CSVs committed to git, smoke query verifying row counts and event-type distribution matches the source.
**Depends on**: Phase 5 (column vocabulary alignment — Retailrocket tables are parallel but use compatible types for eventual unified-view queries in v1.2)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06
**Notes for implementers**:
  - **Phase 7 pre-flight (first task, before any code):** open the Kaggle dataset page in a browser, screenshot the License block, and commit under `.planning/research/v1.1/evidence/kaggle-license.png`. This is the one remaining unresolved research flag and must land before import runs.
  - Three parallel tables in a dedicated `retailrocket_raw` database: `events` (ReplacingMergeTree keyed by row_hash, partitioned by `toYYYYMM(event_time)`), `item_properties` (long EAV, 20.28M rows, ReplacingMergeTree), `category_tree` (1.6k rows, ReplacingMergeTree). See DATASET.md "Recommended ClickHouse Schema" for DDL.
  - Idempotency is **two-layered**: (1) `load_batch_id` short-circuit at the top of `import.py` (`sha256(filenames + sizes)[:16]` — if the batch already exists in `events`, exit 0); (2) ClickHouse `insert_deduplication_token` per chunk (setting `non_replicated_deduplication_window=1000` on the server). No Python-side row-level dedup.
  - Retailrocket CSVs are never committed to git. `data/retailrocket/` is in `.gitignore`; `download.sh` fetches via the Kaggle API with user-local `~/.kaggle/kaggle.json`. The README documents both the manual Kaggle auth step and the `make retailrocket-download` / `make retailrocket-import` / `make retailrocket-reload` targets.
  - Import uses Python + `clickhouse-connect` in 500k-row chunks (HTTP-based, inside the compose network). Expect <15 min wall time total.
  - Event vocabulary gaps (no `remove_from_cart`, no `search` in Retailrocket) are not fabricated — columns stay NULL. Documented in the `data/retailrocket/README.md` and in the import log.
**Success Criteria** (what must be TRUE):
  1. Running `bash scripts/download_retailrocket.sh` on a machine with `~/.kaggle/kaggle.json` configured places all 4 expected CSVs under `data/retailrocket/` with the expected filenames (events.csv, item_properties_part1.csv, item_properties_part2.csv, category_tree.csv) and no additional files
  2. Running `python scripts/retailrocket/import.py` on a fresh `retailrocket_raw` database loads exactly 2,756,101 events, 20,275,902 item_property observations (10,999,999 + 9,275,903), and 1,669 category rows (± 0) — verified by a committed smoke-query SQL file
  3. Running the same import a second time without modifying the CSVs exits 0 in under 5 seconds (the `load_batch_id` short-circuit kicks in — no duplicate rows produced)
  4. `SELECT event_type, count() FROM retailrocket_raw.events GROUP BY event_type` returns exactly `view: 2,664,312`, `addtocart: 69,332`, `transaction: 22,457` — the source distribution is preserved row-for-row
  5. Joining `retailrocket_raw.events` against the `item_latest` view (which reads from `item_properties`) on `itemid` returns a non-null `categoryid` for more than 90% of the event rows (spot check that the EAV load is joinable, not just counted)
  6. The raw CSVs are listed in `.gitignore` and `git status` after a fresh download shows them as ignored (no accidental commit of CC BY-NC-SA material)
**Plans**: TBD

Plans:
- [ ] 07-01: TBD (to be decomposed by `/gsd:plan-phase 7`)

### Phase 8: Rolled-over Dashboard Panels
**Goal**: The existing Streamlit dashboard at `dashboard/app.py` gains two new panels — a session stats panel (total sessions, avg scroll depth, bounce rate, total events for the selected URL scope) and a click ranking panel (top 10 CSS element selectors on the selected URL scope) — both aggregated in ClickHouse via the existing `dashboard/heatmap_queries.py` module pattern, never fetching raw rows into Python.
**Depends on**: Phase 5 (uses e-commerce columns? No — these panels work off v1.0 heatmap columns. Phase 5 is still a soft prerequisite because schema migration must not have broken the existing v1.0 columns the panels read, per Phase 5 success criterion 3/4.)
**Requirements**: STATS-01, STATS-02
**Notes for implementers**:
  - All SQL belongs in `dashboard/heatmap_queries.py` (or a sibling module following the same pattern). Reuse the v1.0 URL-scoping helper (exact match + wildcard `*` → LIKE) — do not re-implement.
  - Panels consume aggregated dataframes only (one row per metric, or a 10-row table for click ranking). Streamlit renders aggregates; never pulls raw event rows into the dashboard process (v1.0 rule, preserved).
  - Bounce rate definition: sessions with exactly one `page_view` event / total sessions, per selected URL scope. Surface the definition as a tooltip in the panel.
  - Session stats read `session_id` from the v1.0 schema; no e-commerce columns needed.
  - Click ranking reads `element_selector` from the v1.0 schema; event_type = 'click'.
**Success Criteria** (what must be TRUE):
  1. Opening the dashboard and selecting a URL scope with at least one session populates the session stats panel with four numeric metrics (total sessions, avg scroll depth as a percentage, bounce rate as a percentage, total events) in under 2 seconds
  2. Switching the URL scope (exact URL or wildcard pattern like `/product/*`) re-queries and updates both panels' values — same URL scoping semantics as the existing v1.0 heatmap
  3. The click ranking panel renders a table of up to 10 rows showing CSS element selector + click count, ordered by count descending, for the selected URL scope
  4. The aggregation for both panels happens in ClickHouse (verifiable by inspecting the query in `heatmap_queries.py` — `GROUP BY` / `count()` / `avg()` in the SQL) — no raw rows fetched to Python
  5. Both panels render a graceful empty state ("No sessions yet" / "No clicks yet") when the selected URL scope has zero matching rows, instead of erroring
**Plans**: TBD

Plans:
- [ ] 08-01: TBD (to be decomposed by `/gsd:plan-phase 8`)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → (v1.0 Phase 5 dropped) → 5 → {6, 7, 8 in parallel}

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Streaming and Storage Backbone | v1.0 | 3/3 | Complete | 2026-04-16 |
| 2. JS Tracker and Event Ingestion Pipeline | v1.0 | 4/4 | Complete | 2026-04-16 |
| 3. Screenshot Capture Service | v1.0 | 2/2 | Complete | 2026-04-16 |
| 4. Heatmap Computation and Core Dashboard | v1.0 | 4/4 | Complete | 2026-04-16 |
| 5 (v1.0). Analytics Features | v1.0 | 0/0 | Dropped — rolled into v1.1 | 2026-04-18 |
| 5. E-commerce Event Schema | v1.1 | 3/3 | Complete | 2026-04-19 |
| 6. E-commerce Tracker API | v1.1 | 0/TBD | Not started | - |
| 7. Retailrocket Import | v1.1 | 0/TBD | Not started | - |
| 8. Rolled-over Dashboard Panels | v1.1 | 0/TBD | Not started | - |
