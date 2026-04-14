# Feature Research

**Domain:** Web analytics / heatmap visualization — real-time event tracking platform for e-commerce
**Researched:** 2026-04-14
**Confidence:** HIGH (core feature categories verified against Microsoft Clarity official docs, PostHog official docs, and cross-referenced across multiple products)

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Click heatmap overlay on page screenshot | Core value proposition; every competitor has it (Hotjar, Clarity, PostHog, Crazy Egg) | MEDIUM | Requires screenshot capture + coordinate mapping; overlay rendered on top of page image |
| Scroll depth / scroll map | Users need to know where the fold is and how far people scroll; Clarity, Hotjar, PostHog all support it | MEDIUM | Track pageview + pageleave events, compute % reached per scroll band |
| Rage click detection | Standard in all tools (Clarity, PostHog, Hotjar); signals UX frustration without session replay | LOW | 3+ clicks in same area within ~1 second; needs coordinate clustering |
| Dead click detection | Standard in Clarity and PostHog; clicks on non-interactive elements = invisible UX bugs | LOW | Click event with no subsequent navigation or DOM change; needs element-type context |
| Page view tracking | Baseline event; required for all aggregation denominators | LOW | Standard pageview event from JS snippet |
| Filter by date range | Every analytics tool supports this; users expect "last 7 days", "last 30 days", custom range | LOW | Apply time window to all queries against ClickHouse |
| Filter by device type | Desktop vs mobile behavior differs significantly; Clarity, Hotjar, PostHog all support device segmentation | LOW | Parse user-agent from event payload |
| Filter by URL / page | Users want to view heatmap for a specific product page, checkout page, etc. | LOW | URL exact match + wildcard/regex support expected |
| Total page views count per view | Denominator for all heatmap intensity; every tool shows it | LOW | Simple COUNT from ClickHouse |
| Heatmap color scale / intensity legend | Visual reference for what hot vs cold means; present in all tools | LOW | UI only; label the color gradient |
| Mouse movement heatmap | PostHog includes it; Hotjar includes move heatmaps; users expect to see attention areas | HIGH | High data volume; coordinate sampling needed to avoid storage explosion |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Real-time heatmap updates (streaming) | Most tools batch/delay by hours; showing live event accumulation is a genuine differentiator given Kafka pipeline already in place | HIGH | Requires Kafka consumer feeding ClickHouse materialized view; streaming aggregation challenging at scale |
| Multiple heatmap types switchable on same page screenshot | Clarity supports click / scroll / area / attention / conversion maps; switching without page reload improves workflow | MEDIUM | Reuse same screenshot; swap aggregation query and re-render overlay |
| Heatmap comparison mode (A/B or date-over-date) | Crazy Egg, Clarity both offer this; lets e-commerce team compare before/after a page redesign | HIGH | Side-by-side or diff overlay; needs two independent query results |
| Ecommerce conversion map (clicks that led to purchase) | Clarity has "Conversion maps" specifically for e-commerce; directly answers "which clicks drive revenue" | HIGH | Requires purchase event linkage; needs session/user ID to join click + order events |
| Rage click hotspot auto-alerting | Proactively surface pages with high rage-click concentrations; moves from reactive to proactive | MEDIUM | Threshold-based query scheduled in ClickHouse; push to dashboard or email |
| Segment by traffic source / referrer | Lets e-commerce team see if paid vs organic traffic behaves differently | MEDIUM | Parse UTM params and referrer from event payload; add as dimension in ClickHouse |
| First click vs last click views | Clarity differentiates these; useful for understanding entry behavior vs exit intent on product pages | LOW | Tag event sequence position in session context; needs session boundary logic |
| Page-level summary panel | Show rage click %, dead click %, avg scroll depth, total sessions at a glance before opening heatmap | LOW | Aggregation query over session metrics; pure UI enhancement |
| URL wildcard grouping (e.g., /product/* aggregated) | Grouping dynamic product pages into one heatmap view is essential for e-commerce with many SKUs | MEDIUM | Regex/glob URL matching in query layer; combine multiple URL patterns |
| Export heatmap as PNG / CSV | Clarity supports download; useful for stakeholder reports and presentations | LOW | Canvas-to-image for PNG; CSV export of underlying click coordinates |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems. Do not build these in Phase 1.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Full session recording / replay | Feels like natural companion to heatmaps; Hotjar, FullStory, PostHog all have it | Massive storage cost (video-equivalent data per session), GDPR complexity (records PII in form fields), requires separate infrastructure (separate player, masking logic); weeks of added scope | Stick to heatmaps + event aggregates for Phase 1; session replay is a future milestone |
| Funnel analysis / conversion funnel builder | Ecommerce teams love funnel views; easy to demo | Requires defining ordered event sequences, session stitching across page boundaries, significant query complexity — not a heatmap feature | Use ClickHouse funnels query type in a later phase once event schema is stable |
| Form analytics (field-level drop-off) | Useful for checkout optimization | Requires field-level event instrumentation beyond clicks; needs careful PII handling for form field values | Defer to Phase 2 when JS snippet can be extended; use dead click map on form elements as proxy |
| User-level session stitching (identify same user across visits) | Personalization and cohort analysis | Requires identity resolution (login events + anonymous ID merge), complex Kafka deduplication logic; scope explosion | Use anonymous session IDs per visit for Phase 1; identity resolution is a future milestone |
| Real-time alerting via email / Slack | Stakeholders want push notifications on anomalies | Notification infrastructure, alert rule builder, subscription management — none of these are core to heatmap visualization | Manual dashboard refresh is sufficient for Phase 1; alerting is a v1.x addition |
| Mobile app heatmaps (iOS / Android) | Clarity and PostHog support mobile; stakeholders may ask | Requires a mobile SDK, entirely different coordinate space (dp/px), different screenshot mechanism; doubles the project scope | Restrict Phase 1 to web only; mobile can be a separate milestone |
| AI/LLM session summarization | Clarity Copilot, Hotjar AI summaries are prominent; stakeholders will notice | Requires LLM integration, prompt engineering, cost management; adds no core data infrastructure value in Phase 1 | AI features are Phase 4+ in the broader lead intelligence platform roadmap |
| A/B test integration | Teams want to see heatmaps per variant | Requires feature flag infrastructure, variant assignment tracking, experiment event schema — not a heatmap concern | Phase 1 heatmap comparison mode (date-over-date) covers the most common use case without experiment infrastructure |

---

## Feature Dependencies

```
[Page View Event] ──required by──> [Scroll Map]
[Page View Event] ──required by──> [Click Heatmap]
[Click Event + XY coords] ──required by──> [Click Heatmap]
[Click Event + XY coords] ──required by──> [Rage Click Detection]
[Click Event + XY coords] ──required by──> [Dead Click Detection]
[Scroll Depth Event] ──required by──> [Scroll Map]
[Mouse Move Event] ──required by──> [Mouse Movement Heatmap]

[Page Screenshot] ──required by──> [Heatmap Overlay Visualization]
[Click Heatmap] ──requires──> [Page Screenshot]

[Session Boundary Logic] ──required by──> [First Click / Last Click views]
[Session Boundary Logic] ──required by──> [Rage Click Detection] (3 clicks within 1 second in same session)

[URL Filter] ──enhances──> [Click Heatmap] (single page vs. group of pages)
[Date Range Filter] ──enhances──> [All Heatmaps]
[Device Type Filter] ──enhances──> [All Heatmaps]

[Purchase Event Schema] ──required by──> [Conversion Map] (clicks → revenue)
[Purchase Event Schema] ──conflicts──> [Phase 1 scope] (requires ecommerce integration beyond JS snippet)

[Mouse Movement Heatmap] ──conflicts──> [Storage Budget] (very high event volume)
[Session Recording] ──conflicts──> [Phase 1 scope] (different infrastructure)
```

### Dependency Notes

- **Page screenshot is gating for all heatmap visualization:** Without a reliable screenshot of the page, coordinate overlays are meaningless. The screenshot must match the page at the time of data collection (handle DOM changes, A/B tests, dynamic content).
- **Session boundary logic gates rage click and first/last click:** A session timeout (typically 30 minutes of inactivity) must be defined and applied consistently from the Kafka consumer layer before session-dependent features work correctly.
- **Mouse movement heatmap requires data volume decision first:** At 1 mousemove event per 100ms, a 3-minute session generates 1,800 events per user. Sampling (e.g., capture every 10th event) must be decided before implementing; don't implement raw.
- **Conversion maps require a purchase event:** Cannot build in Phase 1 without confirmed ecommerce event schema integration. Do not add placeholder infrastructure — wait until the schema is defined.

---

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to validate the concept and deliver value to the e-commerce analytics team.

- [ ] Click heatmap overlay on page screenshot — core deliverable; the thing that proves the platform works
- [ ] Scroll depth map — second most-expected feature; shows fold position and content engagement
- [ ] Rage click detection + visualization on heatmap — high-value signal for UX problems; low implementation cost
- [ ] Page view count + sessions count per URL — required denominator for all heatmap intensities
- [ ] Filter by date range — without this users cannot interpret trends over time
- [ ] Filter by device type (desktop / mobile / tablet) — behavior differs significantly; required for e-commerce
- [ ] Filter by URL / page — must be able to isolate product page vs checkout vs homepage
- [ ] URL wildcard grouping (/product/*) — without this, e-commerce product pages are ungroupable and heatmaps are sparse

### Add After Validation (v1.x)

Features to add once core heatmap pipeline is confirmed working.

- [ ] Dead click detection and overlay — trigger: core rage click + click heatmap confirmed accurate
- [ ] Mouse movement heatmap — trigger: storage capacity confirmed; implement with sampling
- [ ] Segment by traffic source / referrer — trigger: e-commerce team confirms UTM tracking is in place
- [ ] Multiple heatmap types switchable (click / scroll / movement) — trigger: all three base heatmaps implemented
- [ ] Page-level summary panel (rage click %, avg scroll depth) — trigger: base metrics stable
- [ ] Heatmap PNG / CSV export — trigger: team requests for stakeholder reporting

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] Real-time streaming heatmap — defer: requires materialized view tuning and WebSocket infrastructure; high complexity
- [ ] Heatmap comparison mode (date-over-date) — defer: requires stable screenshot versioning; Phase 2
- [ ] Conversion map (click → purchase) — defer: requires ecommerce purchase event integration; Phase 2+
- [ ] Ecommerce-specific rage click alerting — defer: notification infrastructure needed; Phase 2+
- [ ] Session recording / replay — defer: separate infrastructure decision; later milestone
- [ ] Funnel analysis — defer: requires stable event schema + session stitching; later milestone
- [ ] AI/LLM heatmap summaries — defer: Phase 4+ per platform roadmap

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Click heatmap overlay | HIGH | MEDIUM | P1 |
| Scroll depth map | HIGH | MEDIUM | P1 |
| Rage click detection | HIGH | LOW | P1 |
| Filter by date range | HIGH | LOW | P1 |
| Filter by URL / page | HIGH | LOW | P1 |
| Filter by device type | HIGH | LOW | P1 |
| URL wildcard grouping | HIGH | MEDIUM | P1 |
| Page view / session count display | HIGH | LOW | P1 |
| Dead click detection | MEDIUM | LOW | P2 |
| Mouse movement heatmap | MEDIUM | HIGH | P2 |
| Segment by traffic source | MEDIUM | MEDIUM | P2 |
| Multiple heatmap type switching | MEDIUM | LOW | P2 |
| Page-level summary panel | MEDIUM | LOW | P2 |
| PNG / CSV export | LOW | LOW | P2 |
| Heatmap comparison mode | HIGH | HIGH | P3 |
| Real-time streaming heatmap | MEDIUM | HIGH | P3 |
| Conversion map | HIGH | HIGH | P3 |
| Session recording | HIGH | HIGH | P3 (later milestone) |
| Funnel analysis | HIGH | HIGH | P3 (later milestone) |
| AI/LLM summaries | LOW | HIGH | P3 (Phase 4+) |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

---

## Competitor Feature Analysis

| Feature | Microsoft Clarity | PostHog | Hotjar | Our Approach (Phase 1) |
|---------|-------------------|---------|--------|------------------------|
| Click heatmap | Yes (element-based, not pixel) | Yes (element + position) | Yes | Yes — pixel coordinate overlay on screenshot |
| Scroll map | Yes | Yes | Yes | Yes |
| Mouse movement heatmap | No (Clarity dropped it) | Yes | Yes (move heatmap) | P2 — implement with sampling |
| Rage click detection | Yes — automatic flagging | Yes | Yes | Yes — P1 |
| Dead click detection | Yes | Yes | No | Yes — P1 |
| Error click detection | Yes (JS errors linked to clicks) | No | No | No — out of scope |
| First / last click | Yes | No | No | P2 |
| Area map | Yes | No | No | No — low value for Phase 1 |
| Attention map (dwell time) | Yes | No | No | No — requires time-on-element tracking |
| Conversion map | Yes (e-commerce specific) | No | No | P3 — requires purchase event |
| Filter by device | Yes | Yes | Yes | Yes — P1 |
| Filter by date range | Yes | Yes | Yes | Yes — P1 |
| Filter by URL / wildcard | Yes | Yes | Yes | Yes — P1 |
| Segment by traffic source | Yes | Yes | Yes | P2 |
| Heatmap comparison | Yes | No | Yes (Crazy Egg) | P3 |
| Session replay | Yes | Yes | Yes | Explicitly excluded — Phase 1 |
| Funnel analysis | No | Yes | No | Explicitly excluded — Phase 1 |
| AI summaries | Yes (Copilot) | No | Yes | Explicitly excluded — Phase 4+ |
| Export PNG/CSV | Yes | No | Yes | P2 |
| Real-time updates | No (batch) | No (near-real-time) | No (batch) | P3 — unique given Kafka pipeline |

---

## Sources

- Microsoft Clarity official docs — Click maps (updated 2025-12-05): https://learn.microsoft.com/en-us/clarity/heatmaps/click-maps
- Microsoft Clarity official docs — Heatmaps overview (updated 2025-12-05): https://learn.microsoft.com/en-us/clarity/heatmaps/heatmaps-overview
- PostHog official docs — Heatmaps: https://posthog.com/docs/toolbar/heatmaps
- PostHog blog — PostHog vs Hotjar: https://posthog.com/blog/posthog-vs-hotjar
- WebSearch: Hotjar vs Clarity vs FullStory comparison 2026: https://www.luniq.io/en/resources/blog/hotjar-vs-clarity-vs-fullstory-best-heatmaps-for-b2b-firms-in-2026
- WebSearch: Top heatmap tools 2026: https://uxcam.com/blog/best-heatmap-analysis-tool/
- WebSearch: Ecommerce web analytics tools compared: https://www.heatmap.com/blog/best-web-analytics-tools-ecommerce
- WebSearch: Heatmap analysis guide 2025: https://www.heatmap.com/blog/heatmap-analysis

---

*Feature research for: real-time event tracking and heatmap visualization system*
*Researched: 2026-04-14*
