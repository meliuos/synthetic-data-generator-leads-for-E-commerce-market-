# Roadmap: Lead Intelligence Platform — Event Tracking & Heatmap

## Overview

v1.0 shipped the heatmap core in five phases (Phase 5 dropped at pivot): Redpanda + ClickHouse backbone, vanilla-JS tracker with consent gate, Playwright screenshot service, and a Streamlit heatmap dashboard. v1.1 extends the platform toward lead generation by (a) adding typed e-commerce columns to ClickHouse without rebuilding the table, (b) exposing 5 new tracker methods for `product_view` / `add_to_cart` / `remove_from_cart` / `purchase` / `search` gated by the existing consent banner, (c) importing the Retailrocket open-source dataset into parallel ClickHouse tables so downstream lead-scoring work has a real corpus, and (d) landing the two still-useful dashboard panels rolled over from dropped Phase 5 (session stats + click ranking). Each phase remains independently verifiable and the new scope is additive to v1.0 — nothing that shipped gets rewritten.

## Milestones

- Shipped **v1.0 Heatmap Core** — Phases 1–4 (shipped 2026-04-16; Phase 5 dropped)
- Shipped **v1.1 E-commerce Events & Lead Dataset** — Phases 5–8 (shipped 2026-04-29)
- Shipped **v1.2 Lead Scoring & Identification** — Phases 9–12 (shipped 2026-04-29)
- Shipped **v2.0 Synthetic Data Generation** — Phases 13–14 (shipped 2026-05-10)
- Shipped **v2.1 AI Commercial Assistant** — Phases 15–16 (shipped 2026-05-10)
- Shipped **v2.2 Product Intelligence Interface** — Phase 17 (shipped 2026-05-10)
- Shipped **v2.3 ML Pipeline Hardening** — Phases 18–19 (shipped 2026-05-10)
- Shipped **v2.4 Production Monitoring & CI** — Phase 20 (shipped 2026-05-10)

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

### v1.1 (shipped)

- [x] **Phase 5: E-commerce Event Schema** - Additive ClickHouse schema extension with typed e-commerce columns, updated materialized view, `products[]` ARRAY JOIN projection, and `ReplacingMergeTree` orders dedup projection
- [x] **Phase 6: E-commerce Tracker API** - 5 new tracker methods (`productView`, `addToCart`, `removeFromCart`, `purchase`, `search`) inheriting consent gate, plus a demo-shop test SPA that exercises every method
- [x] **Phase 7: Retailrocket Import** - Download + import scripts that idempotently load events, item_properties (long EAV), and category_tree into parallel `retailrocket_raw.*` tables, verified by a smoke query
- [x] **Phase 8: Rolled-over Dashboard Panels** - Session stats panel and click ranking panel added to the existing Streamlit dashboard using the v1.0 `heatmap_queries.py` aggregation pattern

### v1.2 (active)

- [x] **Phase 9: Lead Scoring Data Foundation** - Four read-time ClickHouse views: `analytics.unified_events`, `analytics.live_session_features`, `analytics.retailrocket_session_features`, `analytics.session_features`; both sources queryable
- [x] **Phase 10: Rule-Based Lead Scoring Engine** - Table-driven Python scoring module (`src/scoring/rules.py`), `analytics.lead_scores_rule_based` view, 40+ unit tests; `SELECT anonymous_user_id, lead_score, score_tier FROM analytics.lead_scores_rule_based ORDER BY lead_score DESC` returns a ranked candidate list
- [x] **Phase 11: ML Lead Scoring Model** - LightGBM binary classifier trained on Retailrocket session_features (5-fold CV, scale_pos_weight for 0.82% imbalance); `MLScorer` wrapper, `score_sessions.py` batch CLI, `analytics.lead_scores_ml` ReplacingMergeTree table; ML scores joinable with rule-based scores
- [x] **Phase 12: Lead Identification Dashboard** - Streamlit multi-page "Leads" page with ranked table (rule + ML score), sidebar tier/source filters, rules_fired breakdown column, ML-absent warning banner, and CSV export; `fetch_lead_candidates()` LEFT JOINs `lead_scores_ml FINAL` so ML absence never blocks the view

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
**Plans**: 1 plan

Plans:
- [x] 06-01: Implement tracker e-commerce public APIs + consent inheritance + demo-shop SPA affordances

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
**Plans**: 3

Plans:
- [x] 07-01: ClickHouse schema for `retailrocket_raw` database (003_retailrocket_schema.sql — 3 tables + item_latest view, idempotent DDL)
- [x] 07-02: Download + import scripts (`scripts/download_retailrocket.sh` + `scripts/retailrocket/import.py` — 500k-row chunks, load_batch_id short-circuit, insert_deduplication_token, distribution validation)
- [x] 07-03: Smoke query + Makefile targets + .gitignore + data/retailrocket/README.md + Kaggle license evidence

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
**Plans**: 1

Plans:
- [x] 08-01: Implement ClickHouse-aggregated session stats + top-clicked selector panels in Streamlit dashboard with exact/wildcard URL scope semantics and empty states
## v1.2 Phases

### Phase 9: Lead Scoring Data Foundation
**Goal**: Build the ClickHouse data layer (unified events view + per-session feature table) that all v1.2 scoring models consume.
**Depends on**: Phase 7 (Retailrocket tables must exist for the UNION)
**Status**: Complete (2026-04-25)
**Plans**: 1/1 complete

### Phase 10: Rule-Based Lead Scoring Engine
**Goal**: Implement a deterministic, interpretable lead score from behavioral signals. Table-driven rules in Python, applied via a ClickHouse view.
**Depends on**: Phase 9
**Status**: Complete (2026-04-28)
**Plans**: 1/1 complete

### Phase 11: ML Lead Scoring Model
**Goal**: Train a LightGBM binary classifier (converted vs not-converted) on Retailrocket sessions, export it, and serve predictions alongside rule-based scores.
**Depends on**: Phase 10
**Status**: Complete (2026-04-30)
**Plans**: 1/1 complete

### Phase 12: Lead Identification Dashboard
**Goal**: Surface the downstream output of both the rule-based and ML scoring pipelines (from Phases 10 and 11) directly inside the Streamlit UI, allowing marketers/sales reps to visualize their lead funnel and inspect highly-scored candidate sessions.
**Depends on**: Phase 10 (Rule-Based Engine), Phase 11 (ML Engine)
**Requirements**: LEAD-02
**Notes for implementers**:
  - Create a new "Leads" or "Intelligence" tab in the Streamlit application to separate this view from the heatmap visuals.
  - Queries should join data from `analytics.lead_scores_rule_based` and `analytics.lead_scores_ml` to present unified lead profiles to the user.
  - Rely on ClickHouse for ranking and order calculations (`ORDER BY ml_lead_score DESC LIMIT ...`). Do not load the entire table into Python.
**Success Criteria** (what must be TRUE):
  1. Dashboard contains a new "Leads" tab.
  2. Tab presents a distribution chart (e.g., pie or bar) showing the proportion of sessions in 'hot', 'warm', and 'cold' tiers.
  3. Displays a ranked data table of the top highest-scoring sessions (incorporating both the discrete rule score and the ML percentage).
  4. Users can expand or select a specific lead from the table to view the raw JSON `rule_contributions` that generated the score.
**Status**: Complete (2026-04-29)
**Plans**: 1/1 complete

Plans:
- [x] 12-01: Implement ClickHouse queries in `dashboard/` to fetch top N leads and score tier distribution, scaffold Streamlit Leads page with distribution chart, ranked table, rules_fired breakdown, and CSV export.

---

## v2.0 Phases

### Phase 13: CTGAN Behavioral Simulator
**Goal**: Train a CTGAN (Conditional Tabular GAN) on `analytics.session_features` to generate synthetic e-commerce sessions with realistic behavioral distributions, providing a controlled training/augmentation corpus for the ML scorer and the simulation engine.
**Depends on**: Phase 9 (session_features view), Phase 11 (ML scorer provides quality signal for evaluation)
**Requirements**: SYNTH-01, SYNTH-02, SYNTH-03
**Notes for implementers**:
  - Use `ctgan` from the SDV library. Pin version in `requirements-synth.txt` to avoid breaking changes.
  - Training data: export `analytics.session_features` (all columns, both sources) deduplicated by `(anonymous_user_id, session_id)` to a local Parquet file. Do not load all rows into memory at once — use chunked ClickHouse export.
  - Define column metadata explicitly: continuous columns (`max_scroll_pct`, `session_duration_seconds`, `page_views`) vs discrete (`score_tier`, `cart_abandoned`, `source`). Wrong metadata types significantly degrade GAN output quality.
  - Train for 300 epochs minimum, checkpoint every 50. Log Jensen-Shannon divergence per feature at each checkpoint.
  - Condition the GAN on `category` when sampling for product-level prediction (Phase 17) — ensure `category` is included in the training schema.
  - Export trained model to `models/ctgan_sessions.pkl` (joblib). File is gitignored — `make ctgan-train` regenerates it.
  - `scripts/generate_synthetic_sessions.py` inserts generated rows into `analytics.synthetic_sessions`, which mirrors `session_features` schema. Add `is_synthetic BOOL DEFAULT 1` discriminator column.
**Success Criteria** (what must be TRUE):
  1. `make ctgan-train` completes without error and writes `models/ctgan_sessions.pkl` to disk
  2. `python scripts/generate_synthetic_sessions.py --n-sessions 10000` inserts 10,000 rows into `analytics.synthetic_sessions` with no null values in non-nullable feature columns
  3. Jensen-Shannon divergence < 0.1 on all continuous features (verified by `notebooks/ctgan_trainer.ipynb` evaluation cell and committed as `docs/ctgan_evaluation.md`)
  4. Running the generation script a second time with `--overwrite` replaces rows; without it, appends (row-level idempotency via `is_synthetic + session_id` dedup key)
  5. `SELECT source, count() FROM analytics.synthetic_sessions GROUP BY source` shows a realistic source-label distribution consistent with the training split
**Plans**: 3

Plans:
- [ ] 13-01: ClickHouse schema for `analytics.synthetic_sessions` table + `requirements-synth.txt` + `make ctgan-train` Makefile target
- [ ] 13-02: CTGAN training notebook (`notebooks/ctgan_trainer.ipynb`) — data export, column metadata, 300-epoch training, JS divergence evaluation, model export to `models/ctgan_sessions.pkl`
- [ ] 13-03: `scripts/generate_synthetic_sessions.py` CLI (--n-sessions, --category-filter, --overwrite), ML scorer integration, `analytics.synthetic_sessions` insert, `docs/ctgan_evaluation.md`

---

### Phase 14: Simulation Engine (Mesa / SimPy)
**Goal**: Build an agent-based e-commerce traffic simulator that generates realistic event streams (not just session aggregates) by replaying CTGAN-sampled behavioral profiles through the live Redpanda pipeline — enabling "what-if" scenario testing for lead acquisition strategies.
**Depends on**: Phase 13 (CTGAN model provides behavioral priors for agent initialization)
**Requirements**: SIM-01, SIM-02, SIM-03
**Notes for implementers**:
  - Use Mesa framework for agent-based modeling. Each agent represents one visitor session.
  - Three agent types: `BrowserAgent` (click/scroll/product_view only), `BuyerAgent` (conversion_probability from ML calibrated output), `AbandonerAgent` (adds to cart then exits — tests abandonment detection).
  - Agents draw their behavioral profile (page_views, scroll_pct, product_views, etc.) from `analytics.synthetic_sessions` sampled via CTGAN model.
  - Event emission: simulator pushes events directly to the Redpanda topic via the same RudderStack SDK path as the live tracker — all downstream ClickHouse tables and dashboard panels receive simulated events transparently.
  - Simulated sessions use `session_id` prefixed `sim_` and `anonymous_user_id` prefixed `sim_` so they are distinguishable in ClickHouse queries.
  - CLI: `scripts/run_simulation.py --n-agents 1000 --duration-minutes 60 --seed 42`
**Success Criteria** (what must be TRUE):
  1. A 100-agent, 10-minute simulation (`--n-agents 100 --duration-minutes 10 --seed 0`) writes events to `analytics.click_events` within 30 seconds of completion, visible via `SELECT count() FROM analytics.click_events WHERE session_id LIKE 'sim_%'`
  2. The three agent types produce distinguishable behavioral signals: `BuyerAgent` sessions have `purchase_count > 0`, `AbandonerAgent` sessions have `add_to_cart_count > 0 AND purchase_count = 0`, `BrowserAgent` sessions have both equal to 0
  3. Running `make simulate` with `--seed 42` twice produces the same event count (deterministic replay)
  4. The Streamlit dashboard's session stats and heatmap panels reflect simulated events without code changes (events are indistinguishable to the dashboard layer from real traffic, except for the `sim_` prefix queryable via URL filter)
  5. Simulation log (emitted to stdout) reports: total events emitted, conversion rate achieved, session duration distribution mean ± std
**Plans**: 3

Plans:
- [ ] 14-01: Agent definitions (`src/simulation/agents.py`) — BrowserAgent, BuyerAgent, AbandonerAgent with CTGAN-sampled behavioral profiles
- [ ] 14-02: Mesa environment (`src/simulation/ecommerce_env.py`) + Redpanda event emission bridge + `scripts/run_simulation.py` CLI
- [ ] 14-03: `make simulate` Makefile target + smoke test (100-agent, 10-min) + simulation log format doc

---

## v2.1 Phases

### Phase 15: Lead Profiling & LLM Context Builder
**Goal**: Build the context-assembly layer that translates a lead's behavioral signals into a structured prompt payload for the LLM, enabling personalized sales script generation.
**Depends on**: Phase 12 (lead identification — ranked candidates must exist in ClickHouse)
**Requirements**: AI-01, AI-02
**Notes for implementers**:
  - Use Claude API (`claude-sonnet-4-6`) via the Anthropic SDK. Include prompt caching headers (`cache_control: {"type": "ephemeral"}`) on the system prompt — the per-tier template is static, so cache hit rates should be high.
  - PII constraint: context object must use `anonymous_user_id` only — never email, IP, or real name.
  - One template per score tier (hot / warm / cold). Templates in `src/ai/templates/`.
  - Log all LLM calls to `analytics.ai_script_log` ClickHouse table: `lead_id`, `tier`, `model`, `prompt_tokens`, `cache_tokens`, `output_tokens`, `cost_usd`, `generated_at`.
**Success Criteria** (what must be TRUE):
  1. `python -c "from src.ai.lead_profiler import build_script; print(build_script('anon_123'))"` returns a non-empty personalized sales script in < 3 seconds
  2. System prompt caching is active — the second call for any lead in the same tier returns `cache_tokens > 0` in the API response
  3. LLM call is logged to `analytics.ai_script_log` with correct token counts and cost estimate (at $3/MTok input, $15/MTok output for Sonnet)
  4. Passing an `anonymous_user_id` that has no lead scores returns a graceful error string, not an exception
**Plans**: 2

Plans:
- [ ] 15-01: `src/ai/lead_profiler.py` + `src/ai/prompt_builder.py` — lead context assembly + per-tier prompt templates with prompt caching
- [ ] 15-02: `src/ai/llm_client.py` (Claude API, Sonnet 4.6, cached system prompt) + `analytics.ai_script_log` ClickHouse table + `make test-ai` target

---

### Phase 16: AI Script Generation Dashboard Panel
**Goal**: Surface the LLM script generation capability directly in the Streamlit Leads page — one button click per lead row generates a personalized sales outreach script.
**Depends on**: Phase 15 (LLM context builder must be callable from the dashboard)
**Requirements**: AI-03
**Notes for implementers**:
  - "Generate Script" button on each Leads table row. Use `st.spinner` for the async wait.
  - Display the generated script in `st.text_area` with a copy-to-clipboard button.
  - Show token usage and estimated cost sourced from `analytics.ai_script_log` below the script output.
  - Script history panel: last 10 generated scripts for the current browser session, queryable from `ai_script_log`.
**Success Criteria** (what must be TRUE):
  1. Clicking "Generate Script" on any lead row produces a non-empty script in < 5 seconds with no page reload
  2. Token usage and cost estimate are displayed below the script text
  3. The script history panel shows the last 10 generated scripts for the session
  4. `make test-ai` generates a script for the top-scored lead and asserts: non-empty output, < 500 words, logged in `ai_script_log`
**Plans**: 1

Plans:
- [ ] 16-01: "Generate Script" button + spinner + `st.text_area` output + token/cost display + script history panel in `dashboard/pages/leads.py`

---

## v2.2 Phases

### Phase 17: Product Input & Lead Prediction Interface
**Goal**: Provide an operator-facing Streamlit page where an e-commerce manager enters a product's attributes (name, category, price, description keywords) and receives ML-backed predictions: expected conversion rate, lead tier distribution, top behavioral signals, and a sample of lookalike synthetic sessions — giving product owners actionable intelligence before a product launches.
**Depends on**: Phase 13 (CTGAN model trained — needed to sample synthetic sessions), Phase 11 (ML scorer loadable — needed to score sampled sessions), Phase 14 (optional dependency: if real-time simulation is preferred over static CTGAN sampling for richer event-level predictions)
**Requirements**: PRED-01, PRED-02, PRED-03
**Notes for implementers**:
  - Core prediction flow: (1) accept product attributes from the form, (2) sample N synthetic sessions from CTGAN conditioned on `category`, (3) run `MLScorer` on those sessions, (4) aggregate: conversion_rate_pct = mean(ml_lead_score), tier_distribution = count by tier bucket, top_features = feature importances weighted by session scores.
  - `src/prediction/product_predictor.py` is the backend; it must be importable independently of Streamlit (for CLI/batch use via `make predict-product`).
  - Condition CTGAN sampling on `category` — the model must have been trained with `category` as a discrete column (enforced in Phase 13 plan 02). If the requested category is unseen, fall back to unconditional sampling with a warning.
  - Log every prediction to `analytics.prediction_log` ClickHouse table: `product_name`, `category`, `price`, `keywords`, `n_sessions_sampled`, `conversion_rate_pct`, `tier_hot_pct`, `tier_warm_pct`, `tier_cold_pct`, `predicted_at`. This enables trend tracking ("does adding a discount keyword improve conversion predictions?").
  - Form validation is client-side (Streamlit `st.form` validators): category must be selected from `retailrocket_raw.category_tree`, price must be > 0, at least one field must be non-empty.
  - The "prediction" is a simulation over synthetic data — not a guarantee. Add a disclaimer note below the results.
**Success Criteria** (what must be TRUE):
  1. Submitting a valid product form returns prediction results in < 10 seconds (sampling 1,000 CTGAN sessions + ML scoring + aggregation)
  2. Conversion rate and tier distribution are derived from ≥ 1,000 CTGAN-sampled sessions scored by the Phase 11 ML model; the sample size is shown in the UI
  3. Selecting different categories produces noticeably different tier distributions (model is sensitive to category — verified by spot-checking Electronics vs. Clothing categories)
  4. Every form submission writes one row to `analytics.prediction_log`; `make predict-product --product "Test" --category 213` runs the same pipeline from CLI and also writes to the log
  5. Invalid form inputs (empty category, price ≤ 0) show inline validation messages without triggering a backend call; unseen category falls back to unconditional sampling with a visible warning banner
  6. Results page shows: conversion rate gauge, tier pie chart, top 5 behavioral signals bar chart, and a table of the top 10 scored synthetic sessions with their feature values
**Plans**: 3

Plans:
- [ ] 17-01: `src/prediction/product_predictor.py` — CTGAN conditional sampling + ML scorer pipeline, `predict_for_product(category, price, keywords, n_sessions)` returns structured prediction dict
- [ ] 17-02: `dashboard/pages/predict.py` — Streamlit product input form (category select from ClickHouse, price input, keywords text) + results display (conversion gauge, tier pie, feature bar chart, top sessions table) + disclaimer note
- [ ] 17-03: `analytics.prediction_log` ClickHouse schema + `make predict-product` CLI target + `infra/clickhouse/sql/004_prediction_log.sql` (idempotent DDL)

---

## v2.3 Phases

### Phase 18: Augmented Training Pipeline
**Goal**: Retrain the LightGBM lead scorer on a combined corpus of real Retailrocket sessions + CTGAN synthetic sessions to improve recall on the minority class. Introduce model versioning so the active model can be swapped without code changes.
**Depends on**: Phase 13 (synthetic sessions in `analytics.synthetic_sessions`), Phase 11 (baseline model for comparison)
**Requirements**: ML-05, ML-06
**Success Criteria** (what must be TRUE):
  1. `make build-augmented-dataset` exports real + synthetic session rows, merges them, and writes `data/augmented_training.parquet` with class distribution logged
  2. `notebooks/augmented_training.ipynb` trains LightGBM v2 and its Recall@K (top 10%) is compared against the v1 baseline; result committed to `docs/model_card_v2.md`
  3. `models/lead_scorer_lgbm_v2.pkl` exists after `make train-augmented`
  4. `make select-model VERSION=v2` switches `models/ACTIVE_MODEL` to `v2`; subsequent `make score-sessions --dry-run` logs "active model: v2"
  5. `MLScorer` continues to work with `VERSION=v1` (no regression on the baseline scorer)
**Plans**: 3 plans

Plans:
- [ ] 18-01: `scripts/build_augmented_dataset.py` — real + synthetic data merge, labelling, stratified split, Parquet export
- [ ] 18-02: `notebooks/augmented_training.ipynb` — augmented LightGBM training, v1 vs v2 comparison, feature importance delta, model card
- [ ] 18-03: `src/scoring/model_registry.py` + `models/ACTIVE_MODEL` + `make select-model` + `MLScorer` path update

---

### Phase 19: Prediction REST API Service
**Goal**: Expose the product prediction pipeline (Phase 17) as a standalone FastAPI service in Docker Compose, decoupling ML inference from the Streamlit dashboard process and enabling programmatic access.
**Depends on**: Phase 17 (product_predictor.py must be tested), Phase 18 (active model versioning in place)
**Requirements**: API-01, API-02, API-03
**Success Criteria** (what must be TRUE):
  1. `make api-up` starts the `prediction-api` container; `GET http://localhost:8000/health` returns HTTP 200 with `{"status": "ok"}`
  2. `POST http://localhost:8000/predict/product` with a valid payload returns HTTP 200 in < 10 seconds with `conversion_rate_pct`, `tier_distribution`, and `n_sessions_sampled`
  3. Every successful POST writes one row to `analytics.prediction_log`
  4. The Streamlit predict page (`dashboard/pages/predict.py`) calls the API endpoint (no direct import of `ctgan` or `lightgbm` in the dashboard process)
  5. The prediction history expander on the predict page loads the last 5 predictions from `GET /predictions/history`
**Plans**: 3 plans

Plans:
- [ ] 19-01: `src/api/main.py` + `src/api/schemas.py` + `src/api/dependencies.py` + `requirements-api.txt` + unit tests
- [ ] 19-02: `docker-compose.yml` `prediction-api` service + `make api-up` / `make api-test` Makefile targets
- [ ] 19-03: `dashboard/pages/predict.py` updated to call API + prediction history expander

---

## v2.4 Phases

### Phase 20: ML Monitoring & CI Hardening
**Goal**: Add model drift detection, pipeline observability (Redpanda Console + ClickHouse slow query panel), and a GitHub Actions CI pipeline that validates linting, unit tests, and Docker builds on every pull request.
**Depends on**: Phase 19 (full system running in Docker Compose)
**Requirements**: OPS-01, OPS-02, OPS-03
**Success Criteria** (what must be TRUE):
  1. `make check-drift` prints a drift report (JSD per feature, status ok/warn/fail) and writes one row to `analytics.drift_log`
  2. `http://localhost:8080` (Redpanda Console) shows topic throughput and consumer group lag without any code changes
  3. The Streamlit admin sidebar shows a "Model Health" section with the last drift check result and a slow-query table from `system.query_log`
  4. Pushing a branch with a lint error causes the GitHub Actions CI `lint` job to fail
  5. Pushing a branch with a failing unit test causes the `unit-tests` job to fail; Docker build failure causes `docker-build` to fail
**Plans**: 3 plans

Plans:
- [ ] 20-01: `src/monitoring/drift_detector.py` + `scripts/check_model_drift.py` + `make check-drift` + `analytics.drift_log` + Streamlit Model Health panel
- [ ] 20-02: `redpandadata/console` in `docker-compose.yml` + slow-query panel in Streamlit sidebar + `make console-up`
- [ ] 20-03: `.github/workflows/ci.yml` (lint + unit-tests + docker-build) + `requirements-dev.txt` + `make lint` + README badge

---

## Progress

**Execution Order:**
```
Phases 1–4 (v1.0)
  ↓
Phase 5 → {6, 7, 8 in parallel} (v1.1)
  ↓
Phase 9 → Phase 10 → Phase 11 → Phase 12 (v1.2)
  ↓
Phase 13 (CTGAN) ──────────────┐
                                ├── can run in parallel once Phase 13 ships
Phase 14 (Simulation) ─────────┘  (v2.0)
  ↓
Phase 15 (LLM Context) → Phase 16 (AI Panel)  (v2.1)  ← parallel with Phases 17-18
  ↓
Phase 17 (Product Prediction Interface)  (v2.2)
  ↓
Phase 18 (Augmented Training) ─────────┐
                                        ├── both depend on Phase 17; 18 → 19 sequential
Phase 19 (Prediction API Service) ─────┘  (v2.3)
  ↓
Phase 20 (Monitoring & CI)  (v2.4)
```

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Streaming and Storage Backbone | v1.0 | 3/3 | Complete | 2026-04-16 |
| 2. JS Tracker and Event Ingestion Pipeline | v1.0 | 4/4 | Complete | 2026-04-16 |
| 3. Screenshot Capture Service | v1.0 | 2/2 | Complete | 2026-04-16 |
| 4. Heatmap Computation and Core Dashboard | v1.0 | 4/4 | Complete | 2026-04-16 |
| 5 (v1.0). Analytics Features | v1.0 | 0/0 | Dropped — rolled into v1.1 | 2026-04-18 |
| 5. E-commerce Event Schema | v1.1 | 3/3 | Complete | 2026-04-19 |
| 6. E-commerce Tracker API | v1.1 | 1/1 | Complete | 2026-04-19 |
| 7. Retailrocket Import | v1.1 | 3/3 | Complete | 2026-04-19 |
| 8. Rolled-over Dashboard Panels | v1.1 | 1/1 | Complete | 2026-04-19 |
| 9. Lead Scoring Data Foundation | v1.2 | 1/1 | Complete | 2026-04-25 |
| 10. Rule-Based Lead Scoring Engine | v1.2 | 1/1 | Complete | 2026-04-28 |
| 11. ML Lead Scoring Engine | v1.2 | 1/1 | Complete | 2026-04-30 |
| 12. Lead Identification Dashboard | v1.2 | 1/1 | Complete | 2026-04-29 |
| 13. CTGAN Behavioral Simulator | v2.0 | 3/3 | Complete | 2026-05-10 |
| 14. Simulation Engine (Mesa) | v2.0 | 3/3 | Complete | 2026-05-10 |
| 15. Lead Profiling & LLM Context Builder | v2.1 | 2/2 | Complete | 2026-05-10 |
| 16. AI Script Generation Panel | v2.1 | 1/1 | Complete | 2026-05-10 |
| 17. Product Input & Lead Prediction Interface | v2.2 | 3/3 | Complete | 2026-05-10 |
| 18. Augmented Training Pipeline | v2.3 | 3/3 | Complete | 2026-05-10 |
| 19. Prediction REST API Service | v2.3 | 3/3 | Complete | 2026-05-10 |
| 20. ML Monitoring & CI Hardening | v2.4 | 3/3 | Complete | 2026-05-10 |
