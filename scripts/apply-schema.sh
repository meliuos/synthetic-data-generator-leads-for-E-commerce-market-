#!/usr/bin/env bash
set -euo pipefail

COMPOSE=${COMPOSE:-docker compose}
SQL_FILE=${1:-infra/clickhouse/sql/001_events_schema.sql}

if [[ ! -f "$SQL_FILE" ]]; then
  echo "Schema file not found: $SQL_FILE" >&2
  exit 1
fi

$COMPOSE exec -T clickhouse clickhouse-client --query "SELECT 1" >/dev/null
$COMPOSE exec -T clickhouse clickhouse-client --multiquery < "$SQL_FILE"

echo "Schema applied successfully from $SQL_FILE"
