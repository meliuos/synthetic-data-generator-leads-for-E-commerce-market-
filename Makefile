COMPOSE ?= docker compose

.PHONY: validate up down logs ps schema schema-v11 smoke-test smoke-test-v11

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
