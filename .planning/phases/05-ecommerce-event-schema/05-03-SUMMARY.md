---
phase: 05-ecommerce-event-schema
plan: 03
subsystem: documentation
tags: [docs, schema, clickhouse, ecommerce, ga4, migration, readme]

# Dependency graph
requires:
  - phase: 05-01
    provides: "002_ecommerce_schema.sql with all 6 SQL artifacts and make schema-v11 target"
provides:
  - "docs/schema-v1.1.md: concise developer reference for v1.1 additive schema extension"
  - "README.md pointer to schema-v1.1.md with make schema-v11 / make smoke-test-v11 mentions"
affects:
  - "Phase 6 (E-commerce Tracker API) — contributors find column vocabulary in docs/schema-v1.1.md"
  - "Phase 7 (Retailrocket Import) — documents sibling table schemas for reference"
  - "Phase 8 (Dashboard Panels) — documents GA4 alias view and purchase_items query patterns"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-milestone schema docs at docs/schema-v<MAJOR>.<MINOR>.md linked from root README"
    - "Substitution-rationale paragraph in schema docs for roadmap-to-implementation deviations"

key-files:
  created:
    - docs/schema-v1.1.md
  modified:
    - README.md

key-decisions:
  - "README edit used Strategy A: appended to existing Notes section — no new section needed since Notes already served as schema/tools reference list"
  - "doc links to scripts/smoke-test-v11.sh even though 05-02 may not yet be committed — link is correct; file will exist after wave 2 completes"
  - "Substitution-rationale paragraph included verbatim from plan template — mandatory and permanent documentation"

patterns-established:
  - "Schema docs live at docs/schema-v<MAJOR>.<MINOR>.md and are always linked from the root README"
  - "Substitution rationale (roadmap-vs-implementation) captured inline in the docs file, not only in planning artifacts"

# Metrics
duration: 3min
completed: 2026-04-18
---

# Phase 5 Plan 3: Schema Documentation Summary

**Developer reference for v1.1 additive e-commerce schema: 8-section docs/schema-v1.1.md documenting 8 new columns, sibling tables, GA4 alias view, and mandatory substitution-rationale paragraph citing RESEARCH.md §4/§7.3 with GitHub issue evidence**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-18T23:29:51Z
- **Completed:** 2026-04-18T23:32:36Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `docs/schema-v1.1.md` authored (147 lines, under 250-line limit)
- All 8 e-commerce columns documented with exact ClickHouse types and source shapes
- Both sibling tables documented with engines and query patterns
- Mandatory substitution-rationale paragraph included with RESEARCH.md §4/§7.3 citations and GitHub issues #98953, #24778, #46968
- GA4 alias table with all 4 renames (product_id→item_id, category→item_category, order_id→transaction_id, search_query→search_term)
- `make schema-v11` and `make smoke-test-v11` entry points documented
- `README.md` pointer added surgically (Strategy A — appended to Notes section)

## Task Commits

Each task was committed atomically:

1. **Task 1: Author docs/schema-v1.1.md** — `0b49c47` (docs)
2. **Task 2: Add README.md pointer** — `0a8299c` (docs)

## Files Created/Modified

- `docs/schema-v1.1.md` — 8-section developer reference for v1.1 schema extension (created)
- `README.md` — one bullet appended to Notes section linking to docs/schema-v1.1.md (modified)

## Eight Doc Sections Authored

| # | Section | Content |
|---|---------|---------|
| 1 | Title + intro | What the extension adds/excludes; SCHEMA-01..03 traceability |
| 2 | New columns table | 8 rows × 4 cols (Column, Type, Source shape, Example) |
| 3 | Sibling tables (NOT projections) | Mandatory substitution-rationale paragraph + purchase_items + orders descriptions |
| 4 | Main MV update | ALTER TABLE MODIFY QUERY explanation; NULL-backfill note |
| 5 | GA4 alias view | Zero-storage view + 4-alias mapping table |
| 6 | Running the migration | make schema-v11; idempotency notes; link to 002_ecommerce_schema.sql |
| 7 | Verifying the migration | make smoke-test-v11; 4-event test description; link to scripts/smoke-test-v11.sh |
| 8 | Related references | ROADMAP.md, REQUIREMENTS.md, 05-RESEARCH.md, 002_ecommerce_schema.sql |

## README Pointer Strategy

**Strategy A** (preferred) was used: appended one bullet to the existing `## Notes` section.

The Notes section already listed `001_events_schema.sql` and `scripts/smoke-test.sh` as schema/tool references — logically the correct place for a v1.1 schema pointer. No new section was needed; no existing sections were modified.

Added bullet:
```
- [Schema v1.1 (e-commerce events)](docs/schema-v1.1.md) — 8 new Nullable columns on
  `analytics.click_events`, per-line-item `purchase_items` table, server-side `orders` dedup,
  GA4 alias view. Apply via `make schema-v11`; verify via `make smoke-test-v11`.
```

## Substitution Rationale Confirmation

The mandatory substitution paragraph is present in Section 3 of the doc (lines 38-53), structured as a Markdown blockquote containing:

- Statement: roadmap described ARRAY JOIN projection and ReplacingMergeTree projection
- Bullet 1: Projections cannot use ARRAY JOIN — cites **RESEARCH.md §4** + **GitHub #98953**
- Bullet 2: Projections cannot declare different engine — cites **RESEARCH.md §7.3** + **GitHub #24778**, **#46968**
- Conclusion: secondary materialized views preserve the functional outcomes

All three GitHub issue references and both RESEARCH.md section references are present.

## Pattern Established

Per-milestone schema docs follow this convention: `docs/schema-v<MAJOR>.<MINOR>.md`, always
linked from the root README. Future milestones (v1.2 lead scoring, v2.0, etc.) should create
`docs/schema-v1.2.md`, `docs/schema-v2.0.md` etc. and append a pointer to README in the same
Notes section.

## Deviations from Plan

None — plan executed exactly as written.

## Next Phase Readiness

- Phase 6 (E-commerce Tracker API): `docs/schema-v1.1.md` provides the column vocabulary and JSON shape reference needed for tracker implementation
- Phase 7 (Retailrocket Import): sibling table schemas and query patterns documented
- Phase 8 (Dashboard Panels): GA4 alias view usage and purchase_items query patterns documented
- Note: `scripts/smoke-test-v11.sh` (05-02 output) will be linked correctly once 05-02 commits

---
*Phase: 05-ecommerce-event-schema*
*Completed: 2026-04-18*
