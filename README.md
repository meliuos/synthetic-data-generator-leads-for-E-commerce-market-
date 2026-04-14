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
4. Verify containers are healthy:
   ```bash
   make ps
   ```
5. Stop the stack when done:
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

- ClickHouse async inserts are enabled in `infra/clickhouse/config.d/async_insert.xml`.
- RudderStack file-based config is in `infra/rudderstack/workspaceConfig.json` and forwards events to topic `lead-events`.
