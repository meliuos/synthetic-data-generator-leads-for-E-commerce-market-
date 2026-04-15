---
phase: 04-heatmap-computation-and-core-dashboard
plan: 02
subsystem: ui
tags: [streamlit, plotly, clickhouse, pandas, screenshots]

requires:
  - phase: 04-01
    provides: ClickHouse 5% heatmap binning helpers and URL predicate support
provides:
  - Screenshot-backed Plotly click heatmap overlays for desktop and mobile viewports
  - Shared URL filter normalization for exact and wildcard page scopes
  - Dashboard dependency pin for Plotly rendering
affects: [04-03, 04-04, future dashboard view modes]

tech-stack:
  added: [plotly]
  patterns: [Plotly heatmap overlay with layout.images, shared ClickHouse query helpers]

key-files:
  created: [dashboard/heatmap_plotly.py, dashboard/heatmap_filters.py]
  modified: [dashboard/app.py, dashboard/heatmap_queries.py, dashboard/requirements.txt]

key-decisions:
  - "Use Plotly go.Heatmap plus layout.images so the screenshot remains the rendering surface."
  - "Keep URL parsing and LIKE translation in a shared helper so the dashboard and query layer stay aligned."
  - "Fallback to the screenshot canvas even when no click data is available."

patterns-established:
  - "Pattern 1: Build Plotly figures in a reusable helper, then pass them directly to Streamlit."
  - "Pattern 2: Normalize page-scope filters once and reuse the same value across query paths."

duration: 12m
completed: 2026-04-16
---

# Phase 4 Plan 02: Screenshot Heatmap Overlay Summary

**Screenshot-backed click heatmaps rendered in Plotly over the cached Phase 3 page images, with shared URL filter handling and a pinned dashboard dependency.**

## Performance

- **Duration:** 12m
- **Started:** 2026-04-16T00:34:00+01:00
- **Completed:** 2026-04-16T00:45:54+01:00
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Added a reusable Plotly helper that layers click heatmap bins over the screenshot background.
- Refactored the Streamlit app to fetch aggregated click data and render it with `st.plotly_chart`.
- Added the shared URL filter helper and Plotly dependency pin so later plans can reuse the same contract.

## Task Commits

1. **Task 1: Create Plotly heatmap overlay builder** - `7e3f4bf`
2. **Task 2: Refactor the Streamlit app to render click heatmaps on screenshots** - `7e3f4bf`
3. **Task 3: Add Plotly to the dashboard dependencies** - `7e3f4bf`

**Plan metadata:** `7e3f4bf` (feat: add Plotly screenshot heatmap overlay)

## Files Created/Modified

- `dashboard/heatmap_plotly.py` - Builds the screenshot-backed Plotly figure.
- `dashboard/heatmap_filters.py` - Normalizes exact and wildcard URL filters.
- `dashboard/heatmap_queries.py` - Reuses the shared URL predicate logic.
- `dashboard/app.py` - Renders click overlays instead of static images.
- `dashboard/requirements.txt` - Adds Plotly to the dashboard runtime.

## Decisions Made

- Use the screenshot image as a Plotly layout layer rather than introducing any browser-side canvas code.
- Read screenshot dimensions from the cached file so overlay bins align with the stored pixels.
- Keep the dashboard query path on pre-binned ClickHouse aggregates only.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The system Python environment did not include the dashboard dependencies, so runtime validation was performed in an isolated `.venv-phase4` environment.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Shared overlay infrastructure is in place for URL scoping and additional heatmap modes.
- The dashboard shell is ready for mode switching and scroll/hover specialization in the remaining phase 4 plans.

---
*Phase: 04-heatmap-computation-and-core-dashboard*
*Completed: 2026-04-16*