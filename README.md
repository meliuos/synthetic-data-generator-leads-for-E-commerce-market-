# Lead Intelligence Platform

Phase 1 bootstraps the local event backbone:
- Redpanda (Kafka-compatible broker)
- ClickHouse (analytics store)
- RudderStack data plane
- Streamlit dashboard shell

## Quickstart

1. Copy the environment template:
   ```bash
   cp .env.example .env
   ```
2. Validate Docker Compose:
   ```bash
   make validate
   ```
3. Start the stack:
   ```bash
   make up
   ```
4. Apply ClickHouse schema:
   ```bash
   make schema
   ```
4. Verify containers are healthy:
   ```bash
   make ps
   ```
5. Verify ingestion tables:
   ```bash
   docker compose exec -T clickhouse clickhouse-client --query "SHOW TABLES FROM analytics"
   ```
6. Run end-to-end smoke test (manual produce -> MergeTree row):
   ```bash
   make smoke-test
   ```
7. Stop the stack when done:
   ```bash
   make down
   ```

## Exposed Services

- Redpanda Kafka: localhost:19092
- Redpanda HTTP proxy: localhost:8082
- ClickHouse HTTP: localhost:8123
- RudderStack gateway: localhost:8080
- Streamlit app: localhost:8501

## Notes

- ClickHouse async inserts are enabled in `infra/clickhouse/users.d/async_insert.xml`.
- RudderStack file-based config is in `infra/rudderstack/workspaceConfig.json` and forwards events to topic `lead-events`.
- ClickHouse ingestion schema is defined in `infra/clickhouse/sql/001_events_schema.sql` and creates `events_queue`, `events_mv`, and `click_events`.
- Smoke test script is `scripts/smoke-test.sh`; it publishes one JSON event to Redpanda and verifies ingestion in under 5 seconds.
- [Schema v1.1 (e-commerce events)](docs/schema-v1.1.md) — 8 new Nullable columns on `analytics.click_events`, per-line-item `purchase_items` table, server-side `orders` dedup, GA4 alias view. Apply via `make schema-v11`; verify via `make smoke-test-v11`.
- Phase 6 tracker APIs are available in `src/tracker/index.js`: `productView`, `addToCart`, `removeFromCart`, `purchase`, `search`; all methods inherit consent gating.
- The demo shop at `src/test-spa-page.html` exercises all 5 e-commerce APIs with product cards, cart controls, checkout, and search.
- `search` emits only on explicit submit (Search button / Enter), never on keystroke input.
- Retailrocket import (Phase 7):
   1. Add Kaggle API credentials at `~/.kaggle/kaggle.json`.
   2. Run `make retailrocket-download` (downloads exactly 4 CSV files into `data/retailrocket/`).
   3. Run `make schema-retailrocket` to create `retailrocket_raw.*` tables and helper views.
   4. Install importer dependency once: `python3 -m pip install -r scripts/retailrocket/requirements.txt`.
   5. Run `make retailrocket-import` then `make retailrocket-smoke`.
   6. Re-running `make retailrocket-import` is idempotent (load batch short-circuit + insert dedup tokens).
