---
phase: 12
plan: 1
status: COMPLETE
shipped: 2026-04-29
---

# Phase 12 Plan 01 — Summary

## What shipped

| Artifact | Description |
|---|---|
| `dashboard/heatmap_queries.py` | `build_lead_candidates_query()` + `fetch_lead_candidates()` added. JOINs `lead_scores_rule_based`, `session_features`, and `lead_scores_ml FINAL` (LEFT JOIN). Sorted by `ifNull(ml_lead_score, rule_score/100)` DESC. Parameterized, capped at 5000 rows. |
| `dashboard/pages/leads.py` | Streamlit multi-page "Leads" page. Sidebar filters (tier, source, limit), 4-metric summary row (hot/warm/cold counts + ML-scored count), ranked table with `column_config`, `rules_fired` column, `cart_abandoned` Yes/No, formatted duration, ML-absent warning banner, CSV download button, empty state with `make score-sessions` instruction. |

## Key decisions

| Decision | Reason |
|---|---|
| LEFT JOIN on `lead_scores_ml` | ML table may be empty before training; the page must remain fully functional using rule scores alone |
| `ifNull(ml_lead_score, rule_score/100)` for sort order | Keeps ranking consistent whether ML scores exist or not; both are normalised to [0, 1] before comparison |
| Warning banner (not error) for missing ML scores | Missing ML scores are an expected operational state, not a bug — the page degrades gracefully |
| `rules_fired` as a derived string column | Interprets the six `rule_*` UInt8 flags into a human-readable label without requiring the dashboard to know the rule names at render time |
| `@st.cache_resource` for ClickHouse client | Mirrors the existing app.py pattern; avoids reconnecting on every Streamlit rerun |
| SQL only in `heatmap_queries.py`, not in the page | Preserves the established layering constraint from Phase 4 — UI layer never writes SQL |

## v1.2 status after this plan

All four v1.2 phases are now complete:

| Phase | Name | Status |
|---|---|---|
| 9 | Lead Scoring Data Foundation | COMPLETE |
| 10 | Rule-Based Lead Scoring Engine | COMPLETE |
| 11 | ML Lead Scoring Model | COMPLETE |
| 12 | Lead Identification Dashboard | COMPLETE |

v1.2 is done. Next milestone: v2.0 (CTGAN Behavioral Simulator — Phase 13).
