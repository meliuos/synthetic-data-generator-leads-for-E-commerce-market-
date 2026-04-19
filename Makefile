COMPOSE ?= docker compose
RETAILROCKET_VENV ?= .venv-retailrocket
RETAILROCKET_PYTHON ?= $(RETAILROCKET_VENV)/bin/python
RETAILROCKET_PIP ?= $(RETAILROCKET_VENV)/bin/pip

.PHONY: validate up down logs ps schema schema-v11 schema-retailrocket smoke-test smoke-test-v11 retailrocket-setup retailrocket-download retailrocket-import retailrocket-smoke retailrocket-reload

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

retailrocket-setup:
	python3 -m venv $(RETAILROCKET_VENV)
	$(RETAILROCKET_PIP) install --upgrade pip
	$(RETAILROCKET_PIP) install kaggle -r scripts/retailrocket/requirements.txt

retailrocket-download:
	PATH="$(PWD)/$(RETAILROCKET_VENV)/bin:$$PATH" bash scripts/download_retailrocket.sh

retailrocket-import:
	$(RETAILROCKET_PYTHON) scripts/retailrocket/import.py

retailrocket-smoke:
	docker compose exec -T clickhouse clickhouse-client --user "$${CLICKHOUSE_USER:-analytics}" --password "$${CLICKHOUSE_PASSWORD:-analytics_password}" --multiquery < scripts/retailrocket/smoke.sql

retailrocket-reload: schema-retailrocket retailrocket-import retailrocket-smoke
