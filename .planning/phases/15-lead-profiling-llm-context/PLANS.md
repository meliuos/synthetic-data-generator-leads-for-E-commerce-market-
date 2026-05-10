---
phase: 15
milestone: v2.1
status: COMPLETE
depends_on: [12]
---

# Phase 15 — Lead Profiling & LLM Context Builder

Build the context-assembly layer that translates a lead's behavioral signals into a
structured prompt payload for the LLM, and a logging layer that records every LLM call
with latency and token counts to ClickHouse.

> **Note:** Originally planned with Anthropic Claude. Refactored to use Ollama + Qwen2.5:7b
> for fully local, zero-cost, offline inference (see refactor applied post-implementation).

## Plans

### 15-01: Lead context assembly + prompt templates ✓
- [x] `src/ai/lead_profiler.py` — `fetch_lead_context(anonymous_user_id)` → structured dict
  - Joins `lead_scores_ml FINAL`, `lead_scores_rule_based`, `session_features`, `purchase_items`
  - PII constraint: anonymous_user_id only
  - Raises `LeadNotFoundError` on missing score
- [x] `src/ai/prompt_builder.py` — `build_prompt(lead_context)` → `(system_prompt, user_prompt)`
  - Per-tier Jinja2 templates in `src/ai/templates/` (hot.j2, warm.j2, cold.j2)
  - viewed_products truncated to 10 items max
  - Unknown tier falls back to cold
- [x] `tests/test_prompt_builder.py` — 11 tests, all passing

### 15-02: LLM client + ClickHouse logging ✓
- [x] `src/ai/llm_client.py` — Ollama HTTP API (`OLLAMA_HOST`, `LLM_MODEL=qwen2.5:7b`)
  - `generate_script(system_prompt, user_prompt)` → `ScriptResult`
  - `ScriptResult`: text, model, latency_ms, prompt_length, response_length
  - 30s timeout, raises `LLMTimeoutError`
  - Zero API cost, fully local
- [x] `infra/clickhouse/sql/008_ai_script_log.sql` — `analytics.ai_script_log` table (applied ✓)
- [x] `src/ai/__init__.py` — `build_script(anonymous_user_id)` orchestrator
  - Never raises; returns error string on missing lead, timeout, or inference error
  - Logs to `analytics.ai_script_log` after every successful generation
- [x] `requirements-ai.txt` — `httpx`, `clickhouse-connect`, `jinja2`
- [x] `scripts/test_llm.py` — health check script for Ollama connectivity
- [x] Makefile: `ai-setup`, `schema-ai`, `test-ai` targets

## Smoke Test
```
make test-ai  → 11/11 unit tests pass ✓
make schema-ai → analytics.ai_script_log created ✓
```

## Next Action
Start Ollama (`ollama serve`) and pull model (`ollama pull qwen2.5:7b`), then run:
```
make test-ai
```
Live integration test (requires Ollama running):
```
.venv-ai/Scripts/python scripts/test_llm.py
```
