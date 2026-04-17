# E-commerce Event Taxonomy Research

**Milestone:** v1.1 — Add 5 e-commerce intent events to the existing JS tracker
**Scope:** Event name + property shape only (storage schema lives in the Phase 5 plan)
**Researched:** 2026-04-18
**Overall confidence:** HIGH for Segment/Fueled/GA4 properties, MEDIUM for RudderStack-specific naming (RudderStack's ecommerce docs largely mirror Segment v2 but the canonical Ordering/Browsing pages 404'd during research — cross-verified via community tracking-plan examples and RudderStack SDK documentation)

---

## Canonical Specs Surveyed

| Spec | Status | Naming convention | Array key for order items |
|------|--------|-------------------|---------------------------|
| **Segment Ecommerce Spec V2** | HIGH — reference spec; most tools implement its event names and property set verbatim | `snake_case` | `products` |
| **RudderStack Ecommerce Events Spec** | MEDIUM — explicitly modeled on Segment V2 (same event names `Product Viewed`, `Product Added`, `Product Removed`, `Order Completed`, `Products Searched`) | `snake_case` | `products` |
| **GA4 Recommended Ecommerce Events** | HIGH — diverges in naming: `view_item`, `add_to_cart`, `remove_from_cart`, `purchase`, `search` | `snake_case` but renamed fields (`item_id`, `item_name`, `transaction_id`, `search_term`) | `items` |
| **Retailrocket dataset** | HIGH — only 3 event types (`view`, `addtocart`, `transaction`), 5 columns (`timestamp`, `visitorid`, `event`, `itemid`, `transactionid`) — extremely minimal | lowercase, no underscores | (implicit — transactionid ties rows) |

**Decision rule for this project:** Follow **RudderStack/Segment V2 naming** for event names (because the tracker already uses the RudderStack SDK and the ClickHouse sink flattens RudderStack's `properties` JSON). Add a **GA4-compatible alias layer** in the ClickHouse materialized view so downstream tools that expect GA4 shape (`items[]` instead of `products[]`) can consume the same rows.

---

## Event Property Reference

The columns **Type**, **Required**, **Spec source**, and **Lead-scoring role** are prescriptive for v1.1. "Required" here means "required by the canonical spec AND used by v1.2 lead scoring" — the tracker should refuse to emit an event missing these.

### product_view

**Canonical event name emitted to RudderStack:** `Product Viewed`
**GA4 equivalent:** `view_item`
**Retailrocket equivalent:** `view`
**Fires:** on Product Detail Page (PDP) load, after SPA route settles

| Property | Type | Required | Spec source | Lead-scoring role |
|----------|------|----------|-------------|-------------------|
| `product_id` | string | **yes** | Segment V2, RudderStack | Primary key joining to product catalog; drives affinity scoring |
| `sku` | string | no | Segment V2, RudderStack | Variant-level tracking when catalog has SKU != product_id |
| `name` | string | recommended | Segment V2, RudderStack, GA4 (`item_name`) | Human-readable label for dashboard |
| `category` | string | recommended | Segment V2, RudderStack, GA4 (`item_category`) | Funnel-position signal (category browsing) |
| `brand` | string | optional | Segment V2, GA4 (`item_brand`) | Affinity scoring |
| `variant` | string | optional | Segment V2, GA4 (`item_variant`) | Variant-level affinity |
| `price` | number | recommended | Segment V2, RudderStack, GA4 | Basket-size prediction, lead value |
| `currency` | string (ISO 4217) | recommended | GA4 (required when `value` set) | Multi-currency normalization |
| `position` | number | no | Segment V2 | List-rank in PLP (useful for CTR modeling) |
| `url` | string | recommended | Segment V2 | Joins to existing `page_view` rows on `page_url` |
| `image_url` | string | no | Segment V2 | Dashboard display only |

**Minimum set for v1.2 lead scoring:** `product_id`, `category`, `price`, `currency`, `url`.

---

### add_to_cart

**Canonical event name emitted to RudderStack:** `Product Added`
**GA4 equivalent:** `add_to_cart`
**Retailrocket equivalent:** `addtocart`
**Fires:** on Add-to-Cart button click (client-side), before the cart API roundtrip — the tracker should not wait for the server response

| Property | Type | Required | Spec source | Lead-scoring role |
|----------|------|----------|-------------|-------------------|
| `product_id` | string | **yes** | Segment V2, RudderStack | Joins to product catalog |
| `sku` | string | no | Segment V2 | Variant precision |
| `name` | string | recommended | Segment V2 | Dashboard label |
| `category` | string | recommended | Segment V2 | Funnel segmentation |
| `brand` | string | optional | Segment V2 | Affinity |
| `variant` | string | optional | Segment V2 | Variant precision |
| `price` | number | **yes** | Segment V2 (recommended); required for v1.2 basket-value scoring | Basket value |
| `quantity` | number | **yes** | Segment V2 (recommended); required for basket-size | Basket size |
| `currency` | string (ISO 4217) | recommended | GA4 | Value normalization |
| `cart_id` | string | recommended (v1.1 extension) | **Not in Segment V2** — but critical for v1.2 | Ties adds/removes to the same cart session; enables "basket composition" derived feature |

> **Note on `cart_id`:** Segment V2 does not specify `cart_id` on `Product Added`. For v1.2 lead scoring we need to correlate adds/removes within the same cart, and we cannot rely on `session_id` alone (a user can have multiple cart sessions). We adopt `cart_id` as a project-specific property, consistent with RudderStack's convention of allowing custom properties.

**Minimum set for v1.2 lead scoring:** `product_id`, `price`, `quantity`, `currency`, `cart_id`.

---

### remove_from_cart

**Canonical event name emitted to RudderStack:** `Product Removed`
**GA4 equivalent:** `remove_from_cart`
**Retailrocket equivalent:** (no direct equivalent — inferable by diff of addtocart vs transaction)
**Fires:** on Remove-from-Cart button click

**Property shape:** Identical to `add_to_cart`. Both Segment V2 and Fueled's implementation docs explicitly state "Product Removed follows the same specification as Product Added." Same required set, same `cart_id` convention.

| Property | Type | Required | Spec source | Lead-scoring role |
|----------|------|----------|-------------|-------------------|
| `product_id` | string | **yes** | Segment V2 | Catalog join |
| `price` | number | **yes** | v1.2 scoring need | Cart-value delta |
| `quantity` | number | **yes** | v1.2 scoring need | Cart-size delta |
| `currency` | string | recommended | GA4 | Normalization |
| `cart_id` | string | recommended | Project convention | Cart correlation |
| (all other optional fields from `add_to_cart`) | | optional | Segment V2 | |

---

### purchase (including multi-item handling)

**Canonical event name emitted to RudderStack:** `Order Completed`
**GA4 equivalent:** `purchase`
**Retailrocket equivalent:** `transaction`
**Fires:** on order confirmation page load, **or** server-side webhook from checkout service (preferred if available — client-side can be blocked by ad blockers, lost to navigation)

#### Top-level properties

| Property | Type | Required | Spec source | Lead-scoring role |
|----------|------|----------|-------------|-------------------|
| `order_id` | string | **yes** | Segment V2 (identifier), RudderStack, GA4 (`transaction_id`) | Idempotency key — see dedup pitfall |
| `total` | number | **yes** | Segment V2 | Final charged amount incl. tax/shipping |
| `revenue` | number | recommended | Segment V2 (only valid on `Order Completed`) | Pre-tax/shipping product revenue |
| `tax` | number | recommended | Segment V2, GA4 | Tax amount |
| `shipping` | number | recommended | Segment V2, GA4 | Shipping amount |
| `discount` | number | optional | Segment V2 | Discount applied |
| `coupon` | string | optional | Segment V2, GA4 | Coupon code |
| `currency` | string (ISO 4217) | **yes** | Segment V2, GA4 | Value normalization |
| `affiliation` | string | optional | Segment V2, GA4 | Store/channel attribution |
| `checkout_id` | string | optional | Segment V2 | Correlates to `Checkout Started` if tracked later |
| `products` | array | **yes** | Segment V2, RudderStack | Line items — see below |

#### `products[]` item shape

Each element in the `products` array mirrors the `add_to_cart` property shape (minus `cart_id`):

```
{
  product_id: string,  // required
  sku: string,
  name: string,
  category: string,
  brand: string,
  variant: string,
  price: number,       // required for v1.2
  quantity: number,    // required for v1.2
  coupon: string,
  position: number,
  url: string,
  image_url: string
}
```

#### Multi-item orders: single event with `products[]` array (DECISION)

**Recommendation: one `purchase` event per order, with a `products[]` array.**

| Consideration | Single event + array | One event per line item |
|---------------|----------------------|-------------------------|
| **Spec alignment** | Matches Segment V2, RudderStack, and GA4 (GA4 explicitly supports up to 200 items in one event) | Non-canonical in all three specs |
| **Dedup simplicity** | One `order_id` per event — dedup is a single `DISTINCT order_id` query | Every row shares `order_id`; must also dedup at (`order_id`, `product_id`) level; retry correctness harder |
| **Revenue accounting** | `total`, `revenue`, `tax`, `shipping` live on one row — no double-counting risk | Splitting order-level fields across N rows requires choosing one row as canonical or dividing totals — both error-prone |
| **ClickHouse ergonomics** | Requires `Array(Tuple(...))` or JSON for `products` (ClickHouse supports both natively) | Flat schema is simpler per-row, but aggregate queries need a GROUP BY order_id everywhere |
| **Retailrocket compatibility** | Retailrocket stores one row per `(transactionid, itemid)` pair → we emit one event, downstream flatten via `ARRAY JOIN` | Direct row-level mapping to Retailrocket's shape |
| **v1.2 lead scoring** | Basket composition (bundle features, affinity, basket-size) is a single-row aggregation | Basket features require a pre-aggregation step on every query |

**Chosen:** Single event with `products[]` array. The **ClickHouse materialized view** explodes the array into a per-line-item projection (`purchase_items` table) via `ARRAY JOIN` for anyone who wants the Retailrocket-style flat view — but the canonical row is one-per-order. This keeps dedup trivial (`order_id` is the idempotency key) and matches all three specs without translation loss.

**Rejected alternative:** Emitting N separate `purchase` events, one per line item, with shared `order_id`. Creates correctness hazards for order-level totals and doubles the dedup surface area.

---

### search

**Canonical event name emitted to RudderStack:** `Products Searched`
**GA4 equivalent:** `search`
**Retailrocket equivalent:** (none — Retailrocket has no search event)
**Fires:** on search submit (Enter key or button click), **not** on every keystroke — debounce in the tracker if the SPA emits per-keystroke events

| Property | Type | Required | Spec source | Lead-scoring role |
|----------|------|----------|-------------|-------------------|
| `query` | string | **yes** | Segment V2, RudderStack (`query`); GA4 uses `search_term` | Primary signal — search intent text |
| `results_count` | number | recommended (project extension) | Not in Segment V2 spec; added for v1.2 | Zero-result searches are a strong churn signal |
| `filters` | object | optional | Extension — serialize applied facets (category, price range) | Funnel-depth feature |
| `category` | string | optional | Extension — when search is scoped to a category | Affinity scoping |

**Spec divergence note:** RudderStack/Segment use `query`; GA4 uses `search_term`. The tracker emits `query` (matching RudderStack's SDK expectation); the ClickHouse materialized view exposes both column names as aliases so GA4-shaped consumers work too.

**Minimum set for v1.2 lead scoring:** `query`, `results_count`.

---

## Reconciliation Notes (spec divergences)

| Divergence | RudderStack / Segment V2 | GA4 | Retailrocket | Our choice |
|------------|--------------------------|-----|--------------|------------|
| Event name for PDP view | `Product Viewed` | `view_item` | `view` | `Product Viewed` (emit); store as `type = 'product_view'` in ClickHouse (snake_case, matches existing `click`/`scroll`/`page_view`) |
| Event name for purchase | `Order Completed` | `purchase` | `transaction` | `Order Completed` (emit); store as `type = 'purchase'` |
| Event name for search | `Products Searched` | `search` | — | `Products Searched` (emit); store as `type = 'search'` |
| Order items array key | `products[]` | `items[]` | (flat rows) | `products[]` in RudderStack payload; ClickHouse materialized view exposes both `products` and `items` aliases |
| Product identifier field | `product_id` | `item_id` | `itemid` | `product_id` in payload; ClickHouse projects both `product_id` and `item_id` columns |
| Order identifier field | `order_id` | `transaction_id` | `transactionid` | `order_id` in payload; ClickHouse projects both |
| Search query field | `query` | `search_term` | — | `query` in payload; ClickHouse projects both |
| Product name field | `name` | `item_name` | — | `name` in payload |
| Category field | `category` | `item_category` | — | `category` in payload |
| Currency | `currency` (recommended) | `currency` (required when `value` set) | — | `currency` required on all monetary events (`add_to_cart`, `remove_from_cart`, `purchase`, `product_view` if `price` present) |

**Rule of thumb:** Emit in RudderStack/Segment V2 shape (tracker-side simplicity, aligns with existing SDK wiring). Translate at the ClickHouse materialized view boundary (one place, tested once) for any downstream GA4 consumer.

---

## JSON Payload Examples

These are the exact payloads the tracker should pass to `rudderanalytics.track(eventName, properties)`. The `session_id` and `anonymous_user_id` are injected at the RudderStack context layer (already wired in v1.0) and are not repeated in `properties`.

### product_view

```json
{
  "event": "Product Viewed",
  "type": "product_view",
  "properties": {
    "product_id": "SKU-10293",
    "sku": "SKU-10293-RED-M",
    "name": "Classic Crew Neck Tee",
    "category": "Apparel/Tops",
    "brand": "Acme",
    "variant": "Red / M",
    "price": 24.99,
    "currency": "USD",
    "position": 3,
    "url": "https://shop.example.com/p/classic-tee",
    "image_url": "https://cdn.example.com/p/10293.jpg"
  },
  "timestamp": "2026-04-18T10:12:33.421Z"
}
```

### add_to_cart

```json
{
  "event": "Product Added",
  "type": "add_to_cart",
  "properties": {
    "product_id": "SKU-10293",
    "sku": "SKU-10293-RED-M",
    "name": "Classic Crew Neck Tee",
    "category": "Apparel/Tops",
    "brand": "Acme",
    "variant": "Red / M",
    "price": 24.99,
    "quantity": 2,
    "currency": "USD",
    "cart_id": "cart_0b4f9a"
  },
  "timestamp": "2026-04-18T10:13:01.118Z"
}
```

### remove_from_cart

```json
{
  "event": "Product Removed",
  "type": "remove_from_cart",
  "properties": {
    "product_id": "SKU-10293",
    "sku": "SKU-10293-RED-M",
    "name": "Classic Crew Neck Tee",
    "category": "Apparel/Tops",
    "price": 24.99,
    "quantity": 1,
    "currency": "USD",
    "cart_id": "cart_0b4f9a"
  },
  "timestamp": "2026-04-18T10:13:47.002Z"
}
```

### purchase (multi-item)

```json
{
  "event": "Order Completed",
  "type": "purchase",
  "properties": {
    "order_id": "ORD-2026-04-18-000731",
    "total": 74.97,
    "revenue": 64.98,
    "tax": 5.99,
    "shipping": 4.00,
    "discount": 0,
    "coupon": null,
    "currency": "USD",
    "affiliation": "web-store",
    "checkout_id": "chk_8f27e3",
    "products": [
      {
        "product_id": "SKU-10293",
        "sku": "SKU-10293-RED-M",
        "name": "Classic Crew Neck Tee",
        "category": "Apparel/Tops",
        "brand": "Acme",
        "variant": "Red / M",
        "price": 24.99,
        "quantity": 2,
        "position": 1,
        "url": "https://shop.example.com/p/classic-tee"
      },
      {
        "product_id": "SKU-44112",
        "sku": "SKU-44112-BLK",
        "name": "Everyday Baseball Cap",
        "category": "Apparel/Hats",
        "brand": "Acme",
        "variant": "Black",
        "price": 15.00,
        "quantity": 1,
        "position": 2,
        "url": "https://shop.example.com/p/everyday-cap"
      }
    ]
  },
  "timestamp": "2026-04-18T10:15:22.884Z"
}
```

### search

```json
{
  "event": "Products Searched",
  "type": "search",
  "properties": {
    "query": "red cotton tee",
    "results_count": 42,
    "category": "Apparel/Tops",
    "filters": {
      "color": "red",
      "price_max": 50
    }
  },
  "timestamp": "2026-04-18T10:09:55.317Z"
}
```

---

## Emission Pattern (tracker API shape)

The existing v1.0 tracker uses a **direct queue-and-flush pattern** (`eventQueue.push(...)` then `trackEventBatch(events, sessionId)` flushes to RudderStack). The v1.1 events should follow the same pattern — not introduce a new delivery path — but through a **public API exposed on the tracker** so host sites can call it from their SPA framework (React hook, Vue composable, plain JS — the tracker stays framework-agnostic).

**Recommended shape (extends `src/tracker/events.js`):**

```js
// New public functions, same consent/queue conventions as v1.0
function captureProductView(product, eventQueue, hasConsent) { ... }
function captureAddToCart(product, cart, eventQueue, hasConsent) { ... }
function captureRemoveFromCart(product, cart, eventQueue, hasConsent) { ... }
function capturePurchase(order, eventQueue, hasConsent) { ... }
function captureSearch(searchData, eventQueue, hasConsent) { ... }
```

**Why this pattern (rejected alternatives):**

| Pattern | Verdict | Reason |
|---------|---------|--------|
| **Direct function call on tracker instance** (chosen) | ✅ | Matches v1.0 architecture. Host site imports `window.LeadTracker.productView({...})`. Framework-agnostic. |
| **`dataLayer.push({...})` (GTM convention)** | ❌ | Adds a second abstraction layer and a GTM dependency. v1.0 does not use GTM; introducing it for v1.1 is scope creep. |
| **Auto-detection via DOM mutation observers** | ❌ | Unreliable (every e-commerce SPA structures DOM differently), expensive, and contradicts the explicit-consent model. |
| **Wrap an existing framework event bus** | ❌ | Couples tracker to a specific framework. Host sites in this project may use any SPA (Next.js, vanilla, etc.). |

**Public API surface exposed to host sites:**

```js
window.LeadTracker = {
  // v1.0 (existing)
  init(config),
  // v1.1 new
  productView(product),         // accepts a product object
  addToCart(product, cart),     // product + cart context
  removeFromCart(product, cart),
  purchase(order),              // order object with products[]
  search(query, results, filters)
};
```

Each function: (1) checks `hasConsent()` first (v1.0 gate), (2) normalizes the input into the canonical property shape above, (3) pushes onto `eventQueue`, (4) the existing flush loop sends via `rudderanalytics.track(eventName, properties)`.

---

## Pitfalls & Prevention

### Critical

#### P-1: Purchase deduplication on retries and back-button reloads
**What goes wrong:** User refreshes the order confirmation page, or the SPA retries a failed network call, or the user hits Back and Forward — each re-fires `Order Completed` with the same `order_id`. Downstream revenue is double-counted.
**Prevention:**
- The tracker MUST check a `localStorage` set of seen `order_id`s before emitting `Order Completed`. First emit marks the ID as seen; subsequent emits are no-ops with a `console.debug` trace.
- The ClickHouse `orders` projection MUST use `ReplacingMergeTree(event_time)` keyed on `order_id`, so even if a duplicate slips past the tracker, the materialized view collapses it.
- The `order_id` must follow GA4's format rules if we ever pipe to GA4 later: alphanumeric + underscore only, max 256 chars, unique within 31 days. Reject dashes and spaces at the tracker boundary.
**Detection:** Daily query `SELECT order_id, COUNT(*) FROM purchase_events GROUP BY order_id HAVING COUNT(*) > 1` — should return zero rows.

#### P-2: Consent gate compatibility with e-commerce flows
**What goes wrong:** In v1.0 the consent gate blocks all tracking until the user clicks Accept. But e-commerce sites often have guest checkout — a user can browse, add to cart, and purchase without ever interacting with the banner. Under a strict consent gate, we capture zero purchase events for guest checkouts.
**Prevention:**
- Keep the strict gate for v1.1. Document explicitly that guest-checkout purchases where consent was not given will not be captured — this is correct GDPR behavior, not a bug.
- If business requirements demand it, add a second consent category `transaction_tracking` with its own opt-in — but this is a scope expansion, not a v1.1 item.
- The consent banner should include a pre-checkout reminder: "Accept cookies to help us improve your shopping experience." (Copy change only, not code.)
**Detection:** Compare `COUNT(DISTINCT session_id) WHERE type='page_view' AND url LIKE '%/checkout/%'` against `COUNT(DISTINCT session_id) WHERE type='purchase'`. A large gap flags unconsented guest flows.

#### P-3: event_payload JSON structure inconsistency with v1.0
**What goes wrong:** v1.0 events are flat (`x_pct`, `y_pct`, `element_selector` as top-level columns + raw JSON in `event_payload`). v1.1 `purchase` has a nested `products[]` array. If the ClickHouse materialized view is written naïvely, it tries to flatten `products` into scalar columns and loses data, or silently drops the array.
**Prevention:**
- Keep `event_payload String` as the raw source-of-truth column — write the entire RudderStack `properties` object there as JSON, unchanged, for every event type.
- Add **typed nullable columns** for the new e-commerce fields (`product_id Nullable(String)`, `category Nullable(String)`, `price Nullable(Float64)`, `quantity Nullable(UInt32)`, `order_id Nullable(String)`, `cart_value Nullable(Float64)`, `search_query Nullable(String)`, `results_count Nullable(UInt32)`). v1.0 rows leave them NULL; v1.1 rows populate them from the JSON via `JSONExtract` in the materialized view.
- For `purchase`, create a **second materialized view** `purchase_items` that `ARRAY JOIN`s the `products[]` array into one row per line item. Dashboard queries for per-product metrics use `purchase_items`; order-level queries use the main events table.

### Moderate

#### P-4: `price` and `quantity` type drift
**What goes wrong:** Different SPA codebases pass `price` as a string ("24.99") or include currency symbols ("$24.99"), and `quantity` as a string ("2"). Lead scoring breaks silently when SUM() returns NaN.
**Prevention:** The tracker's `captureAddToCart` / `capturePurchase` etc. must coerce `price` to Number and strip non-numeric characters; coerce `quantity` to Integer. Log a `console.warn` on coercion so debugging is possible. Reject events where coercion produces NaN.

#### P-5: Missing `currency` breaks multi-store deployments
**What goes wrong:** A single tracker deployment covers two stores (USD and EUR). Monetary values are summed without normalization — cart value becomes meaningless.
**Prevention:** Make `currency` required at the tracker boundary (reject emission if absent on any monetary event). Default to a config-level `defaultCurrency` passed to `init()` so host sites can set it once.

#### P-6: SPA route-change `product_view` double-fires
**What goes wrong:** Some SPAs fire the history API on both the `pushState` and the subsequent `popstate`, causing two `product_view` events per actual navigation.
**Prevention:** Reuse the v1.0 SPA page-view debounce (if it exists) for `product_view`. If not implemented in v1.0, add a 300ms debounce keyed on `(product_id, url)` in the tracker.

#### P-7: Search debouncing — per-keystroke vs per-submit
**What goes wrong:** Emitting `Products Searched` on every keystroke ("r", "re", "red", "red ", "red c", ...) floods the pipeline and the query field becomes meaningless for lead scoring.
**Prevention:** `captureSearch` should only be called on explicit submit events (Enter key, button click, filter apply). Do NOT wire it to `input` events. Document this clearly in the tracker README.

### Minor

#### P-8: `cart_id` lifecycle
**What goes wrong:** `cart_id` is a v1.1 extension and is not a standard spec field. Implementations may forget to reset it after checkout completion, causing post-purchase `Product Added` events (e.g., a user immediately starts a new cart) to share the previous `cart_id`.
**Prevention:** The tracker's `capturePurchase` should clear/rotate `cart_id` after a successful purchase emit. Document in the public API that host sites pass a fresh `cart_id` at cart creation time — the tracker does not generate it.

#### P-9: Large `products[]` arrays in a single payload
**What goes wrong:** Wholesale/B2B orders can have hundreds of line items. RudderStack has no hard limit but Kafka message size (default 1 MB) and ClickHouse JSON parsing can choke.
**Prevention:** GA4 caps at 200 items/event. Adopt the same cap in the tracker — if `products.length > 200`, split into multiple `purchase` events each with a unique synthesized `order_id` suffix (`ORD-xxx_part1`, `ORD-xxx_part2`) AND add a `parent_order_id` field. For this academic project the 200-item cap is unlikely to be hit; document and move on.

---

## Retailrocket Compatibility Notes

The v1.2 lead-scoring work uses Retailrocket's dataset for training. The tracker-emitted events must map bidirectionally:

| Retailrocket column | Retailrocket event | Our event | Our property | Notes |
|---------------------|-------------------|-----------|--------------|-------|
| `timestamp` | all | all | `timestamp` (RudderStack context) | Retailrocket is Unix ms; ours is ISO 8601 — convert at the materialized view |
| `visitorid` | all | all | `anonymous_user_id` (RudderStack context, hashed) | |
| `event` = "view" | view | `product_view` | — | 1:1 mapping |
| `event` = "addtocart" | addtocart | `add_to_cart` | — | 1:1 mapping; Retailrocket has no `quantity`, assume 1 |
| `event` = "transaction" | transaction | `purchase` | — | One row per `(transactionid, itemid)` in Retailrocket → `ARRAY JOIN products` in our materialized view |
| `itemid` | all | `product_view`, `add_to_cart`, `purchase` | `product_id` (or `products[].product_id`) | `itemid` is integer in RR; we use string to allow SKU-style IDs |
| `transactionid` | transaction | `purchase` | `order_id` | Integer in RR; we use string |

**Missing Retailrocket signals that our tracker provides:** `category`, `price`, `quantity`, `currency`, `url`, `cart_id`, `results_count`, full search events. These are net-new training features for v1.2.
**Retailrocket signals our tracker does not capture:** none — all five Retailrocket event types (`view`, `addtocart`, `transaction`) have a direct equivalent; Retailrocket has no search.

**Implication for v1.2:** A Retailrocket-trained model can run on our event stream by projecting our events down to the Retailrocket schema. The reverse (augmenting Retailrocket with our richer signals) is not possible — Retailrocket data is static. Plan v1.2 model experiments around the Retailrocket-compatible subset first, then layer on our richer signals as additional features.

---

## Sources

**Primary (authoritative):**
- [Segment Ecommerce Spec V2 — V2 Ecommerce Events](https://segment.com/docs/connections/spec/ecommerce/v2/) — HIGH confidence (canonical reference; ecosystem-wide source of `Product Viewed`, `Product Added`, `Product Removed`, `Order Completed`, `Products Searched` event names and snake_case property shape)
- [Google Analytics 4 — Measure Ecommerce](https://developers.google.com/analytics/devguides/collection/ga4/ecommerce) — HIGH confidence (required/recommended parameters for `view_item`, `add_to_cart`, `remove_from_cart`, `purchase`; items array up to 200 elements)
- [Google Analytics 4 — Recommended Events](https://developers.google.com/analytics/devguides/collection/ga4/reference/events) — HIGH confidence (GA4 event names and parameter definitions)
- [GA4 — Minimize duplicate key events with transaction IDs](https://support.google.com/analytics/answer/12313109?hl=en) — HIGH confidence (transaction_id uniqueness, 31-day window, alphanumeric + underscore rule)

**Secondary (community implementations of the same specs):**
- [Fueled — Order Completed spec implementation](https://learn.fueled.io/integrations/destinations/segment.com/segment-event-specifications/order-completed) — MEDIUM confidence (concrete property type table; confirms `order_id` as dedup key)
- [Fueled — Product Viewed spec implementation](https://learn.fueled.io/integrations/destinations/segment.com/segment-event-specifications/product-viewed) — MEDIUM confidence (property list)
- [Fueled — Product Added/Removed spec implementation](https://learn.fueled.io/integrations/destinations/segment.com/segment-event-specifications/product-added-removed) — MEDIUM confidence (confirms both events share the same spec; no standard `cart_id`)
- [RudderStack Docs — Ecommerce Events Specification index](https://www.rudderstack.com/docs/event-spec/ecommerce-events-spec/) — MEDIUM confidence (confirms RudderStack uses Segment V2 event names; deep-page content not retrievable during research, cross-verified via tracking-plan examples on the Data Catalog page)
- [RudderStack Docs — Data Catalog (event examples)](https://www.rudderstack.com/docs/data-governance/git-based-management/data-catalog/events/) — MEDIUM confidence (shows Product Viewed property shape in tracking-plan YAML)

**Retailrocket dataset:**
- [Retailrocket recommender system dataset (Kaggle)](https://www.kaggle.com/datasets/retailrocket/ecommerce-dataset) — HIGH confidence (5-column schema, three event types)
- [RecPack — RetailRocket dataset docs](https://recpack.froomle.ai/generated/recpack.datasets.RetailRocket.html) — HIGH confidence (events table columns)

**Dedup / operational best practice:**
- [DataVinci — Duplicate Transactions in GA4 guide](https://datavinci.services/blog/unlocking-the-mystery-of-duplicate-transactions-in-ga4-a-comprehensive-guide-to-resolution/) — MEDIUM confidence (client-side dedup patterns, dataLayer guard checks)
- [Stape Community — GA4 deduplicate with same transaction id](https://community.stape.io/t/ga4-deduplicate-with-same-transaction-id/2569) — LOW confidence (community thread; used only to corroborate the primary GA4 doc)

**Confidence summary:** HIGH for all event names, property shapes, and the single-event-with-array purchase decision. MEDIUM for RudderStack-specific page-level details (the direct ecommerce-spec pages 404'd or returned navigation-only content, but RudderStack explicitly mirrors Segment V2 and the SDK behavior is confirmed by the existing v1.0 code path). LOW for `cart_id` convention (project-specific extension, not in any surveyed spec).
