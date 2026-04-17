# Lead Intelligence Platform — Event Tracking & Heatmap

## What This Is

A real-time user interaction tracking and lead intelligence platform for e-commerce sites. A JavaScript snippet is injected into an existing site to capture user events (heatmap signals — clicks, scrolls, mouse movement, page views — plus e-commerce intent signals — product views, cart actions, purchases, searches), stream them through RudderStack → Redpanda → ClickHouse, and surface them in an interactive Streamlit dashboard.

v1.0 shipped the heatmap core (click/scroll/hover overlays on page screenshots). v1.1 extends the platform toward lead generation by capturing e-commerce-specific events and seeding the store with an open-source dataset so downstream lead-scoring work has usable data without waiting for organic traffic.

This is Phase 1 of a larger lead intelligence system (per CdC: simulation, lead scoring, AI sales assistant come in later milestones).

## Core Value

Capture user behavior signals that identify purchase-intent leads for an e-commerce site — heatmap engagement plus e-commerce intent events — backed by a scalable real-time event pipeline.

## Current Milestone: v1.1 — E-commerce Events & Lead Dataset

**Goal:** Extend tracking beyond heatmap events to the 5 lead-informative e-commerce actions, import the Retailrocket open-source dataset into ClickHouse for a usable corpus, and complete the dashboard with the still-useful panels from the dropped Phase 5.

**Target features:**
- E-commerce event API in the tracker (`product_view`, `add_to_cart`, `remove_from_cart`, `purchase`, `search`)
- ClickHouse schema extension with typed e-commerce fields (`product_id`, `category`, `price`, `quantity`, `order_id`, `cart_value`, `search_query`)
- Retailrocket dataset import (events + item properties + category tree) into ClickHouse, idempotent and script-driven
- Demo shop affordances on the test SPA so the events can be exercised at defense
- Session stats panel + click ranking panel in the dashboard (rolled over from dropped Phase 5)

## Requirements

### Validated

<!-- v1.0 shipped 2026-04-16. Full list in REQUIREMENTS.md traceability. -->

- ✓ **PIPE-01..05** — Redpanda + ClickHouse pipeline (v1.0)
- ✓ **TRACK-01..07** — JS tracker with coordinate normalization, throttled mousemove, SPA route detection, consent gate (v1.0)
- ✓ **SHOT-01..02** — Playwright screenshot service at 1440px + 390px (v1.0)
- ✓ **HEAT-01..03** — Click, scroll, hover heatmap overlays on screenshots (v1.0)
- ✓ **DASH-01..02** — URL filter with wildcard support, heatmap type switcher (v1.0)

### Active

<!-- v1.1 scope — to be refined in REQUIREMENTS.md during this milestone. -->

- [ ] Tracker emits `product_view` events with `product_id`, `category`, `price`
- [ ] Tracker emits `add_to_cart` events with `product_id`, `quantity`, `price`
- [ ] Tracker emits `remove_from_cart` events with `product_id`
- [ ] Tracker emits `purchase` events with `order_id`, `total`, `items`
- [ ] Tracker emits `search` events with query string and result count
- [ ] ClickHouse schema stores typed e-commerce fields without breaking existing heatmap events
- [ ] Retailrocket dataset imported into ClickHouse via idempotent script
- [ ] Test SPA page exercises all 5 new event APIs end-to-end
- [ ] Dashboard session stats panel (sessions, avg scroll depth, bounce rate, events per page)
- [ ] Dashboard click ranking panel (top 10 element selectors per page)

### Out of Scope

- Lead scoring model (ML) — deferred to v1.2
- Lead identification UI / cart-abandoner dashboard — deferred to v1.2
- Live event feed panel — dropped from old Phase 5; doesn't serve lead intel
- Page flow Sankey diagram — dropped from old Phase 5; doesn't serve lead intel
- Synthetic data generation (CTGAN) — CdC Phase 3, later milestone
- LSTM/Transformer behavior modeling — CdC Phase 3, later milestone
- AI commercial assistant / LLM scripts — CdC Phase 5, later milestone
- Simulation engine (Mesa/SimPy) — CdC Phase 4, later milestone
- Session replay (OpenReplay) — separate concern, not heatmap/lead
- Mobile app — web tracker only
- Real-time heatmap streaming — batch refresh sufficient

## Context

- GL4 final year project (Ammar Mazen, Souilem Mootez, Chaabani Mayar)
- v1.0 heatmap core shipped 2026-04-16 — click/scroll/hover overlays on page screenshots work end-to-end
- The v1.0 data (click coordinates, scroll %, mouse trails) is rich for UX analysis but doesn't identify leads for e-commerce — a user clicking on a product page doesn't tell you if they're a potential buyer
- v1.1 closes that gap by adding e-commerce semantic events (what did the user *do* in the funnel) + a seeded dataset (Retailrocket, Kaggle, CC BY-NC-SA) so lead-scoring work in v1.2 has a real corpus to train against
- Academic project — open-source datasets only; no paid data sources
- Existing codebase already has the tracker pipeline, dashboard, screenshot service — v1.1 extends, it doesn't rebuild

## Constraints

- **Tech**: RudderStack mandatory — event SDK and pipeline (v1.0)
- **Tech**: Redpanda mandatory — streaming backbone (v1.0)
- **Tech**: ClickHouse for columnar event storage (v1.0); v1.1 schema extension must be additive (no table rebuild)
- **Tech**: Streamlit + Plotly for dashboard (v1.0)
- **Tech**: Retailrocket dataset locked as the corpus for v1.1 (Kaggle, CC BY-NC-SA) — drives event vocabulary and field shape
- **Legal**: RGPD compliant — cookie consent before any tracking (v1.0 already enforces this; e-commerce events inherit the gate)
- **Legal**: Data anonymization of PII (no raw IPs/emails stored) — Retailrocket is already anonymized; organic events use hashed IDs
- **Delivery**: GL4 academic project — must be demonstrable at defense

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| RudderStack for event collection | Mandated by CdC — open-source, structured, pipeline-compatible | ✓ Good (v1.0) |
| Redpanda for streaming | Kafka-API compatible, no ZooKeeper, simpler ops | ✓ Good (v1.0) |
| ClickHouse for storage | Columnar DB optimal for event analytics at scale | ✓ Good (v1.0) |
| Screenshot overlay (not canvas injection) | Simpler, no live page dependency | ✓ Good (v1.0) |
| Streamlit for dashboard | Rapid interactive UI | ✓ Good (v1.0) |
| Retailrocket dataset for lead corpus | Open source (CC BY-NC-SA); has view/cart/transaction events; ~2.7M events maps cleanly to our event_type column | — Pending (v1.1) |
| Additive schema extension (not rebuild) | ClickHouse `ALTER TABLE ADD COLUMN` is cheap; avoids v1.0 data loss | — Pending (v1.1) |
| Drop live feed + Sankey from dropped Phase 5 | Don't serve lead intel; session stats + click ranking kept for utility | — Pending (v1.1) |

---
*Last updated: 2026-04-18 after v1.1 milestone start (v1.0 archived; active scope replaced)*
