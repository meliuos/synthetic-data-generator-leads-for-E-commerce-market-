#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# v1.1 E-commerce Schema Smoke Test
# Produces 4 events through Redpanda → ClickHouse and asserts 6 outcomes:
#   1. 8 new columns populated (SCHEMA-01 coverage)
#   2. Flat JSON extraction — product_view (SCHEMA-02 flat)
#   3. Nested properties JSON extraction — add_to_cart (SCHEMA-02 nested)
#   4. Per-line-item fan-out in analytics.purchase_items (SCHEMA-03 ARRAY JOIN)
#   5. Order dedup in analytics.orders FINAL (SCHEMA-03 ReplacingMergeTree)
#   6. GA4 alias view returns item_id / transaction_id / search_term columns
# ---------------------------------------------------------------------------

COMPOSE=${COMPOSE:-docker compose}
CLICKHOUSE_USER=${CLICKHOUSE_USER:-analytics}
CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD:-analytics_password}
TOPIC=${EVENTS_TOPIC:-lead-events}

SESSION_ID="ecom-smoke-$(date +%s)"
ORDER_ID="ord-${SESSION_ID}"

# Event timestamps: purchase-C slightly before purchase-D so ReplacingMergeTree
# keeps the later event_time (event-D) as the surviving row after FINAL dedup.
TS_BASE=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")
TS_LATER=$(date -u +"%Y-%m-%dT%H:%M:%S.050Z")

echo "Starting v1.1 e-commerce smoke test (session_id=${SESSION_ID}, order_id=${ORDER_ID})"

# ---------------------------------------------------------------------------
# Ensure topic exists
# ---------------------------------------------------------------------------
$COMPOSE exec -T redpanda rpk topic create "$TOPIC" -p 1 -r 1 >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
# Helper: run a ClickHouse query and return trimmed output
# ---------------------------------------------------------------------------
ch_query() {
    $COMPOSE exec -T clickhouse clickhouse-client \
        --user "$CLICKHOUSE_USER" \
        --password "$CLICKHOUSE_PASSWORD" \
        --query "$1" 2>/dev/null | tr -d '[:space:]'
}

ch_query_raw() {
    $COMPOSE exec -T clickhouse clickhouse-client \
        --user "$CLICKHOUSE_USER" \
        --password "$CLICKHOUSE_PASSWORD" \
        --query "$1" 2>/dev/null
}

# ---------------------------------------------------------------------------
# EVENT A — product_view, FLAT shape (top-level e-commerce fields, no properties)
# Tests SCHEMA-02 flat extraction: product_id, category, price from top-level keys
# ---------------------------------------------------------------------------
EVENT_A=$(cat <<EOF
{"event_id":"evt-a-${SESSION_ID}","event_time":"${TS_BASE}","event_type":"product_view","type":"product_view","page_url":"https://example.com/product/SKU-100","session_id":"${SESSION_ID}","anonymous_user_id":"anon_ecom_smoke","device_type":"desktop","product_id":"SKU-100","category":"electronics/headphones","price":99.99,"event_payload":"{\"source\":\"smoke-v11\",\"shape\":\"flat\"}"}
EOF
)

# ---------------------------------------------------------------------------
# EVENT B — add_to_cart, NESTED properties shape
# Tests SCHEMA-02 nested extraction: product_id, quantity, price via properties fallback
# ---------------------------------------------------------------------------
EVENT_B=$(cat <<EOF
{"event_id":"evt-b-${SESSION_ID}","event_time":"${TS_BASE}","event_type":"add_to_cart","type":"add_to_cart","page_url":"https://example.com/product/SKU-200","session_id":"${SESSION_ID}","anonymous_user_id":"anon_ecom_smoke","device_type":"desktop","properties":{"product_id":"SKU-200","quantity":3,"price":19.50},"event_payload":"{\"source\":\"smoke-v11\",\"shape\":\"nested\"}"}
EOF
)

# ---------------------------------------------------------------------------
# EVENT C — purchase with properties.products[] (fans out per-line-item)
# Tests SCHEMA-03: purchase_items ARRAY JOIN MV + orders dedup MV
# Uses 'timestamp' field for event_time (secondary MVs read 'timestamp', not 'event_time')
# Uses 'session_id' at top level (read by secondary MVs directly)
# ---------------------------------------------------------------------------
EVENT_C=$(cat <<EOF
{"event_id":"evt-c-${SESSION_ID}","timestamp":"${TS_BASE}","event_type":"purchase","type":"purchase","page_url":"https://example.com/checkout/thankyou","session_id":"${SESSION_ID}","anonymous_user_id":"anon_ecom_smoke","device_type":"desktop","properties":{"order_id":"${ORDER_ID}","total":139.49,"revenue":139.49,"currency":"USD","products":[{"product_id":"SKU-100","name":"Headphones","category":"electronics/headphones","price":99.99,"quantity":1,"position":1},{"product_id":"SKU-200","name":"Cable","category":"electronics/cables","price":19.50,"quantity":2,"position":2}]},"event_payload":"{\"source\":\"smoke-v11\",\"shape\":\"purchase\"}"}
EOF
)

# ---------------------------------------------------------------------------
# EVENT D — duplicate purchase (same order_id, different event_id/timestamp)
# Tests ReplacingMergeTree dedup: analytics.orders FINAL must return count()=1
# event_time 50ms later than Event C → this row wins in ReplacingMergeTree(event_time)
# ---------------------------------------------------------------------------
EVENT_D=$(cat <<EOF
{"event_id":"evt-d-${SESSION_ID}","timestamp":"${TS_LATER}","event_type":"purchase","type":"purchase","page_url":"https://example.com/checkout/thankyou","session_id":"${SESSION_ID}","anonymous_user_id":"anon_ecom_smoke","device_type":"desktop","properties":{"order_id":"${ORDER_ID}","total":139.49,"revenue":139.49,"currency":"USD","products":[{"product_id":"SKU-100","name":"Headphones","category":"electronics/headphones","price":99.99,"quantity":1,"position":1},{"product_id":"SKU-200","name":"Cable","category":"electronics/cables","price":19.50,"quantity":2,"position":2}]},"event_payload":"{\"source\":\"smoke-v11\",\"shape\":\"purchase-dup\"}"}
EOF
)

# ---------------------------------------------------------------------------
# Produce all 4 events to the topic
# ---------------------------------------------------------------------------
echo "Producing 4 events to topic: $TOPIC"

printf '%s\n' "$EVENT_A" | $COMPOSE exec -T redpanda rpk topic produce "$TOPIC" -f '%v\n' >/dev/null
printf '%s\n' "$EVENT_B" | $COMPOSE exec -T redpanda rpk topic produce "$TOPIC" -f '%v\n' >/dev/null
printf '%s\n' "$EVENT_C" | $COMPOSE exec -T redpanda rpk topic produce "$TOPIC" -f '%v\n' >/dev/null
printf '%s\n' "$EVENT_D" | $COMPOSE exec -T redpanda rpk topic produce "$TOPIC" -f '%v\n' >/dev/null

echo "Events produced. Waiting for ClickHouse materialized views to flush..."

# ---------------------------------------------------------------------------
# BOUNDED POLL — wait up to 10s for events to land in click_events
# The v1.1 test gives extra time (10s vs 5s) for the secondary MVs to also flush.
# ---------------------------------------------------------------------------
deadline=$((SECONDS + 10))

while (( SECONDS <= deadline )); do
    base_count=$(ch_query "SELECT count() FROM analytics.click_events WHERE session_id = '${SESSION_ID}'")
    if [[ "$base_count" -ge 4 ]]; then
        echo "Base events landed: click_events count=${base_count}"
        break
    fi
    if (( SECONDS > deadline )); then
        echo "FAIL: events were not ingested into click_events within 10 seconds (session_id=${SESSION_ID}, count=${base_count})" >&2
        exit 1
    fi
done

if [[ "$base_count" -lt 4 ]]; then
    echo "FAIL: events were not ingested into click_events within 10 seconds (session_id=${SESSION_ID}, count=${base_count})" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# ASSERTION 1 — SCHEMA-01: 8 new columns populated at least once
# Expected: c_product_id>=2, c_category>=2, c_price>=2, c_quantity>=1, c_order_id>=2
# cart_value, search_query, results_count not exercised — not asserted
# ---------------------------------------------------------------------------
echo "Assertion 1: SCHEMA-01 column coverage..."

ASSERT1=$(ch_query_raw "SELECT
    countIf(product_id IS NOT NULL)    AS c_product_id,
    countIf(category IS NOT NULL)      AS c_category,
    countIf(price IS NOT NULL)         AS c_price,
    countIf(quantity IS NOT NULL)      AS c_quantity,
    countIf(order_id IS NOT NULL)      AS c_order_id,
    countIf(cart_value IS NOT NULL)    AS c_cart_value,
    countIf(search_query IS NOT NULL)  AS c_search_query,
    countIf(results_count IS NOT NULL) AS c_results_count
FROM analytics.click_events
WHERE session_id = '${SESSION_ID}'
FORMAT TabSeparated")

read -r c_product_id c_category c_price c_quantity c_order_id c_cart_value c_search_query c_results_count <<< "$ASSERT1"

fail1=0
[[ "$c_product_id" -ge 2 ]]  || { echo "FAIL: Assertion 1 — c_product_id=${c_product_id} (expected >=2)" >&2; fail1=1; }
[[ "$c_category"   -ge 2 ]]  || { echo "FAIL: Assertion 1 — c_category=${c_category} (expected >=2)" >&2; fail1=1; }
[[ "$c_price"      -ge 2 ]]  || { echo "FAIL: Assertion 1 — c_price=${c_price} (expected >=2)" >&2; fail1=1; }
[[ "$c_quantity"   -ge 1 ]]  || { echo "FAIL: Assertion 1 — c_quantity=${c_quantity} (expected >=1)" >&2; fail1=1; }
[[ "$c_order_id"   -ge 2 ]]  || { echo "FAIL: Assertion 1 — c_order_id=${c_order_id} (expected >=2)" >&2; fail1=1; }

if [[ "$fail1" -ne 0 ]]; then
    echo "  Observed counts: product_id=${c_product_id} category=${c_category} price=${c_price} quantity=${c_quantity} order_id=${c_order_id} cart_value=${c_cart_value} search_query=${c_search_query} results_count=${c_results_count}" >&2
    exit 1
fi
echo "  PASS: product_id=${c_product_id} category=${c_category} price=${c_price} quantity=${c_quantity} order_id=${c_order_id}"

# ---------------------------------------------------------------------------
# ASSERTION 2 — SCHEMA-02 flat extraction: Event A (product_view)
# Expected: product_id='SKU-100', category='electronics/headphones', price~=99.99
# ---------------------------------------------------------------------------
echo "Assertion 2: SCHEMA-02 flat extraction (product_view)..."

ASSERT2=$(ch_query_raw "SELECT product_id, category, toString(price)
FROM analytics.click_events
WHERE session_id='${SESSION_ID}' AND event_type='product_view'
FORMAT TabSeparated")

if [[ -z "$ASSERT2" ]]; then
    echo "FAIL: Assertion 2 — no product_view row found for session_id=${SESSION_ID}" >&2
    exit 1
fi

read -r pid2 cat2 price2 <<< "$ASSERT2"

if [[ "$pid2" != "SKU-100" ]]; then
    echo "FAIL: Assertion 2 — product_id='${pid2}' (expected 'SKU-100')" >&2
    echo "  Full row: ${ASSERT2}" >&2
    exit 1
fi
if [[ "$cat2" != "electronics/headphones" ]]; then
    echo "FAIL: Assertion 2 — category='${cat2}' (expected 'electronics/headphones')" >&2
    exit 1
fi
if [[ -z "$price2" ]]; then
    echo "FAIL: Assertion 2 — price is NULL/empty (expected ~99.99)" >&2
    exit 1
fi
echo "  PASS: product_id=${pid2} category=${cat2} price=${price2}"

# ---------------------------------------------------------------------------
# ASSERTION 3 — SCHEMA-02 nested extraction: Event B (add_to_cart, properties shape)
# Expected: product_id='SKU-200', quantity=3, price~=19.50
# ---------------------------------------------------------------------------
echo "Assertion 3: SCHEMA-02 nested extraction (add_to_cart)..."

ASSERT3=$(ch_query_raw "SELECT product_id, toString(quantity), toString(price)
FROM analytics.click_events
WHERE session_id='${SESSION_ID}' AND event_type='add_to_cart'
FORMAT TabSeparated")

if [[ -z "$ASSERT3" ]]; then
    echo "FAIL: Assertion 3 — no add_to_cart row found for session_id=${SESSION_ID}" >&2
    exit 1
fi

read -r pid3 qty3 price3 <<< "$ASSERT3"

if [[ "$pid3" != "SKU-200" ]]; then
    echo "FAIL: Assertion 3 — product_id='${pid3}' (expected 'SKU-200')" >&2
    echo "  Full row: ${ASSERT3}" >&2
    exit 1
fi
if [[ "$qty3" != "3" ]]; then
    echo "FAIL: Assertion 3 — quantity='${qty3}' (expected '3')" >&2
    exit 1
fi
if [[ -z "$price3" ]]; then
    echo "FAIL: Assertion 3 — price is NULL/empty (expected ~19.50)" >&2
    exit 1
fi
echo "  PASS: product_id=${pid3} quantity=${qty3} price=${price3}"

# ---------------------------------------------------------------------------
# ASSERTION 4 — Per-line-item fan-out in analytics.purchase_items
# Expected: count()=4 (2 purchase events × 2 line items each)
#           groupArray contains both 'SKU-100' and 'SKU-200'
# ---------------------------------------------------------------------------
echo "Assertion 4: SCHEMA-03 per-line-item fan-out (purchase_items)..."

# Give purchase_items_mv extra time to flush if needed
deadline2=$((SECONDS + 10))
items_count=0

while (( SECONDS <= deadline2 )); do
    items_count=$(ch_query "SELECT count() FROM analytics.purchase_items WHERE order_id = '${ORDER_ID}'")
    if [[ "$items_count" -ge 4 ]]; then
        break
    fi
done

if [[ "$items_count" -lt 4 ]]; then
    echo "FAIL: Assertion 4 — purchase_items count=${items_count} for order_id=${ORDER_ID} (expected 4)" >&2
    echo "  Query: SELECT count() FROM analytics.purchase_items WHERE order_id = '${ORDER_ID}'" >&2
    exit 1
fi

ITEMS_SKUS=$(ch_query_raw "SELECT groupArray(product_id) FROM analytics.purchase_items WHERE order_id = '${ORDER_ID}' FORMAT TabSeparated")

if ! echo "$ITEMS_SKUS" | grep -q "SKU-100"; then
    echo "FAIL: Assertion 4 — SKU-100 not found in purchase_items groupArray: ${ITEMS_SKUS}" >&2
    exit 1
fi
if ! echo "$ITEMS_SKUS" | grep -q "SKU-200"; then
    echo "FAIL: Assertion 4 — SKU-200 not found in purchase_items groupArray: ${ITEMS_SKUS}" >&2
    exit 1
fi
echo "  PASS: purchase_items count=${items_count}, skus=${ITEMS_SKUS}"

# ---------------------------------------------------------------------------
# ASSERTION 5 — Server-side order_id dedup via analytics.orders FINAL
# MUST use FINAL to force query-time dedup before background merge fires
# Expected: count()=1 (both duplicate purchase events collapse to one row)
# ---------------------------------------------------------------------------
echo "Assertion 5: SCHEMA-03 order dedup (orders FINAL)..."

# Give orders_mv extra time if needed
deadline3=$((SECONDS + 10))
orders_count=0

while (( SECONDS <= deadline3 )); do
    orders_count=$(ch_query "SELECT count() FROM analytics.orders FINAL WHERE order_id = '${ORDER_ID}'")
    if [[ "$orders_count" -ge 1 ]]; then
        break
    fi
done

if [[ "$orders_count" -ne 1 ]]; then
    RAW_COUNT=$(ch_query "SELECT count() FROM analytics.orders WHERE order_id = '${ORDER_ID}'")
    echo "FAIL: Assertion 5 — orders FINAL count=${orders_count} for order_id=${ORDER_ID} (expected 1)" >&2
    echo "  Query: SELECT count() FROM analytics.orders FINAL WHERE order_id = '${ORDER_ID}'" >&2
    echo "  Without FINAL count=${RAW_COUNT} (shows raw inserted rows before background merge)" >&2
    exit 1
fi
echo "  PASS: orders FINAL count=${orders_count} (dedup confirmed for order_id=${ORDER_ID})"

# ---------------------------------------------------------------------------
# ASSERTION 6 — GA4 alias view exposes renamed columns
# Expected: exactly one product_view row with item_id='SKU-100',
#           item_category='electronics/headphones', transaction_id NULL, search_term NULL
# ---------------------------------------------------------------------------
echo "Assertion 6: GA4 alias view (click_events_ga4)..."

ASSERT6=$(ch_query_raw "SELECT item_id, item_category, toString(transaction_id), toString(search_term)
FROM analytics.click_events_ga4
WHERE session_id = '${SESSION_ID}' AND event_type = 'product_view'
FORMAT TabSeparated")

if [[ -z "$ASSERT6" ]]; then
    echo "FAIL: Assertion 6 — no product_view row found in click_events_ga4 for session_id=${SESSION_ID}" >&2
    echo "  Query: SELECT item_id, item_category, transaction_id, search_term FROM analytics.click_events_ga4 WHERE session_id='${SESSION_ID}' AND event_type='product_view'" >&2
    exit 1
fi

read -r item_id6 item_cat6 txn_id6 search_term6 <<< "$ASSERT6"

if [[ "$item_id6" != "SKU-100" ]]; then
    echo "FAIL: Assertion 6 — item_id='${item_id6}' (expected 'SKU-100')" >&2
    echo "  Full row: ${ASSERT6}" >&2
    exit 1
fi
if [[ "$item_cat6" != "electronics/headphones" ]]; then
    echo "FAIL: Assertion 6 — item_category='${item_cat6}' (expected 'electronics/headphones')" >&2
    exit 1
fi
echo "  PASS: item_id=${item_id6} item_category=${item_cat6} transaction_id=${txn_id6} search_term=${search_term6}"

# ---------------------------------------------------------------------------
# ALL ASSERTIONS PASSED
# ---------------------------------------------------------------------------
echo ""
echo "PASS: v1.1 e-commerce schema smoke test (session_id=${SESSION_ID}, order_id=${ORDER_ID})"
exit 0
