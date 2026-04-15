# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-15)

**Core value:** Show exactly where users click, scroll, and engage on any page as a live heatmap overlay backed by a scalable real-time event pipeline.
**Current focus:** Phase 4 in progress (Heatmap Computation and Core Dashboard)

## Current Position

Phase: 4 of 5 (Heatmap Computation and Core Dashboard)
Plan: 4 of 4 completed
Status: Complete
Last activity: 2026-04-16 - Completed 04-04-PLAN.md

Progress: [██████████] 100% (13 plans completed out of 13 planned)

## Accumulated Decisions

| Date | Plan | Decision | Why it matters |
| --- | --- | --- | --- |
| 2026-04-15 | 04-01 | Centralize heatmap SQL in `dashboard/heatmap_queries.py` | Keeps aggregation logic reusable and out of Streamlit UI code |
| 2026-04-15 | 04-01 | Support URL matching as exact value or wildcard (`*` -> `LIKE`) | Enables flexible page grouping without changing app SQL |
| 2026-04-15 | 04-01 | Expose only 5% binned dataframe results from helper APIs | Enforces Phase 4 contract: dashboard consumes aggregates, not raw rows |
| 2026-04-16 | 04-02 | Layer Plotly heatmaps over cached screenshots with `layout.images` | Keeps the screenshot as the rendering surface and aligns bins to the Phase 3 pixels |
| 2026-04-16 | 04-03 | Normalize URL scope once and reuse it for every mode | Prevents divergent wildcard parsing between the UI and ClickHouse query layer |
| 2026-04-16 | 04-04 | Render scroll as full-width bands and dispatch views by mode | Preserves one dashboard shell while giving scroll its correct visual semantics |

## Blockers / Concerns

- No product blockers from Phase 4 implementation.
- Environment note: host Python is externally managed (PEP 668), so dependency verification should continue via isolated virtual environments.

## Phase Status Snapshot

### Phase 1: Streaming and Storage Backbone
- Status: Complete
- Delivered: Redpanda + ClickHouse schema + smoke test pipeline

### Phase 2: JS Tracker and Event Ingestion Pipeline
- Status: Planned (not executed)
- Plans: 02-01, 02-02, 02-03, 02-04

### Phase 3: Screenshot Capture Service
- Status: Complete
- Delivered: Screenshot service and dashboard screenshot viewer

### Phase 4: Heatmap Computation and Core Dashboard
- Status: Complete (4/4 complete)
- Completed: 04-01 (ClickHouse binning query helpers), 04-02 (overlay rendering), 04-03 (URL and mode controls), 04-04 (scroll/hover views)
- Remaining: None

## Session Continuity

Last session: 2026-04-15 23:50:59 UTC
Stopped at: Completed 04-04-PLAN.md
Resume file: None
