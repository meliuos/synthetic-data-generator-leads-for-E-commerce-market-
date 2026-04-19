---
phase: 06-ecommerce-tracker-api
plan: 01
subsystem: tracker
tags: [javascript, tracker, ecommerce, consent, dedup, demo-spa]

# Dependency graph
requires:
  - phase: 05-01
    provides: "v1.1 click_events e-commerce columns + MV extraction of flat/properties fields"
  - phase: 05-02
    provides: "smoke-test-v11 shape contract for purchase/products payload"
provides:
  - "5 public tracker APIs: productView/addToCart/removeFromCart/purchase/search"
  - "purchase dedup by order_id using localStorage seen-set"
  - "demo-shop SPA with product cards, cart, checkout, and search submit"
affects:
  - "Phase 7 import (shared event vocabulary alignment)"
  - "Phase 8 dashboard (new e-commerce fields become queryable side-by-side with v1.0 events)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "E-commerce events emit top-level fields and mirrored properties payload"
    - "Consent gate is inherited by new APIs without introducing a second pipeline"
    - "Purchase dedup is client-side first layer; server dedup remains second layer"

key-files:
  created:
    - src/tracker/index.ecommerce.test.js
    - .planning/phases/06-ecommerce-tracker-api/06-01-SUMMARY.md
  modified:
    - src/tracker/index.js
    - src/tracker/constants.js
    - src/test-spa-page.html
    - package.json
    - README.md
    - .planning/ROADMAP.md
    - .planning/REQUIREMENTS.md
    - .planning/STATE.md

key-decisions:
  - "Node built-in test runner (`node --test`) used for zero-dependency tracker unit tests"
  - "`search` emits only on explicit submit in demo SPA (button click path)"
  - "Demo SPA flush payload now forwards full e-commerce properties, not just click/scroll fields"

patterns-established:
  - "Tracker public APIs validate minimally and return null when consent is missing or payload is invalid"
  - "`cart_id` rotates after purchase and order dedup persists in localStorage"

# Metrics
duration: 35min
completed: 2026-04-19
---

# Phase 6 Plan 1: E-commerce Tracker API Summary

Implemented the full Phase 6 tracker surface in one plan: 5 consent-gated e-commerce APIs, client-side purchase dedup, and a static demo-shop SPA that exercises every API with real UI controls.

## Accomplishments

- Added public APIs in `src/tracker/index.js`:
  - `productView({product_id, category, price, currency})`
  - `addToCart({product_id, quantity, price, category, currency})`
  - `removeFromCart({product_id, quantity})`
  - `purchase({order_id, total, items, currency})`
  - `search({query, results_count})`
- Added client-state behavior:
  - `cart_id` persisted/managed in localStorage and rotated after purchase
  - purchase dedup via localStorage seen-set keyed by `order_id`
- Added event vocabulary constants for all 5 e-commerce event types.
- Added tracker unit tests in `src/tracker/index.ecommerce.test.js` for:
  - event emission by API
  - purchase dedup
  - consent-gate inheritance
- Upgraded `src/test-spa-page.html` into a demo shop with:
  - 3 product cards
  - add/remove cart affordances
  - checkout purchase button
  - search bar + submit button
- Updated flush payload mapping so e-commerce fields reach RudderStack/ClickHouse in `properties`.

## Verification

- Ran `npm test`
- Result: 5 tests passed, 0 failed.

## Task Commits

1. `2c05c89` — tracker e-commerce APIs + dedup + tests
2. `3749f70` — demo shop SPA implementing all e-commerce affordances

## Deviations from Plan

- There was no pre-existing `06-01-PLAN.md` decomposition file; implementation proceeded directly from `.planning/ROADMAP.md` Phase 6 requirements and success criteria.

## Next Phase Readiness

- Phase 7 can proceed independently (Retailrocket import path is separate).
- Phase 8 can proceed independently (dashboard stats/click ranking over existing schema).
- For end-to-end verification against live infra, run `make up`, `make schema-v11`, then interact with `src/test-spa-page.html` and query `analytics.click_events`.
