# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-18)

**Core value:** Capture user behavior signals that identify purchase-intent leads for an e-commerce site — heatmap engagement plus e-commerce intent events — backed by a scalable real-time event pipeline.
**Current focus:** Milestone v1.1 — defining requirements and roadmap for e-commerce events and lead dataset.

## Current Position

Milestone: v1.1 — E-commerce Events & Lead Dataset
Phase: Not started (defining requirements)
Plan: —
Status: Defining v1.1 requirements
Last activity: 2026-04-18 — v1.0 archived, v1.1 started

Progress: v1.0 complete (13/13 plans shipped); v1.1 in init.

## Accumulated Decisions

Decisions from v1.0 — still load-bearing for v1.1:

| Date | Plan | Decision | Why it matters |
| --- | --- | --- | --- |
| 2026-04-15 | 04-01 | Centralize heatmap SQL in `dashboard/heatmap_queries.py` | v1.1 session stats + click ranking queries belong in this same module |
| 2026-04-15 | 04-01 | Support URL matching as exact value or wildcard (`*` -> `LIKE`) | v1.1 e-commerce event queries reuse this URL scoping helper |
| 2026-04-15 | 04-01 | Expose only binned/aggregated dataframes from query helpers | v1.1 panels must follow the same rule — never fetch raw rows into Streamlit |
| 2026-04-16 | 04-02 | Layer Plotly heatmaps over cached screenshots with `layout.images` | Pattern applies to any future overlay panel |
| 2026-04-16 | 04-03 | Normalize URL scope once and reuse it for every mode | v1.1 dashboard filters should consume the same normalized scope |
| 2026-04-16 | 04-04 | Render scroll as full-width bands, dispatch views by mode | Mode-dispatch pattern extends cleanly to new v1.1 panels |

## Blockers / Concerns

- No v1.0 blockers.
- Environment note: host Python is externally managed (PEP 668); dependency verification must continue via isolated venvs (v1.0 used `.venv-phase4`).
- v1.1 open decisions for roadmapper/plan-phase: Retailrocket table strategy (merge vs. parallel table); typed columns vs. JSON payload for e-commerce fields; demo shop scope for the test SPA.

## Milestone History

See [.planning/MILESTONES.md](./MILESTONES.md) for shipped milestones.

- **v1.0** — Heatmap Core (Complete, 2026-04-16) — Phases 1–4 shipped; Phase 5 dropped, useful parts rolled into v1.1.

## Session Continuity

Last session: 2026-04-18
Stopped at: v1.1 initialization in progress (requirements definition next)
Resume file: None
