COMPOSE ?= docker compose

.PHONY: validate up down logs ps schema smoke-test

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
