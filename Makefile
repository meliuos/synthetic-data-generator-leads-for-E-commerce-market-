COMPOSE ?= docker compose
RETAILROCKET_VENV ?= .venv-retailrocket

ifeq ($(OS),Windows_NT)
    RETAILROCKET_PYTHON ?= $(RETAILROCKET_VENV)/Scripts/python
    RETAILROCKET_PIP    ?= $(RETAILROCKET_VENV)/Scripts/pip
else
    RETAILROCKET_PYTHON ?= $(RETAILROCKET_VENV)/bin/python
    RETAILROCKET_PIP    ?= $(RETAILROCKET_VENV)/bin/pip
endif

.PHONY: validate up down logs ps schema schema-v11 schema-retailrocket schema-v12 schema-phase10 schema-phase11 smoke-test smoke-test-v11 smoke-test-v12 smoke-test-phase10 smoke-test-phase11 score-sessions ml-setup retailrocket-setup retailrocket-download retailrocket-import retailrocket-smoke retailrocket-reload synth-setup schema-phase13 smoke-test-phase13 ctgan-train generate-synthetic sim-setup simulate smoke-test-sim ai-setup schema-ai test-ai schema-phase17 predict-product test-predictor build-augmented-dataset train-augmented select-model test-registry api-up api-down api-test test-api schema-phase20 check-drift console-up lint

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

schema-v12:
	bash scripts/apply-schema.sh infra/clickhouse/sql/004_foundation.sql

smoke-test-v12:
	docker compose exec -T clickhouse clickhouse-client --user "$${CLICKHOUSE_USER:-analytics}" --password "$${CLICKHOUSE_PASSWORD:-analytics_password}" --multiquery < scripts/verify_features.sql

schema-phase10:
	bash scripts/apply-schema.sh infra/clickhouse/sql/005_lead_scoring.sql

smoke-test-phase10:
	docker compose exec -T clickhouse clickhouse-client --user "$${CLICKHOUSE_USER:-analytics}" --password "$${CLICKHOUSE_PASSWORD:-analytics_password}" --multiquery < scripts/smoke_phase10.sql

schema-phase11:
	bash scripts/apply-schema.sh infra/clickhouse/sql/006_ml_scores.sql

smoke-test-phase11:
	docker compose exec -T clickhouse clickhouse-client --user "$${CLICKHOUSE_USER:-analytics}" --password "$${CLICKHOUSE_PASSWORD:-analytics_password}" --multiquery < scripts/smoke_phase11.sql

ML_VENV ?= .venv-ml

ifeq ($(OS),Windows_NT)
    ML_PYTHON ?= $(ML_VENV)/Scripts/python
else
    ML_PYTHON ?= $(ML_VENV)/bin/python
endif

ml-setup:
	python -m venv $(ML_VENV)
	$(ML_PYTHON) -m pip install --upgrade pip
	$(ML_PYTHON) -m pip install -r requirements-ml.txt

score-sessions:
	$(ML_PYTHON) scripts/score_sessions.py

retailrocket-setup:
	$(PYTHON3) -m venv $(RETAILROCKET_VENV)
	$(RETAILROCKET_PYTHON) -m pip install --upgrade pip
	$(RETAILROCKET_PYTHON) -m pip install kaggle -r scripts/retailrocket/requirements.txt

retailrocket-download:
	PATH="$(PWD)/$(RETAILROCKET_VENV)/bin:$$PATH" bash scripts/download_retailrocket.sh

retailrocket-import:
	$(RETAILROCKET_PYTHON) scripts/retailrocket/import.py

retailrocket-smoke:
	docker compose exec -T clickhouse clickhouse-client --user "$${CLICKHOUSE_USER:-analytics}" --password "$${CLICKHOUSE_PASSWORD:-analytics_password}" --multiquery < scripts/retailrocket/smoke.sql

retailrocket-reload: schema-retailrocket retailrocket-import retailrocket-smoke

# ---------------------------------------------------------------------------
# Phase 13 — CTGAN Behavioral Simulator
# ---------------------------------------------------------------------------

SYNTH_VENV ?= .venv-synth
N_SESSIONS ?= 10000

# Detect Windows vs Unix for venv binary paths.
ifeq ($(OS),Windows_NT)
    SYNTH_PYTHON ?= $(SYNTH_VENV)/Scripts/python
    SYNTH_PIP    ?= $(SYNTH_VENV)/Scripts/pip
    PYTHON3      ?= python
else
    SYNTH_PYTHON ?= $(SYNTH_VENV)/bin/python
    SYNTH_PIP    ?= $(SYNTH_VENV)/bin/pip
    PYTHON3      ?= python3
endif

synth-setup:
	$(PYTHON3) -m venv $(SYNTH_VENV)
	$(SYNTH_PYTHON) -m pip install --upgrade pip
	$(SYNTH_PYTHON) -m pip install -r requirements-synth.txt
	$(SYNTH_PYTHON) -m ipykernel install --user --name=synth --display-name="Python 3 (synth)"

schema-phase13:
	bash scripts/apply-schema.sh infra/clickhouse/sql/007_synthetic_sessions.sql

smoke-test-phase13:
	docker compose exec -T clickhouse clickhouse-client \
	  --user "$${CLICKHOUSE_USER:-analytics}" \
	  --password "$${CLICKHOUSE_PASSWORD:-analytics_password}" \
	  --query "SELECT count() AS synthetic_sessions FROM analytics.synthetic_sessions"

ctgan-train:
	$(SYNTH_PYTHON) -m nbconvert --to notebook --execute \
	  --ExecutePreprocessor.timeout=10800 \
	  --ExecutePreprocessor.kernel_name=python3 \
	  --output ctgan_trainer_executed \
	  --output-dir notebooks \
	  notebooks/ctgan_trainer.ipynb

generate-synthetic:
	$(SYNTH_PYTHON) scripts/generate_synthetic_sessions.py \
	  --n-sessions $(N_SESSIONS) \
	  --overwrite

# ---------------------------------------------------------------------------
# Phase 14 — Simulation Engine
# ---------------------------------------------------------------------------

SIM_VENV    ?= .venv-sim
N_AGENTS    ?= 1000
DURATION    ?= 60
SEED        ?= 42
AGENT_MIX   ?= browser:0.6,buyer:0.3,abandoner:0.1

ifeq ($(OS),Windows_NT)
    SIM_PYTHON ?= $(SIM_VENV)/Scripts/python
else
    SIM_PYTHON ?= $(SIM_VENV)/bin/python
endif

sim-setup:
	$(PYTHON3) -m venv $(SIM_VENV)
	$(SIM_PYTHON) -m pip install --upgrade pip
	$(SIM_PYTHON) -m pip install -r requirements-sim.txt

simulate:
	$(SIM_PYTHON) scripts/run_simulation.py \
	  --n-agents $(N_AGENTS) \
	  --duration-minutes $(DURATION) \
	  --seed $(SEED) \
	  --agent-mix "$(AGENT_MIX)"

smoke-test-sim:
	$(SIM_PYTHON) scripts/run_simulation.py \
	  --n-agents 100 \
	  --duration-minutes 10 \
	  --seed 0 \
	  --dry-run

# ---------------------------------------------------------------------------
# Phase 15 — Lead Profiling & LLM Context Builder
# ---------------------------------------------------------------------------

AI_VENV ?= .venv-ai

ifeq ($(OS),Windows_NT)
    AI_PYTHON ?= $(AI_VENV)/Scripts/python
else
    AI_PYTHON ?= $(AI_VENV)/bin/python
endif

ai-setup:
	$(PYTHON3) -m venv $(AI_VENV)
	$(AI_PYTHON) -m pip install --upgrade pip
	$(AI_PYTHON) -m pip install -r requirements-ai.txt

schema-ai:
	bash scripts/apply-schema.sh infra/clickhouse/sql/008_ai_script_log.sql

test-ai:
	$(AI_PYTHON) -m pytest tests/test_prompt_builder.py -v

# ---------------------------------------------------------------------------
# Phase 17 — Product Input & Lead Prediction Interface
# ---------------------------------------------------------------------------

PRODUCT     ?= "Wireless Headphones"
CATEGORY    ?= 1051
PRICE       ?= 49.99
KEYWORDS    ?= audio,bluetooth
N_PREDICT   ?= 1000
MODEL_PATH  ?= models/ctgan_sessions.pkl

schema-phase17:
	bash scripts/apply-schema.sh infra/clickhouse/sql/009_prediction_log.sql

predict-product:
	$(SYNTH_PYTHON) scripts/predict_product.py \
	  --product "$(PRODUCT)" \
	  --category $(CATEGORY) \
	  --price $(PRICE) \
	  --keywords "$(KEYWORDS)" \
	  --n-sessions $(N_PREDICT) \
	  --model $(MODEL_PATH)

test-predictor:
	$(SYNTH_PYTHON) -m pytest tests/test_product_predictor.py -v

# ---------------------------------------------------------------------------
# Phase 18 — Augmented Training Pipeline
# ---------------------------------------------------------------------------

VERSION ?= v2

build-augmented-dataset:
	$(ML_PYTHON) scripts/build_augmented_dataset.py \
	  --output-dir data \
	  --seed 42

train-augmented: build-augmented-dataset
	$(ML_PYTHON) -m nbconvert --to notebook --execute \
	  --ExecutePreprocessor.timeout=7200 \
	  --ExecutePreprocessor.kernel_name=python3 \
	  --output augmented_training_executed \
	  --output-dir notebooks \
	  notebooks/augmented_training.ipynb

select-model:
	$(ML_PYTHON) -c "from src.scoring.model_registry import set_active_model; set_active_model('$(VERSION)')"

test-registry:
	$(ML_PYTHON) -m pytest tests/test_model_registry.py -v

# ---------------------------------------------------------------------------
# Phase 19 — Prediction REST API Service
# ---------------------------------------------------------------------------

API_URL ?= http://localhost:8000

api-up:
	$(COMPOSE) up -d --build prediction-api

api-down:
	$(COMPOSE) stop prediction-api

api-test:
	curl -s -X POST $(API_URL)/predict/product \
	  -H "Content-Type: application/json" \
	  -d '{"product_name":"Test Product","category":"1051","price":29.99,"keywords":"test","n_sessions":200}' \
	  | python -c "import sys,json; d=json.load(sys.stdin); assert 'conversion_rate_pct' in d and 'tier_distribution' in d, d; print('API test PASSED. conversion_rate_pct='+str(d['conversion_rate_pct'])+'%')"

test-api:
	$(ML_PYTHON) -m pytest tests/test_prediction_api.py -v

# ---------------------------------------------------------------------------
# Phase 20 — ML Monitoring & CI Hardening
# ---------------------------------------------------------------------------

schema-phase20:
	bash scripts/apply-schema.sh infra/clickhouse/sql/010_drift_log.sql

check-drift:
	$(SYNTH_PYTHON) scripts/check_model_drift.py

console-up:
	$(COMPOSE) up -d redpanda-console

lint:
	ruff check src/ scripts/ tests/
