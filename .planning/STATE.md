# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-15)

**Core value:** Show exactly where users click, scroll, and engage on any page — as a live heatmap overlay backed by a scalable real-time event pipeline.
**Current focus:** Phase 1 — Streaming and Storage Backbone

## Current Position

Phase: 1 of 5 (Streaming and Storage Backbone)
Plan: 1 of 3 in current phase
Status: In progress
Last activity: 2026-04-15 — Completed 01-01-PLAN.md

Progress: [█░░░░░░░░░] 6%

## Performance Metrics

**Velocity:**
- Total plans completed: 1
- Average duration: 1 min
- Total execution time: 1 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 1 | 1 min | 1 min |

**Recent Trend:**
- Last 5 plans: 01-01 (1 min)
- Trend: stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: ORDER BY `(page_url, event_type, toDate(event_time))` locked in Phase 1 — cannot change after data flows
- Roadmap: Coordinate normalization (pageX/pageY as document percentages) locked in Phase 2 — wrong values are unrecoverable
- Roadmap: ClickHouse async_insert must be configured at Phase 1 schema design time to avoid insert hammering
- 01-01: Use file-based RudderStack backend config to keep local setup deterministic and control-plane independent
- 01-01: Include RudderStack Postgres service in compose so bootstrap has no hidden local prerequisites

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 2: RudderStack self-hosted Kafka destination config against Redpanda needs hands-on spike before full tracker build — confirmed in docs but exact destination fields unverified
- Phase 5: Mouse movement storage budget needs a load test before enabling (1 user × 30 min × 10 Hz = 18,000 events; project monthly ClickHouse growth)

## Session Continuity

Last session: 2026-04-14 23:29:51Z
Stopped at: Completed 01-01-PLAN.md
Resume file: None
