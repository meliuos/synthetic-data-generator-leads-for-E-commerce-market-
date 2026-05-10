---
phase: 16
milestone: v2.1
status: COMPLETE
depends_on: [15]
---

# Phase 16 — AI Script Generation Dashboard Panel

Surface the LLM script generation capability directly in the Streamlit Leads page —
one button click per lead row generates a personalised sales outreach script using
the Phase 15 `build_script()` function (Ollama + Qwen2.5:7b backend).

## Plans

### 16-01: Generate Script button + output display + script history ✓
- [x] Updated `dashboard/pages/leads.py`:
  - Per-lead expander row below the ranked table (top 20 leads)
  - `st.button(f"Generate Script##{uid}")` — unique key per lead, no Streamlit collision
  - On click: `_call_build_script(uid)` inside `st.spinner("Generating sales script via Ollama…")`
  - Script stored in `st.session_state[f"script_{uid}"]` — persists across reruns
  - `st.text_area(label="Generated Script", value=script_text, height=200)` on success
  - Metadata caption from `analytics.ai_script_log`: model, prompt chars, response chars, timestamp
  - Error handling:
    - `_SENTINEL_NOT_FOUND` ("No behavioral data found") → `st.warning`
    - `_SENTINEL_TIMEOUT` ("timed out") → `st.error`
  - Script History panel: `analytics.ai_script_log` last 10 rows as `st.dataframe`
  - Empty history state: info message directing user to generate scripts
- [x] Added `httpx>=0.27.0` and `jinja2>=3.1.0` to `dashboard/requirements.txt`

## Architecture Notes

- `_call_build_script()` does a lazy import of `src.ai.build_script` so the dashboard
  runs even if Ollama deps are not installed (shows a friendly error string instead)
- Repo root is added to `sys.path` at module load so `src/ai` is importable from the
  Streamlit process regardless of working directory
- Cost column replaced with model/prompt/response char counts (Ollama = $0 per call)
- Tier emoji (🔥/🌡️/❄️) in expander label for quick visual scanning

## Smoke Test

Start the dashboard and navigate to the Leads page:
```
cd dashboard && streamlit run app.py
```
1. Table loads with rule + ML scores  ✓
2. "Generate Script" expander visible per lead row  ✓
3. Click button → spinner → script in text_area (requires Ollama running)  ✓
4. Script History panel renders (empty state if no scripts yet)  ✓
