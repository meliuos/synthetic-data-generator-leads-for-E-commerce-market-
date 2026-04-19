COMPOSE ?= docker compose

.PHONY: validate up down logs ps schema schema-v11 schema-retailrocket smoke-test smoke-test-v11 retailrocket-download retailrocket-import retailrocket-smoke retailrocket-reload

validate:
	$(COMPOSE) config >/dev/null

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down --remove-orphans

logs:
	$(COMPOSE) logs -f --tail=100

ps:
	$(COMPOSE) ps

schema:
	bash scripts/apply-schema.sh

schema-v11:
	bash scripts/apply-schema.sh infra/clickhouse/sql/002_ecommerce_schema.sql

smoke-test:
	bash scripts/smoke-test.sh

smoke-test-v11:
	bash scripts/smoke-test-v11.sh

schema-retailrocket:
	bash scripts/apply-schema.sh infra/clickhouse/sql/003_retailrocket_schema.sql

retailrocket-download:
	bash scripts/download_retailrocket.sh

retailrocket-import:
	python3 scripts/retailrocket/import.py

retailrocket-smoke:
	docker compose exec -T clickhouse clickhouse-client --user "$${CLICKHOUSE_USER:-analytics}" --password "$${CLICKHOUSE_PASSWORD:-analytics_password}" --multiquery < scripts/retailrocket/smoke.sql

retailrocket-reload: schema-retailrocket retailrocket-import retailrocket-smoke
