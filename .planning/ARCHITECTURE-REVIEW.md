# Architecture Review — Lead Intelligence Platform

**Date:** 2026-04-29
**Scope:** v1.0 + v1.1 delivered architecture; pre-v1.2 evaluation

---

## Architecture Overview

The current system follows a strict unidirectional pipeline:

```
Browser (JS Tracker)
  → RudderStack Data Plane (self-hosted, event enrichment + routing)
    → Redpanda (Kafka-API event buffer)
      → ClickHouse (Kafka Engine → Materialized View → MergeTree)
        → Streamlit Dashboard (Plotly overlays, aggregate-only queries)

Playwright Screenshot Service (parallel, shared Docker volume)
```

All components run in a single Docker Compose stack. No external cloud dependencies.

---

## What Is Working Well

### 1. Clean unidirectional data flow
Each layer has a single responsibility and a clear interface contract. The pipeline is easy to
reason about, debug, and extend. Extending the tracker or adding a ClickHouse table doesn't
require touching unrelated layers.

### 2. 3-table ClickHouse ingestion pattern
Kafka Engine queue → Materialized View → MergeTree target is the correct architecture.
Querying the Kafka Engine directly consumes offsets and is correctly avoided everywhere.
Async insert (`async_insert.xml`) prevents "Too many parts" errors that would otherwise arise
from per-event inserts at the RudderStack batch boundary.

### 3. Additive schema evolution
v1.1 extended the schema with `ALTER TABLE ADD COLUMN IF NOT EXISTS` — a metadata-only
operation in ClickHouse that doesn't rewrite data. v1.0 events continue inserting unchanged,
with the 8 new columns reading as NULL. The migration is idempotent and versioned
(`001_events_schema.sql` → `002_ecommerce_schema.sql`). This pattern must be preserved for
all future schema changes.

### 4. ClickHouse-side aggregation discipline
All heatmap and dashboard queries aggregate in SQL (5% grid binning). Python receives
pre-aggregated dataframes (~400 cells, not 50k raw rows). This pattern scales to tens of
millions of events without OOM. It is enforced across all dashboard modules and must remain
non-negotiable in v1.2.

### 5. Defense-in-depth purchase dedup
Two-layer dedup for purchase events: client-side `localStorage` seen-set on `order_id`
(blocks duplicate emits from back-button / form resubmit) + server-side `ReplacingMergeTree`
on the `analytics.orders` table (collapses retries that reached the DB). Both layers are
independently verifiable.

### 6. GDPR compliance
Consent gate implemented in the tracker, pre-opt-in events are blocked at the JS layer before
the SDK initializes. No raw IP storage. Retailrocket CSVs excluded from git (`data/retailrocket/`
in `.gitignore`). Anonymized `anonymous_user_id` (hashed) throughout. This is solid for an
academic defense and the pattern is production-appropriate.

---

## Issues Identified

### ISSUE-01 — Redpanda version pinned at v24.1.10 (minor)
**Severity:** Low
**Current state:** `docker-compose.yml` uses `redpanda:v24.1.10`. Research notes recommend
v26.1.4 (released April 2026).
**Impact:** ~2 years of bug fixes and Kafka API improvements are missing. Functional for the
demo; higher risk in a long-running deployment.
**Fix:** Bump to `redpanda:v26.1.4` in `docker-compose.yml`. No schema or client changes
needed (Kafka API compatible). Retest the smoke test after bump.

---

### ISSUE-02 — No data TTL on `click_events` (minor for demo, missing for production)
**Severity:** Low (academic context) / Medium (production handoff)
**Current state:** `analytics.click_events` has no `TTL` clause. Data accumulates
indefinitely.
**Impact:** Not a problem for the defense demo. For a production deployment or a v2.0 system
that ingests synthetic data at scale, unbounded growth becomes a cost and performance concern.
**Fix:** Add `TTL event_time + INTERVAL 1 YEAR DELETE` to `001_events_schema.sql` as a
comment-annotated recommendation, or define it as an optional migration in v1.2 setup.

---

### ISSUE-03 — Hardcoded credential defaults in docker-compose (hygiene)
**Severity:** Low (academic context)
**Current state:** `CLICKHOUSE_PASSWORD: ${CLICKHOUSE_PASSWORD:-analytics_password}` — the
fallback is a plaintext password visible in the committed file.
**Impact:** Not a security issue in a local-only dev stack, but it is a habit that carries
risk if the compose file is reused for a cloud deployment without reviewing the defaults.
**Fix:** Remove the `:-analytics_password` fallback. Add a `.env.example` file with
placeholder values. Document that `.env` must be created before `docker compose up`.

---

### ISSUE-04 — No observability layer (medium for production path)
**Severity:** Medium (if the system is demoed live with real traffic)
**Current state:** No monitoring for Redpanda consumer lag, ClickHouse query performance,
RudderStack delivery failures, or Streamlit response times.
**Impact:** If events silently fail (Kafka consumer lag grows, MV query fails, RudderStack
drops a batch), the dashboard shows stale data with no alert. In a live demo this is a risk.
**Fix (v1.2):**
- Add Redpanda Console (`redpandadata/console`) as a Compose service — it's free, Docker-ready,
  and gives consumer-lag visibility with no code changes.
- Add a `system.query_log` summary panel to the Streamlit admin sidebar (last 10 slow queries).
- These are low-effort, high-confidence additions that raise demo confidence.

---

### ISSUE-05 — Screenshot staleness: no TTL or auto-refresh (minor)
**Severity:** Low
**Current state:** Screenshots are cached by URL+viewport hash. A manual "Refresh Screenshot"
button exists in the dashboard, but there is no scheduled or TTL-based refresh.
**Impact:** If the tracked page changes layout after screenshots are cached, the heatmap
overlay will drift. Manageable during a controlled demo; a real deployment needs a policy.
**Fix:** Define a `SCREENSHOT_TTL_HOURS` environment variable in the screenshot service (default:
24). If the cached file is older than TTL, re-capture on next dashboard load. Document the
default in the service README.

---

### ISSUE-06 — No unified view across `click_events` and `retailrocket_raw.events` (v1.2 gap)
**Severity:** Medium (blocks v1.2 ML work)
**Current state:** Live tracker events land in `analytics.click_events`. Retailrocket import
(Phase 7, pending) lands in `retailrocket_raw.events`. They use compatible types (confirmed
in DATASET.md) but there is no cross-database unified view.
**Impact:** v1.2 lead scoring SQL and ML feature pipelines will need to query both tables.
Without a unified view, every v1.2 query duplicates the UNION logic.
**Fix (Phase 9 — v1.2 setup):** Define `analytics.unified_events` as a read-time UNION ALL
view merging the two event sources with a `source` discriminator column (`'live'` vs
`'retailrocket'`). This is a zero-storage view; no data is copied.

---

### ISSUE-07 — RudderStack as a single point of failure (acceptable for demo)
**Severity:** Low (academic) / High (production)
**Current state:** Single RudderStack container; no replica, no retry persistence to disk.
**Impact:** If RudderStack crashes during a live demo, event ingestion stops. Recovery requires
`docker compose restart rudderstack`.
**Fix:** For v2+ production context, configure RudderStack's persistent job store to use the
existing Postgres container (already wired — `rudder-postgres` in compose). This is already
partially in place; verify `JOBS_DB_*` env vars are activating the retry queue, not just
the config DB.

---

## Architecture Verdict

The current architecture is **well-designed for its scope**. The pipeline is correct, the
ClickHouse schema strategy is sound, and the GDPR posture is solid. The issues identified are
hygiene-level (credentials, versions) or forward-looking (observability, unified view). None
require a rebuild. The system is ready for v1.2 feature work once Phase 7 ships.

**Do not redesign:** The 3-table ClickHouse pattern, the consent gate, the coordinate
normalization approach, and the aggregation-in-SQL discipline are all correct and should be
preserved as-is into v1.2 and beyond.

---
*Written: 2026-04-29*
