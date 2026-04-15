---
phase: 04-heatmap-computation-and-core-dashboard
plan: 01
subsystem: database
tags: [clickhouse, streamlit, pandas, heatmap, query-builder]
requires:
  - phase: 01-streaming-and-storage-backbone
    provides: ClickHouse click_events schema and ingestion path
  - phase: 03-screenshot-capture-service
    provides: Dashboard foundation for screenshot-backed visual overlays
provides:
  - Reusable ClickHouse heatmap aggregation query helpers
  - Parameterized exact and wildcard URL filtering for dashboard queries
  - Dataframe-ready query output contract for Phase 4 rendering
affects: [04-02-PLAN, 04-03-PLAN, 04-04-PLAN]
tech-stack:
  added: [pandas]
  patterns: [parameterized ClickHouse SQL builder, query_df dataframe access for dashboard data contract]
key-files:
  created: [dashboard/heatmap_queries.py]
  modified: [dashboard/requirements.txt]
key-decisions:
  - "Centralized all heatmap aggregation SQL in a dedicated module instead of embedding SQL in Streamlit view code."
  - "Implemented wildcard URL support using '*' to '%' translation with LIKE parameterization."
  - "Mapped scroll events to a vertical lane (x=50) while binning y from scroll_pct to keep a consistent x/y aggregation API."
patterns-established:
  - "Dashboard consumes only pre-aggregated 5% bins from ClickHouse, never raw click_events rows."
  - "Heatmap query helpers expose both config-driven and convenience wrapper APIs for app integration."
duration: 9min
completed: 2026-04-15
---

# Phase 4 Plan 1: ClickHouse Heatmap Aggregation Layer Summary

**Parameterized ClickHouse helper module now returns 5% grid-binned heatmap dataframes for exact and wildcard URL filters across click, scroll, and mousemove events.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-04-15T22:24:30Z
- **Completed:** 2026-04-15T22:33:21Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Built `dashboard/heatmap_queries.py` with explicit, parameterized query construction for URL filters, event type, viewport, device type, and optional time windows.
- Implemented 5% coordinate binning in ClickHouse (`round(... / 5) * 5`) and dataframe output via `query_df()` for dashboard-ready consumption.
- Added `pandas==2.2.3` to dashboard dependencies to support dataframe-based query handling.

## Task Commits

Each task was committed atomically:

1. **Task 1: Build ClickHouse heatmap query helpers** - `2cec0f6` (feat)
2. **Task 2: Add dataframe support to the dashboard dependency set** - `b828787` (chore)

**Plan metadata:** Pending (added after SUMMARY/STATE updates)

## Files Created/Modified
- `dashboard/heatmap_queries.py` - Query config, SQL builder, URL wildcard/exact filtering, and dataframe-returning helper APIs.
- `dashboard/requirements.txt` - Added pandas for dataframe-oriented query result handling.

## Decisions Made
- Kept aggregation in ClickHouse and exposed only binned results in helper APIs to enforce the Phase 4 data contract.
- Added both typed config (`HeatmapQueryConfig`) and a convenience function (`fetch_heatmap_aggregates_for`) to reduce integration friction in `dashboard/app.py`.
- Treated URL wildcards as user-friendly `*` patterns and translated safely to SQL LIKE patterns.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Verification commands assumed `python`, environment provides `python3`**
- **Found during:** Task 1 verification
- **Issue:** `python -m py_compile ...` failed because `python` executable was unavailable.
- **Fix:** Re-ran verification with `python3`.
- **Files modified:** None
- **Verification:** Compile and SQL builder checks completed successfully.
- **Committed in:** N/A (execution environment only)

**2. [Rule 3 - Blocking] System Python is externally managed (PEP 668) for `pip install` verification**
- **Found during:** Task 2 verification
- **Issue:** Direct `pip install -r dashboard/requirements.txt` was blocked in the host environment.
- **Fix:** Performed dependency resolution and import validation inside isolated virtual environments.
- **Files modified:** None
- **Verification:** Requirements resolved and imports succeeded in venv.
- **Committed in:** N/A (execution environment only)

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Verification path adjusted for environment constraints with no scope changes and no behavior changes.

## Issues Encountered
- Host environment lacks a global `python` alias and blocks system `pip` installs; both were resolved via non-invasive verification methods.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Query aggregation contract is in place for overlay rendering and controls in subsequent Phase 4 plans.
- Next implementation can import `dashboard/heatmap_queries.py` directly to request filtered 5% bins for screenshot overlays.

---
*Phase: 04-heatmap-computation-and-core-dashboard*
*Completed: 2026-04-15*
