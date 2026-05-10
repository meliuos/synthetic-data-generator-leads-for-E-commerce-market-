---
phase: 14
milestone: v2.0
status: COMPLETE
depends_on: [13]
---

# Phase 14 — Simulation Engine (Mesa)

Build an agent-based e-commerce traffic simulator that generates realistic event
streams (not just session aggregates) by replaying CTGAN-sampled behavioral profiles
through the live Redpanda pipeline — enabling "what-if" scenario testing for lead
acquisition strategies.

## Plans

### 14-01: Agent definitions ✓
- [x] Created `src/simulation/agents.py` (Mesa 3.x API — `Agent(model, ...)`, no unique_id):
  - `BrowserAgent` — page_view, product_view, scroll; no cart/purchase
  - `BuyerAgent` — conversion_probability from ml_lead_score; full funnel
  - `AbandonerAgent` — adds to cart exactly once, then exits
  - All agents: `session_id = f"sim_{uuid4().hex[:8]}"`, dwell time from log-normal
- [x] Added `requirements-sim.txt`: `mesa>=2.3`, `numpy`, `kafka-python`, `clickhouse-connect`

### 14-02: Mesa environment + Redpanda emission bridge ✓
- [x] Created `src/simulation/ecommerce_env.py` (`mesa.Model` subclass, Mesa 3.x):
  - `__init__(n_agents, agent_mix, duration_minutes, seed, dry_run)`
  - `step()` — `self.agents.shuffle_do("step")` (Mesa 3.x random activation)
  - `run()` — loops steps, flushes emitter, returns summary dict
  - Samples profiles from `analytics.synthetic_sessions` via ClickHouse; falls back to defaults
- [x] Created `src/simulation/event_emitter.py`:
  - Kafka producer (kafka-python) to Redpanda topic `rudder_events`
  - Buffers 100 events or 1s before flush
  - `dry_run=True` counts events without sending
  - `"simulated": True` property on every event for downstream filtering
- [x] Created `scripts/run_simulation.py`:
  - CLI: `--n-agents`, `--duration-minutes`, `--seed`, `--agent-mix`, `--dry-run`
  - Prints JSON summary: `{total_events, n_agents, simulated_minutes, conversion_rate, dry_run}`

### 14-03: Makefile targets + smoke test ✓
- [x] Added to `Makefile`: `sim-setup`, `simulate`, `smoke-test-sim`
- [x] Variables: `SIM_VENV`, `N_AGENTS=1000`, `DURATION=60`, `SEED=42`, `AGENT_MIX`
- [x] OS detection for `SIM_PYTHON` (Windows Scripts/ vs Unix bin/)
- [x] `make smoke-test-sim` passes: 100 agents, 10 min, dry-run → 666 events, exit 0
- [x] Updated `ctgan-train` timeout to 10800s (3h) in Makefile

## Smoke Test Result

```
make smoke-test-sim
→ total_events: 666, conversion_rate: 0.6765, dry_run: true  ✓
```

## Next Action

After Phase 13 training completes (`make generate-synthetic`), run a live simulation:
```
make simulate N_AGENTS=500 DURATION=30
```
Then verify `sim_*` session_ids appear in `analytics.click_events`.

## Implementation Notes

- Mesa 3.x removed `mesa.time.RandomActivation` — use `self.agents.shuffle_do("step")` instead
- `agents_by_type[BuyerAgent]` gives the Mesa 3.x typed agent view
- Redpanda topic matches the RudderStack destination topic (`rudder_events`) so simulated events
  flow through the same ClickHouse Materialized View as real browser traffic
- `"simulated": True` is stored in `event_payload` (JSON string column) and can be filtered with
  `JSONExtractBool(event_payload, 'simulated') = 1` in ClickHouse
