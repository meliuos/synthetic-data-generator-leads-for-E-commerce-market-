---
phase: 01-streaming-and-storage-backbone
plan: 02
subsystem: database
tags: [clickhouse, kafka, redpanda, mergetree, materialized-view]
requires:
  - phase: 01-01
    provides: Local stack with Redpanda and ClickHouse containers
provides:
  - ClickHouse 3-table ingestion model (Kafka queue + MV + MergeTree)
  - One-command schema apply workflow
  - Verified ORDER BY contract for Phase 1 analytics table
affects: [phase-01-03-smoke-test, phase-02-ingestion]
tech-stack:
  added: [ClickHouse Kafka engine, MergeTree table, materialized view]
  patterns: ["Idempotent SQL schema applied via container exec automation"]
key-files:
  created: [infra/clickhouse/sql/001_events_schema.sql, infra/clickhouse/users.d/async_insert.xml]
  modified: [scripts/apply-schema.sh, Makefile, docker-compose.yml, README.md]
key-decisions:
  - "Lock click_events ORDER BY to (page_url, event_type, toDate(event_time)) per roadmap contract."
  - "Use users.d profile settings for async_insert to satisfy ClickHouse config validation rules."
patterns-established:
  - "Apply schema with make schema after stack startup."
  - "Verify schema contracts through SHOW TABLES and system.tables sorting_key checks."
duration: 20min
completed: 2026-04-15
---

# Phase 1 Plan 2: ClickHouse 3-Table Schema Summary

**ClickHouse now ingests Redpanda topic events through a Kafka queue table and materialized view into a MergeTree table with the locked Phase 1 sorting key.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-04-14T23:33:12Z
- **Completed:** 2026-04-14T23:53:44Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- Added idempotent ClickHouse schema for `events_queue`, `events_mv`, and `click_events` in the analytics database.
- Added `make schema` workflow through `scripts/apply-schema.sh` for one-command schema application.
- Verified table creation and required sorting key: `page_url, event_type, toDate(event_time)`.

## Task Commits

1. **Task 1: Add SQL schema for analytics ingestion** - `836b41c` (feat)
2. **Task 2: Add schema apply script and make target** - `9f13c5f` (chore)
3. **Task 3: Verify schema and document query checks** - `ec879a8` (fix)

## Files Created/Modified
- `infra/clickhouse/sql/001_events_schema.sql` - Core ingestion schema with Kafka source, MV, and MergeTree target.
- `scripts/apply-schema.sh` - Container-aware schema apply automation.
- `Makefile` - Added `schema` target.
- `docker-compose.yml` - Corrected Redpanda/ClickHouse healthchecks and ClickHouse users profile mount.
- `infra/clickhouse/users.d/async_insert.xml` - Async insert profile settings in valid config location.
- `README.md` - Added schema apply and verification instructions.

## Decisions Made
- Kept schema idempotent and runnable repeatedly to support local reset workflows.
- Used explicit ClickHouse credentials in scripts to match non-default container user configuration.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed Redpanda healthcheck flag incompatibility**
- **Found during:** Task 3 (schema verification)
- **Issue:** Redpanda container remained unhealthy because `rpk cluster health` no longer accepts `--brokers` in this image.
- **Fix:** Updated compose healthcheck to use supported `rpk cluster health --exit-when-healthy` invocation.
- **Files modified:** `docker-compose.yml`
- **Verification:** `docker compose ps -a` reported Redpanda as healthy.
- **Committed in:** `ec879a8`

**2. [Rule 3 - Blocking] Fixed invalid ClickHouse async_insert config location**
- **Found during:** Task 3 (schema verification)
- **Issue:** ClickHouse failed startup because `async_insert` was mounted under `config.d` (server config), but it is a user-level setting.
- **Fix:** Moved config to `users.d` profile file and updated compose mount path.
- **Files modified:** `infra/clickhouse/users.d/async_insert.xml`, `docker-compose.yml`
- **Verification:** ClickHouse became healthy and schema applied successfully.
- **Committed in:** `ec879a8`

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both fixes were necessary to make schema verification executable; no scope creep.

## Issues Encountered
- Long initial image pull/build time on first `make up` execution.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 01-03 smoke test can now validate produce-to-ingest latency against a stable schema.
- Pipeline is ready for tracker integration work in Phase 2 once smoke test passes.

---
*Phase: 01-streaming-and-storage-backbone*
*Completed: 2026-04-15*
