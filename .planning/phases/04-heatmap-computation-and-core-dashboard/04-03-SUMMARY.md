---
phase: 04-heatmap-computation-and-core-dashboard
plan: 03
subsystem: ui
tags: [streamlit, plotly, clickhouse, filters, wildcard]

requires:
  - phase: 04-02
    provides: Screenshot-backed Plotly overlay rendering and ClickHouse click aggregation
provides:
  - Shared wildcard URL scoping for dashboard queries
  - Single click/scroll/hover mode switcher in the Streamlit shell
  - Normalized filter reuse across every heatmap mode
affects: [04-04, future filter-driven dashboard views]

tech-stack:
  added: []
  patterns: [shared page-scope normalization, single control surface for mode selection]

key-files:
  created: []
  modified: [dashboard/app.py]

key-decisions:
  - "Use one normalized URL filter value for every mode instead of re-parsing wildcard text per query."
  - "Expose mode switching in the dashboard UI now so later view helpers can plug into the same shell."
  - "Keep the screenshot refresh workflow unchanged while the data scope changes underneath it."

patterns-established:
  - "Pattern 1: Exact page selection and wildcard page scopes share the same filter contract."
  - "Pattern 2: The control surface owns page scope and mode state; the render path stays shared."

duration: 1m
completed: 2026-04-16
---

# Phase 4 Plan 03: Filter and Mode Controls Summary

**Wildcard URL scoping and click/scroll/hover mode controls added to the Streamlit dashboard, all routed through one normalized filter value.**

## Performance

- **Duration:** 1m
- **Started:** 2026-04-16T00:45:54+01:00
- **Completed:** 2026-04-16T00:46:44+01:00
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments

- Added the wildcard page scope input and normalized it with the selected URL before querying ClickHouse.
- Added the click, scroll, and hover mode switcher while preserving the existing screenshot refresh flow.
- Kept the app on a single render path so the later scroll/hover views can attach cleanly.

## Task Commits

1. **Task 1: Build URL filter normalization helpers** - `30f4a49`
2. **Task 2: Add URL filter and heatmap mode controls to the dashboard** - `30f4a49`

**Plan metadata:** `30f4a49` (feat: add URL filter and mode controls)

## Files Created/Modified

- `dashboard/app.py` - Adds the wildcard input, mode switcher, and normalized filter usage.

## Decisions Made

- Keep URL wildcard translation centralized so exact and wildcard scopes behave the same way everywhere.
- Map the UI label `Hover` to the `mousemove` event type used by the query layer.
- Preserve the selected screenshot viewport while the active dataset changes via mode or URL scope.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None beyond the existing environment note about using an isolated Python environment for runtime validation.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The dashboard now has a single control surface for page scope and mode selection.
- The scroll-band and hover-specific rendering logic can be isolated into view helpers without changing the UI shell.

---
*Phase: 04-heatmap-computation-and-core-dashboard*
*Completed: 2026-04-16*