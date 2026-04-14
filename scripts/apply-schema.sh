#!/usr/bin/env bash
set -euo pipefail

COMPOSE=${COMPOSE:-docker compose}
SQL_FILE=${1:-infra/clickhouse/sql/001_events_schema.sql}
CLICKHOUSE_USER=${CLICKHOUSE_USER:-analytics}
CLICKHOUSE_PASSWORD=${CLICKHOUSE_PASSWORD:-analytics_password}

if [[ ! -f "$SQL_FILE" ]]; then
  echo "Schema file not found: $SQL_FILE" >&2
  exit 1
fi

$COMPOSE exec -T clickhouse clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --query "SELECT 1" >/dev/null
$COMPOSE exec -T clickhouse clickhouse-client --user "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --multiquery < "$SQL_FILE"

echo "Schema applied successfully from $SQL_FILE"
