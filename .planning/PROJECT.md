# Lead Intelligence Platform — Event Tracking & Heatmap

## What This Is

A real-time user interaction tracking and heatmap platform for e-commerce sites. A JavaScript snippet is injected into an existing site to capture user events (clicks, scrolls, mouse movement, page views, rage clicks), stream them through Rudderstack → Kafka → ClickHouse, and visualize them as heatmap overlays on page screenshots in an interactive dashboard.

This is Phase 1 of a larger lead intelligence system (per CdC: synthetic data, simulation, lead scoring, AI sales assistant come later).

## Core Value

Show exactly where users click, scroll, and engage on any page — as a live heatmap overlay backed by a scalable real-time event pipeline.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] JS tracking snippet embeds into any existing site
- [ ] Captures click events with (x, y) coordinates relative to page
- [ ] Captures scroll depth per page per session
- [ ] Captures mouse movement/hover zones
- [ ] Detects and flags rage clicks (3+ rapid clicks in same area)
- [ ] Events stream via Rudderstack → Kafka pipeline
- [ ] Events stored in ClickHouse
- [ ] Dashboard renders click heatmap as color overlay on page screenshot
- [ ] Dashboard renders scroll depth heatmap
- [ ] Dashboard renders hover/movement heatmap
- [ ] Dashboard shows rage click zones
- [ ] Page selector: choose which URL/page to visualize
- [ ] Cookie consent / RGPD-compliant event capture

### Out of Scope

- Synthetic data generation (CTGAN) — CdC Phase 3, not Phase 1
- LSTM/Transformer behavior modeling — CdC Phase 3
- Lead scoring model — CdC Phase 5
- AI commercial assistant / LLM scripts — CdC Phase 5
- Simulation engine (Mesa/SimPy) — CdC Phase 4
- Session replay (OpenReplay) — separate concern, not heatmap
- Real-time dashboard updates — batch refresh sufficient for v1
- Mobile app — web tracker only

## Context

- GL4 final year project (Ammar Mazen, Souilem Mootez, Chaabani Mayar)
- Larger CdC has 6 phases — this project initializes Phase 1 only
- Existing site to track (not building a demo shop)
- Heatmap displayed as overlay on captured page screenshot (not canvas injection)
- ClickHouse preferred for storage; open to faster alternative if justified

## Constraints

- **Tech**: Rudderstack mandatory — event SDK and pipeline
- **Tech**: Kafka (or Redpanda) mandatory — streaming backbone
- **Tech**: ClickHouse preferred for columnar event storage
- **Legal**: RGPD compliant — cookie consent before any tracking
- **Legal**: Data anonymization of PII (no raw IPs/emails stored)
- **Delivery**: GL4 academic project — must be demonstrable

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Rudderstack for event collection | Mandated by CdC — open-source, structured, pipeline-compatible | — Pending |
| Kafka/Redpanda for streaming | Mandated by CdC — scalable, distributed event bus | — Pending |
| ClickHouse for storage | CdC default — columnar DB optimal for event analytics at scale | — Pending |
| Screenshot overlay (not canvas injection) | User preference — simpler to implement, no live page dependency | — Pending |
| Streamlit for dashboard | CdC recommendation — rapid interactive UI | — Pending |

---
*Last updated: 2026-04-15 after initialization*
