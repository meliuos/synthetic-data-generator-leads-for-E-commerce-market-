# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-15)

**Core value:** Show exactly where users click, scroll, and engage on any page — as a live heatmap overlay backed by a scalable real-time event pipeline.
**Current focus:** Phase 1 — Streaming and Storage Backbone

## Current Position

Phase: 2 of 5 (JS Tracker and Event Ingestion Pipeline)
Plan: 0 of 4 in current phase
Status: Phase 1 complete
Last activity: 2026-04-15 — Completed 01-03-PLAN.md (Phase 1 done)

Progress: [██░░░░░░░░] 18%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: 8 min
- Total execution time: 24 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 3 | 24 min | 8 min |

**Recent Trend:**
- Last 5 plans: 01-01 (1 min), 01-02 (20 min), 01-03 (3 min)
- Trend: improving

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
- 01-02: ClickHouse async_insert must live under users profile config (users.d), not top-level config.d
- 01-02: Schema verification baseline includes sorting_key introspection via system.tables
- 01-03: Smoke test should publish via rpk topic produce, not REST proxy, for deterministic local behavior
- 01-03: Smoke test must create topic idempotently to avoid first-run false negatives

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 2: RudderStack self-hosted Kafka destination config against Redpanda needs hands-on spike before full tracker build — confirmed in docs but exact destination fields unverified
- Phase 5: Mouse movement storage budget needs a load test before enabling (1 user × 30 min × 10 Hz = 18,000 events; project monthly ClickHouse growth)

## Session Continuity

Last session: 2026-04-15 00:00:16Z
Stopped at: Completed 01-03-PLAN.md (Phase 1 complete)
Resume file: None
