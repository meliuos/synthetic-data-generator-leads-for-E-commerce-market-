---
phase: 01-streaming-and-storage-backbone
plan: 03
subsystem: testing
tags: [smoke-test, redpanda, clickhouse, kafka, ingestion]
requires:
  - phase: 01-02
    provides: ClickHouse schema and running ingestion stack
provides:
  - Repeatable produce-to-ingest smoke test automation
  - 5-second ingestion SLA verification script
  - Makefile/README workflow for pipeline validation
affects: [phase-02-ingestion, phase-04-dashboard]
tech-stack:
  added: [rpk topic producer smoke workflow]
  patterns: ["Latency-gated smoke validation before higher-layer tracker work"]
key-files:
  created: [scripts/smoke-test.sh]
  modified: [Makefile, README.md]
key-decisions:
  - "Use Redpanda rpk producer in smoke test for deterministic local delivery."
  - "Create topic idempotently inside smoke script to avoid false negatives on fresh environments."
patterns-established:
  - "Run make schema then make smoke-test as baseline pipeline gate."
  - "Smoke tests assert ingestion SLA with explicit timeout checks."
duration: 3min
completed: 2026-04-15
---

# Phase 1 Plan 3: Manual Produce to MergeTree Smoke Test Summary

**A scripted smoke test now publishes a JSON event to Redpanda and verifies it appears in ClickHouse `click_events` within the required 5-second window.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-14T23:56:44Z
- **Completed:** 2026-04-14T23:59:28Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Added `scripts/smoke-test.sh` to produce one event and poll ClickHouse for ingestion completion.
- Added `make smoke-test` workflow and documented the command sequence in README.
- Executed smoke test successfully with pass output under 5 seconds.

## Task Commits

1. **Task 1: Add reproducible smoke test script** - `b0b2bc7` (test)
2. **Task 2: Add Make target and documentation for smoke test** - `39e2f11` (docs)
3. **Task 3: Execute smoke test and capture plan completion artifacts** - `5a79510` (fix)

## Files Created/Modified
- `scripts/smoke-test.sh` - Produces event and enforces ingestion timeout.
- `Makefile` - Adds `smoke-test` command target.
- `README.md` - Documents smoke test execution path.

## Decisions Made
- Smoke producer path uses `rpk topic produce` instead of REST proxy for more consistent local behavior.
- Topic creation is embedded in script to support first-run environments.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Replaced REST proxy produce path with rpk producer**
- **Found during:** Task 3 (smoke execution)
- **Issue:** Initial REST-based produce path did not create/write to topic reliably in this local configuration, causing false smoke failures.
- **Fix:** Added idempotent topic creation and switched publish step to `rpk topic produce`.
- **Files modified:** `scripts/smoke-test.sh`
- **Verification:** `make smoke-test` passed with row visible in `analytics.click_events` within 5 seconds.
- **Committed in:** `5a79510`

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Fix was required to make smoke verification reliable; scope remained within plan intent.

## Issues Encountered
- Transient local terminal session closures during command execution; rerun in fresh shell resolved without code changes.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 1 success criteria are validated end-to-end.
- Phase 2 can now build tracker ingestion against a verified storage backbone.

---
*Phase: 01-streaming-and-storage-backbone*
*Completed: 2026-04-15*
