# Risks & Recommendations — Lead Intelligence Platform

**Date:** 2026-04-29
**Scope:** Current v1.1 state + forward risk for v1.2–v2.1 phases

---

## Risk Register

### RISK-02 — Retailrocket class imbalance will degrade ML model quality
**Likelihood:** High (known from dataset analysis)
**Impact:** Medium — the Retailrocket dataset has a ~0.82% conversion rate
(`transaction / total_events` ≈ 22,457 / 2,756,101). Training a naive binary classifier on
this distribution produces a model that predicts "no conversion" for every session and still
achieves 99.2% accuracy. AUC and Precision@K will expose this.
**Mitigation (Phase 11):**
- Use LightGBM with `scale_pos_weight = (non-converted sessions / converted sessions)` — built-in
  class imbalance handling.
- Alternatively, apply SMOTE oversampling on the minority class in the training split only
  (never on the test split).
- Primary metric: ROC-AUC (not accuracy). Secondary: Precision@10% (how good is the top decile?).
- Set a hard minimum AUC threshold of 0.70 before calling the model "usable" in Phase 12.

---

### RISK-03 — Retailrocket vocabulary gaps reduce ML feature coverage
**Likelihood:** Certain (documented in ROADMAP.md Phase 7 Notes)
**Impact:** Medium — Retailrocket has no `remove_from_cart` events and no `search` events.
These features will be NULL for all Retailrocket sessions in the `session_features` table,
while live tracker sessions will have them populated.
**Mitigation:**
- Do not impute zeros for NULL features — NULLs carry signal (the event didn't happen vs the
  event happened with value 0). LightGBM handles NULLs natively; do not fill.
- Document the gap in the model card (Phase 11 deliverable).
- When scoring live tracker sessions with the ML model, the richer feature set (search, remove)
  may produce a distribution shift — monitor AUC on live sessions separately from Retailrocket.

---

### RISK-04 — Redpanda version drift between research and compose (minor)
**Likelihood:** Already present
**Impact:** Low — `redpanda:v24.1.10` is used instead of recommended `v26.1.4`. The Kafka
API is stable and nothing in the current stack uses version-specific features. The risk is
latent: a bug fixed in v25/v26 could surface under load.
**Mitigation:** Bump the image tag to `v26.1.4` before the defense demo. Test with the full
smoke test suite. This is a one-line change with low regression risk.

---

### RISK-05 — Silent event loss with no observability layer
**Likelihood:** Medium (any live demo with real traffic)
**Impact:** Medium — if RudderStack drops a batch, the Kafka consumer lags, or a ClickHouse
MV query fails, the dashboard shows stale data with no alert. During a live defense demo this
is embarrassing.
**Mitigation:**
- Add Redpanda Console to the Compose stack (`redpandadata/console:v2.7.0`) — requires no
  code changes, shows consumer lag on a web UI at port 8085.
- Add a health-check query in the Streamlit sidebar: `SELECT max(event_time) FROM analytics.click_events` displayed as "Last event received: X minutes ago."
- These two changes together give real-time pipeline visibility at the demo.

---

### RISK-06 — Screenshot misalignment under dynamic content
**Likelihood:** Medium (demo shop SPA with dynamic cart state)
**Impact:** Low — if the demo SPA changes layout after a screenshot is cached (e.g., cart
banner appears after adding items), the heatmap overlay will be misaligned.
**Mitigation:**
- Keep the demo SPA layout static: do not show a cart overlay that shifts the page layout.
  Cart state should update in-place (not push content down).
- Document the screenshot staleness behavior in the README with the workaround ("Refresh
  Screenshot" button in the dashboard).

---

### RISK-07 — LLM API cost and latency in Phase 15/16
**Likelihood:** Low (academic use, low volume)
**Impact:** Low for demo; medium for any extended use
**Mitigation:**
- Use prompt caching on the system prompt (static per score tier) — the Anthropic SDK
  `cache_control: {"type": "ephemeral"}` header on the system message reduces cost by ~90%
  on repeated calls for the same tier.
- Log token usage to `analytics.ai_script_log` so cost is visible and bounded.
- For the defense demo: pre-generate 3 sample scripts (hot / warm / cold) and cache them as
  static examples. Only call the live API if the reviewer explicitly requests a new generation.

---

### RISK-08 — CTGAN training instability (Phase 13)
**Likelihood:** Medium — GANs are sensitive to hyperparameters and can mode-collapse or
produce unrealistic distributions.
**Impact:** Medium — if synthetic data is unrealistic, it won't augment the training set
usefully and may degrade ML model quality.
**Mitigation:**
- Evaluate synthetic data quality with Jensen-Shannon divergence (< 0.1 threshold per feature)
  before using it for ML augmentation.
- Use SDV's `CTGANSynthesizer` with the recommended defaults before tuning. The SDV library
  provides built-in quality report generation — use it.
- Checkpoint the model every 50 epochs. If quality plateaus, stop early rather than overfitting.

---

## Prioritized Recommendations

### Immediate (before defense)

1. **Ship Phase 7** — Retailrocket import is the only outstanding v1.1 task. Start with the
   Kaggle auth pre-flight, then run the download + import. Target: 1–2 days.

2. **Add Redpanda Console to docker-compose** — one service block, zero code changes, full
   pipeline visibility. Do this alongside Phase 7.

3. **Bump Redpanda to v26.1.4** — one-line change, run smoke tests after. Low risk.

4. **Add pipeline health indicator to Streamlit** — `SELECT max(event_time)` in the sidebar.
   < 30 minutes of work; eliminates the "is it even working?" question during a live demo.

### Before v1.2 starts

5. **Define `analytics.unified_events` view** — zero-storage UNION ALL across `click_events`
   and `retailrocket_raw.events`. This is Phase 9 task 1 and gates all subsequent scoring work.

6. **Review `session_features` SQL design with the team** — the feature columns lock in the
   ML model's input space. Getting agreement on the feature list before coding Phase 10 saves
   a rewrite later.

### Before v2.0 starts

7. **Validate ML model on live tracker data (not just Retailrocket)** — the distribution
   shift between synthetic Retailrocket and real live sessions is the biggest unknown in the
   system. Reserve a 2-week soak period after Phase 12 ships to collect live lead scores and
   manually validate top-scored candidates.

8. **Design the simulation event schema before Mesa coding starts (Phase 14)** — the simulator
   must emit events that match the exact tracker JSON shape (including `anonymous_user_id`,
   `session_id`, `event_type`, `properties`). Lock this in Phase 13 before Phase 14 begins.

---

## Non-Issues (Do Not Over-Engineer)

The following are **not risks** at this stage and should not be addressed:

- **Real-time heatmap streaming** — batch refresh (60s) is sufficient. WebSocket + streaming
  materialized view is weeks of work for negligible UX improvement in a demo context.
- **Multi-region / HA deployment** — single-node Docker Compose is the right scope for an
  academic project. Do not add Kubernetes or replica sets.
- **Raw event replay / event sourcing** — the Kafka Engine retains offsets but not historical
  messages. This is fine. Retroactive reprocessing is not a v1.2 requirement.
- **Full GDPR audit** — consent gate is implemented. A full legal audit is out of scope for
  a GL4 project.

---
*Written: 2026-04-29*
