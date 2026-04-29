---
phase: 10
plan: 1
status: COMPLETE
shipped: 2026-04-29
---

# Phase 10 Plan 01 — Summary

## What shipped

| Artifact | Description |
|---|---|
| `src/scoring/rules.py` | Table-driven rule engine. `SessionFeatures` and `LeadScore` frozen dataclasses, six-rule `_RULES` list, `score_session()` / `score_sessions()`. No external deps. |
| `src/scoring/__init__.py` | Package re-exports (`TIER_HOT_MIN`, `TIER_WARM_MIN`, `LeadScore`, `SessionFeatures`, `score_session`, `score_sessions`). |
| `tests/test_scoring_rules.py` | 40+ test cases across nine test classes: individual rule fire/no-fire, scroll NULL semantics, bouncer strict conditions, score combinations, clamping, tier boundaries, Retailrocket source invariant, batch API, `from_dict`. |
| `infra/clickhouse/sql/005_phase10_lead_scoring.sql` | `analytics.lead_scores_rule_based` — read-time VIEW over `analytics.session_features` using WITH alias chaining for rule flags → raw_score → clamped lead_score → score_tier. Exposes six `rule_*` flag columns for Phase 12 interpretability. |
| `scripts/smoke_phase10.sql` | Six validation queries: tier distribution by source, top-10 ranked leads, hot lead existence, [0,100] boundary check, Retailrocket bouncer-never-fires assertion, rule contribution totals. |
| `Makefile` | `schema-phase10` and `smoke-test-phase10` targets. |

## Key decisions

| Decision | Reason |
|---|---|
| Rules are data `(name, delta, predicate)` not code | Adding/retuning a rule requires only an edit to `_RULES`; tests re-run automatically; ClickHouse view stays structurally consistent |
| `rule_contributions` omits non-fired rules | Phase 12 dashboard reads the dict to show "what drove this score" — absent key means rule didn't fire, which is cleaner than `{rule: 0}` noise |
| ClickHouse `ifNull(max_scroll_pct, 0.0)` for scroll_engagement | Preserves NULL-doesn't-fire semantic without a verbose `AND max_scroll_pct IS NOT NULL` guard; 0.0 is always below the 70.0 threshold |
| Retailrocket bouncer fires never (page_views=0, not 1) | No special-casing needed; the predicate `page_views = 1` is naturally false for all Retailrocket rows — verified by a dedicated smoke assertion |
| Tier constants exported at module level | Phase 12 Streamlit code and any future ML calibration can import `TIER_HOT_MIN` / `TIER_WARM_MIN` without re-hardcoding the thresholds |
| Maximum achievable score = 85 (not 100) | Rule deltas sum to 85; ceiling clamp exists for future rule additions without breaking the API contract |

## Score table

| Rules fired | Raw score | Clamped | Tier |
|---|---|---|---|
| All five positive | 85 | 85 | hot |
| add_to_cart + purchase + depth + search + scroll | 85 | 85 | hot |
| add_to_cart only | 30 | 30 | warm |
| purchase only | 20 | 20 | cold |
| bouncer only | -10 | 0 | cold |
| None | 0 | 0 | cold |
