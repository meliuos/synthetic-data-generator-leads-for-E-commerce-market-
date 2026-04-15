---
phase: 04-heatmap-computation-and-core-dashboard
plan: 04
subsystem: ui
tags: [streamlit, plotly, clickhouse, scroll, mousemove]

requires:
  - phase: 04-03
    provides: Shared filter controls and mode selection for the Streamlit dashboard
provides:
  - Scroll heatmap bands that span the screenshot width
  - Hover/mousemove heatmap rendering on the same screenshot overlay
  - A mode dispatcher that keeps the dashboard shell shared across all views
affects: [phase 05 dashboard follow-on work, future analytics modes]

tech-stack:
  added: []
  patterns: [mode-specific view helpers, scroll-band expansion, shared render dispatcher]

key-files:
  created: [dashboard/heatmap_views.py]
  modified: [dashboard/app.py]

key-decisions:
  - "Render scroll data as horizontal bands by expanding the aggregated row across the screenshot width."
  - "Keep hover on the same screenshot-backed Plotly overlay path as click heatmaps."
  - "Dispatch by mode in a shared helper so the Streamlit shell stays simple."

patterns-established:
  - "Pattern 1: Mode-specific transformation lives outside the main Streamlit file."
  - "Pattern 2: The app queries pre-binned data and delegates layout semantics to helper modules."

duration: 2m
completed: 2026-04-16
---

# Phase 4 Plan 04: Scroll and Hover Views Summary

**Scroll-band and mousemove heatmaps rendered over the same cached screenshots through a shared mode dispatcher, completing the phase 4 dashboard views.**

## Performance

- **Duration:** 2m
- **Started:** 2026-04-16T00:46:44+01:00
- **Completed:** 2026-04-16T00:48:10+01:00
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added a scroll view helper that expands each depth bin into full-width horizontal bands.
- Added a mode dispatcher so click, scroll, and hover all share the same screenshot-backed shell.
- Verified the finished Streamlit app starts cleanly in the isolated dashboard environment.

## Task Commits

1. **Task 1: Implement scroll and hover aggregation helpers** - `c898d33`
2. **Task 2: Wire scroll depth and hover heatmap rendering into the dashboard** - `c898d33`

**Plan metadata:** `c898d33` (feat: add scroll and hover heatmap views)

## Files Created/Modified

- `dashboard/heatmap_views.py` - Expands scroll bands and dispatches the render mode.
- `dashboard/app.py` - Routes the selected mode through the shared view helper.

## Decisions Made

- Use a shared screenshot overlay for all modes rather than introducing separate canvases.
- Expand scroll rows across the width so the visual reads as a depth band, not a point cloud.
- Keep hover on the same aggregated query shape as click so the UI remains predictable.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The system Python environment was missing the dashboard dependencies; validation used the isolated `.venv-phase4` environment with the required packages installed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 4 is fully represented in the dashboard shell and ready for downstream analytics work.
- The shared query/filter/view split makes it straightforward to add future modes without rewriting the app layout.

---
*Phase: 04-heatmap-computation-and-core-dashboard*
*Completed: 2026-04-16*