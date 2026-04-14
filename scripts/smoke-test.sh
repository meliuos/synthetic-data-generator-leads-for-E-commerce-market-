#!/usr/bin/env bash
set -euo pipefail

COMPOSE=${COMPOSE:-docker compose}
CLICKHOUSE_USER=${CLICKHOUSE_USER:-analytics}
CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD:-analytics_password}
TOPIC=${EVENTS_TOPIC:-lead-events}
SESSION_ID="smoke-$(date +%s)"
EVENT_ID="evt-$SESSION_ID"
EVENT_TIME=$(date -u +"%Y-%m-%d %H:%M:%S.%3N")

JSON_PAYLOAD=$(cat <<EOF
{
  "records": [
    {
      "value": {
        "event_id": "$EVENT_ID",
        "event_time": "$EVENT_TIME",
        "event_type": "click",
        "page_url": "https://example.com/product/42",
        "referrer": "https://example.com/",
        "x_pct": 42.5,
        "y_pct": 63.1,
        "scroll_pct": 75.0,
        "element_selector": "button.buy-now",
        "element_tag": "button",
        "device_type": "desktop",
        "viewport_width": 1440,
        "viewport_height": 900,
        "session_id": "$SESSION_ID",
        "anonymous_user_id": "anon_hash_123",
        "event_payload": "{\"source\":\"smoke-test\"}"
      }
    }
  ]
}
EOF
)

echo "Producing smoke test event to topic: $TOPIC"
curl -sS -X POST "http://localhost:8082/topics/$TOPIC" \
  -H "Content-Type: application/vnd.kafka.json.v2+json" \
  -d "$JSON_PAYLOAD" >/dev/null

deadline=$((SECONDS + 5))
row_count=0

while (( SECONDS <= deadline )); do
  row_count=$($COMPOSE exec -T clickhouse clickhouse-client \
    --user "$CLICKHOUSE_USER" \
    --password "$CLICKHOUSE_PASSWORD" \
    --query "SELECT count() FROM analytics.click_events WHERE session_id = '$SESSION_ID'")
  row_count=$(echo "$row_count" | tr -d '[:space:]')
  if [[ "$row_count" != "0" ]]; then
    echo "PASS: event ingested in <=5s (session_id=$SESSION_ID, rows=$row_count)"
    exit 0
  fi
done

echo "FAIL: event was not ingested in 5 seconds (session_id=$SESSION_ID)" >&2
exit 1
