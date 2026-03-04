.PHONY: help setup run run-direct run-direct-single run-deep run-focus run-focus-deep run-single run-focus-single run-cycle run-cycle-deep run-cycle-verify run-loop run-loop-deep verify-sources e2e-install e2e-open e2e-run e2e-playwright-install e2e-service e2e-service-all e2e-service-list qa-program qa-program-loop qa-report-latest api-up api-down api-reset api-logs api-ps api-health docker-build docker-run docker-run-cycle docker-run-loop clean frontend-install frontend-dev frontend-build

PYTHON ?= python3
TOP ?= 6
WORKSPACE ?= /Users/mike/workspace/side_project/Ora
OUTPUT_DIR ?= /Users/mike/workspace/side_project/Ora/ora-automation/research_reports
OUTPUT_NAME ?= rd_research_report
MAX_FILES ?= 1500
EXTENSIONS ?= md,py,java,kt,ts,tsx,toml,yml,yaml,json,properties,xml,sh,gradle,txt
FOCUS ?=
RUN_NAME ?= V10_자동회차
VERSION_TAG ?= V10
DEBATE_ROUNDS ?= 2
ORCHESTRATION_PROFILE ?= standard
PIPELINE_STAGES ?= analysis,deliberation,execution
PIPELINE_ALLOWED_SERVICES ?= b2b,b2b-android,b2c,ai,telecom,docs
PIPELINE_SERVICES ?=
PIPELINE_FEATURES ?=
LLM_DELIBERATION_CMD ?= $(if $(shell .venv/bin/python --version 2>/dev/null),.venv/bin/python,python3) scripts/llm_round_openai.py
LLM_DELIBERATION_TIMEOUT ?= 45
LLM_CONSENSUS_CMD ?= $(if $(shell .venv/bin/python --version 2>/dev/null),.venv/bin/python,python3) scripts/llm_round_openai.py
LLM_CONSENSUS_TIMEOUT ?= 45
ORA_RD_LLM_PROVIDER ?= gemini
GOOGLE_CLOUD_PROJECT_ID ?= ora-project-474413
GOOGLE_CLOUD_LOCATION ?= asia-northeast3
GEMINI_MODEL ?= gemini-2.5-flash
MCP_GEMINI_MODEL ?= gemini-2.5-flash
EMBEDDING_LOCATION ?= asia-northeast3
GOOGLE_CLOUD_FALLBACK_LOCATIONS ?= us-central1,us-east1,europe-west1
GOOGLE_APPLICATION_CREDENTIALS ?= /Users/mike/workspace/side_project/Ora/ora-automation/google-service-account.json
ORA_RD_GEMINI_DISABLE_VERTEX ?= 0
PIPELINE_EXECUTION_COMMAND ?=
PIPELINE_ROLLBACK_COMMAND ?=
PIPELINE_RETRY_MAX ?= 2
PIPELINE_RETRY_DELAY ?= 1.2
PIPELINE_FAIL_DEFAULT ?= RETRY
RUN_MAX_FILES ?= 1500
RUN_EXTENSIONS ?= md,py,java,kt,ts,tsx,toml,yml,yaml,json,properties,xml,sh,gradle,txt
RUN_EXTENSIONS_DEEP ?= md,py,java,kt,ts,tsx,toml,yml,yaml,json,properties,xml,sh,gradle,txt,ini,cfg,swift
KEEP_LAST_RUNS ?= 12
PERSIST_CYCLE_ARTIFACTS ?= 0
HISTORY_MAX_FILES ?= 12
VERIFY_SCOPE ?= recent
VERIFY_MAX_FILES ?= 6
RUN_CYCLES ?= 1
VERIFY_ROUNDS ?= 3
VERIFY_TIMEOUT ?= 8
VERIFY_RETRY_DELAY ?= 1.2
ORA_RD_RESEARCH_ARXIV_SEARCH ?= 1
ORA_RD_RESEARCH_CROSSREF_SEARCH ?= 1
ORA_RD_RESEARCH_OPENALEX_SEARCH ?= 1
ORA_RD_RESEARCH_SEARCH_TIMEOUT ?= 8
ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS ?= 6
ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS ?= 6
ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS ?= 6
ORA_RD_RESEARCH_CROSSREF_SEARCH_TIMEOUT ?= 8
ORA_RD_RESEARCH_OPENALEX_SEARCH_TIMEOUT ?= 8
# Backward-compatible aliases
ORA_RD_ARXIV_SEARCH_ENABLED ?= $(ORA_RD_RESEARCH_ARXIV_SEARCH)
ORA_RD_ARXIV_SEARCH_MAX_RESULTS ?= $(ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS)
ORA_RD_ARXIV_SEARCH_TIMEOUT ?= $(ORA_RD_RESEARCH_SEARCH_TIMEOUT)
ORA_RD_CROSSREF_SEARCH_TIMEOUT ?= $(ORA_RD_RESEARCH_CROSSREF_SEARCH_TIMEOUT)
ORA_RD_OPENALEX_SEARCH_TIMEOUT ?= $(ORA_RD_RESEARCH_OPENALEX_SEARCH_TIMEOUT)
VERIFY_SOURCE_FILES ?= /Users/mike/workspace/side_project/Ora/ora-automation/research_reports/V9_대화흐름혁신_업무자동화_신뢰성강화/research_sources.json
DOCKER_IMAGE ?= ora-automation:local
DOCKER_HOST_WORKSPACE ?= /Users/mike/workspace/side_project/Ora
DOCKER_OUTPUT_DIR ?= /workspace/Ora/ora-automation/research_reports/runs/docker
DOCKER_OUTPUT_HOST_DIR ?= $(DOCKER_HOST_WORKSPACE)/ora-automation/research_reports/runs/docker
DOCKERFILE ?= Dockerfile
COMPOSE ?= docker compose
API_BASE_URL ?= http://localhost:8000
DOCKER_MAKE_COMMON_ARGS = TOP="$(TOP)" FOCUS="$(FOCUS)" VERSION_TAG="$(VERSION_TAG)" DEBATE_ROUNDS="$(DEBATE_ROUNDS)" ORCHESTRATION_PROFILE="$(ORCHESTRATION_PROFILE)" PIPELINE_STAGES="$(PIPELINE_STAGES)" PIPELINE_ALLOWED_SERVICES="$(PIPELINE_ALLOWED_SERVICES)" PIPELINE_SERVICES="$(PIPELINE_SERVICES)" PIPELINE_FEATURES="$(PIPELINE_FEATURES)" LLM_DELIBERATION_CMD="$(LLM_DELIBERATION_CMD)" LLM_DELIBERATION_TIMEOUT="$(LLM_DELIBERATION_TIMEOUT)" LLM_CONSENSUS_CMD="$(LLM_CONSENSUS_CMD)" LLM_CONSENSUS_TIMEOUT="$(LLM_CONSENSUS_TIMEOUT)" PIPELINE_EXECUTION_COMMAND="$(PIPELINE_EXECUTION_COMMAND)" PIPELINE_ROLLBACK_COMMAND="$(PIPELINE_ROLLBACK_COMMAND)" PIPELINE_RETRY_MAX="$(PIPELINE_RETRY_MAX)" PIPELINE_RETRY_DELAY="$(PIPELINE_RETRY_DELAY)" PIPELINE_FAIL_DEFAULT="$(PIPELINE_FAIL_DEFAULT)" MAX_FILES="$(MAX_FILES)" EXTENSIONS="$(EXTENSIONS)" OUTPUT_NAME="$(OUTPUT_NAME)" ORA_RD_RESEARCH_ARXIV_SEARCH="$(ORA_RD_RESEARCH_ARXIV_SEARCH)" ORA_RD_RESEARCH_CROSSREF_SEARCH="$(ORA_RD_RESEARCH_CROSSREF_SEARCH)" ORA_RD_RESEARCH_OPENALEX_SEARCH="$(ORA_RD_RESEARCH_OPENALEX_SEARCH)" ORA_RD_RESEARCH_SEARCH_TIMEOUT="$(ORA_RD_RESEARCH_SEARCH_TIMEOUT)" ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS="$(ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS)" ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS="$(ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS)" ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS="$(ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS)" ORA_RD_RESEARCH_CROSSREF_SEARCH_TIMEOUT="$(ORA_RD_RESEARCH_CROSSREF_SEARCH_TIMEOUT)" ORA_RD_RESEARCH_OPENALEX_SEARCH_TIMEOUT="$(ORA_RD_RESEARCH_OPENALEX_SEARCH_TIMEOUT)" ORA_RD_ARXIV_SEARCH_ENABLED="$(ORA_RD_ARXIV_SEARCH_ENABLED)" ORA_RD_ARXIV_SEARCH_MAX_RESULTS="$(ORA_RD_ARXIV_SEARCH_MAX_RESULTS)" ORA_RD_ARXIV_SEARCH_TIMEOUT="$(ORA_RD_ARXIV_SEARCH_TIMEOUT)" ORA_RD_CROSSREF_SEARCH_TIMEOUT="$(ORA_RD_CROSSREF_SEARCH_TIMEOUT)" ORA_RD_OPENALEX_SEARCH_TIMEOUT="$(ORA_RD_OPENALEX_SEARCH_TIMEOUT)"


E2E_PROJECT_DIR ?= $(shell cd .. && pwd)/OraMainFrontend
E2E_PM ?= npm
E2E_MODE ?= open
E2E_BASE_URL ?=
E2E_CONFIG_FILE ?=
E2E_SPEC_FILE ?=
E2E_SERVICE ?= ai
E2E_TOOL ?= cypress
E2E_SERVICE_LIST ?= b2b b2b-android b2c ai telecom
E2E_CMD ?=
E2E_PYTEST_ARGS ?=
E2E_SERVICE_MODE ?= run
E2E_FORCE_CYPRESS ?= 0
E2E_FAIL_FAST ?= 0
QA_SERVICES ?= $(E2E_SERVICE_LIST)
QA_RETRY_MAX ?= 1
QA_RETRY_DELAY ?= 1.5
QA_FAIL_FAST ?= $(E2E_FAIL_FAST)
QA_OUTPUT_ROOT ?= $(OUTPUT_DIR)/qa_runs
QA_RUN_NAME ?=
QA_LOOP_CYCLES ?= 1

help:
	@echo "make setup                    : venv 생성 + 패키지 설치(-e .)."
	@echo "make run-deep                      : 확장 설정으로 1회 분석 실행."
	@echo "make run-single                    : TOP=1로 한 전략만 1회 출력."
	@echo "make run-focus FOCUS=<label>        : 포커스 라벨로 1회 분석 실행."
	@echo "make run                           : 기본 스캔 실행(현재 폴더 기준)."
	@echo "make run-cycle                     : 기본 runner 실행(V10_자동회차)."
	@echo "make run-cycle-deep                 : 깊은 설정으로 runner 실행."
	@echo "make run-loop                 : run-cycle 여러 번 반복(변화 관찰)."
	@echo "DEBATE_ROUNDS=<N> : 에이전트 토론 라운드 수(기본 2, 라운드별 수렴 판정 시 조기 종료될 수 있음)."
	@echo "make run-loop-deep                  : run-cycle-deep 반복."
	@echo "make run-cycle-verify          : runner 실행 후 research_sources.json 검증(run-cycle와 동일)."
	@echo "make run-focus-deep                 : 포커스 라벨 + deep 설정 1회 실행."
	@echo "ORCHESTRATION_PROFILE=<standard|strict> : 오케스트레이션 프로필"
	@echo "PIPELINE_STAGES=analysis,deliberation,execution : 단계 구성"
	@echo "PIPELINE_SERVICES=b2c,ai ... : 서비스 스코프 지정"
	@echo "LLM_DELIBERATION_CMD='<cmd>' : LLM 토론 커맨드(JSON in/out)"
	@echo "PIPELINE_EXECUTION_COMMAND='<cmd>' : execution stage 실제 실행 커맨드"
	@echo "PIPELINE_ROLLBACK_COMMAND='<cmd>'  : execution 실패 시 롤백 커맨드"
	@echo "make verify-sources                : 지정한 소스 파일만 URL 검증."
	@echo "make run-direct               : venv 없이 python3 스크립트 직접 실행."
	@echo "make clean                    : 임시 실행 결과 정리."
	@echo ""
	@echo "FastAPI + Postgres + RabbitMQ (Docker Compose)"
	@echo "make api-up                   : API + DB + RabbitMQ + 5개 역할 워커 기동"
	@echo "make api-down                 : API/DB/RabbitMQ/워커 중지"
	@echo "make api-reset                : 전체 중지 + DB 볼륨 삭제"
	@echo "make api-ps                   : Compose 상태 확인"
	@echo "make api-logs                 : API/DB 로그 팔로우"
	@echo "make api-health               : API 헬스체크 호출"
	@echo ""
	@echo "Docker 실행"
	@echo "make docker-build                    : ora-automation 도커 이미지 빌드"
	@echo "make docker-run                      : 도커에서 1회 분석(run-direct) 실행"
	@echo "make docker-run-cycle                : 도커에서 run-cycle 실행"
	@echo "make docker-run-loop                 : 도커에서 run-loop 실행"
	@echo ""
	@echo "E2E(Cypress/Playwright)"
	@echo "make e2e-install             : 지정 프로젝트에서 cypress 설치(npm/pnpm/yarn)"
	@echo "make e2e-playwright-install  : 지정 프로젝트에서 Playwright 설치(npm/pnpm/yarn)"
	@echo "make e2e-open E2E_PROJECT_DIR=<front 폴더>     : npm install 후 npx cypress open 실행."
	@echo "make e2e-run E2E_PROJECT_DIR=<front 폴더>      : npm install 후 npx cypress run 실행."
	@echo "make e2e-open E2E_TOOL=playwright : npx playwright test --ui 실행"
	@echo "make e2e-run E2E_TOOL=playwright  : npx playwright test 실행"
	@echo "make e2e-service SERVICE=<b2b|b2b-android|android|b2c|ai|telecom> : 서비스별 E2E 실행."
	@echo "make e2e-service-all                                   : 기본 슬롯(E2E_SERVICE_LIST) 순차 실행."
	@echo "make e2e-service-all E2E_FAIL_FAST=1                   : 실패 시 즉시 종료."
	@echo "make e2e-service-list                          : 서비스별 E2E 지원 목록 출력."
	@echo "make qa-program                                   : 서비스별 E2E + md/json 리포트 생성."
	@echo "make qa-program QA_SERVICES='b2c ai'              : 특정 서비스만 QA 실행."
	@echo "make qa-program-loop QA_LOOP_CYCLES=3             : QA 파이프라인 반복 실행."
	@echo "make qa-report-latest                              : 최신 QA md 리포트 경로 출력."
	@echo ""
	@echo "예시) make e2e-open E2E_PROJECT_DIR=/Users/mike/workspace/side_project/Ora/OraWebAppFrontend E2E_PM=npm E2E_BASE_URL=http://localhost:3000"

setup:
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -e .

run:
	@if [ -x ".venv/bin/python" ]; then \
		PYTHON_BIN=".venv/bin/python"; \
	else \
		PYTHON_BIN="$(PYTHON)"; \
	fi; \
	mkdir -p $(OUTPUT_DIR)/runs; \
	ORA_RD_RESEARCH_ARXIV_SEARCH=$(ORA_RD_RESEARCH_ARXIV_SEARCH) \
	ORA_RD_RESEARCH_CROSSREF_SEARCH=$(ORA_RD_RESEARCH_CROSSREF_SEARCH) \
	ORA_RD_RESEARCH_OPENALEX_SEARCH=$(ORA_RD_RESEARCH_OPENALEX_SEARCH) \
	ORA_RD_RESEARCH_SEARCH_TIMEOUT=$(ORA_RD_RESEARCH_SEARCH_TIMEOUT) \
	ORA_RD_ARXIV_SEARCH_ENABLED=$(ORA_RD_ARXIV_SEARCH_ENABLED) \
	ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS=$(ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS) \
	ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS=$(ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS) \
	ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS=$(ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS) \
	ORA_RD_CROSSREF_SEARCH_TIMEOUT=$(ORA_RD_CROSSREF_SEARCH_TIMEOUT) \
	ORA_RD_OPENALEX_SEARCH_TIMEOUT=$(ORA_RD_OPENALEX_SEARCH_TIMEOUT) \
	ORA_RD_LLM_PROVIDER=$(ORA_RD_LLM_PROVIDER) \
	ORA_RD_GEMINI_DISABLE_VERTEX=$(ORA_RD_GEMINI_DISABLE_VERTEX) \
	GOOGLE_CLOUD_PROJECT_ID=$(GOOGLE_CLOUD_PROJECT_ID) \
	GOOGLE_CLOUD_LOCATION=$(GOOGLE_CLOUD_LOCATION) \
	GEMINI_MODEL=$(GEMINI_MODEL) \
	MCP_GEMINI_MODEL=$(MCP_GEMINI_MODEL) \
	EMBEDDING_LOCATION=$(EMBEDDING_LOCATION) \
	GOOGLE_CLOUD_FALLBACK_LOCATIONS=$(GOOGLE_CLOUD_FALLBACK_LOCATIONS) \
	GOOGLE_APPLICATION_CREDENTIALS=$(GOOGLE_APPLICATION_CREDENTIALS) \
	PYTHONPATH="$(shell pwd)/src" "$$PYTHON_BIN" -m ora_rd_orchestrator.cli \
		--workspace $(WORKSPACE) \
		--output-dir $(OUTPUT_DIR)/runs \
		--output-name $(OUTPUT_NAME) \
		--top $(TOP) \
		--max-files $(MAX_FILES) \
		--extensions $(EXTENSIONS) \
		--focus "$(FOCUS)" \
		--version-tag $(VERSION_TAG) \
		--debate-rounds $(DEBATE_ROUNDS) \
		--orchestration-profile $(ORCHESTRATION_PROFILE) \
		--orchestration-stages "$(PIPELINE_STAGES)" \
		--service-scope "$(if $(strip $(PIPELINE_SERVICES)),$(PIPELINE_SERVICES),$(PIPELINE_ALLOWED_SERVICES))" \
		--feature-scope "$(PIPELINE_FEATURES)" \
		--llm-deliberation-timeout $(LLM_DELIBERATION_TIMEOUT) \
		--llm-consensus-timeout $(LLM_CONSENSUS_TIMEOUT) \
		--llm-deliberation-cmd "$(LLM_DELIBERATION_CMD)" \
		--llm-consensus-cmd "$(LLM_CONSENSUS_CMD)"

run-deep:
	@$(MAKE) run \
		TOP=8 \
		MAX_FILES=2400 \
		EXTENSIONS=$(RUN_EXTENSIONS_DEEP) \
		RUN_MAX_FILES=2400 \
		RUN_EXTENSIONS=$(RUN_EXTENSIONS_DEEP)

run-focus:
	@$(MAKE) run TOP=8 FOCUS="$(FOCUS)" VERSION_TAG="$(VERSION_TAG)"

run-single:
	@$(MAKE) run TOP=1 FOCUS="$(FOCUS)" VERSION_TAG="$(VERSION_TAG)"

run-focus-single:
	@$(MAKE) run-single FOCUS="$(FOCUS)" VERSION_TAG="$(VERSION_TAG)"

run-direct:
	mkdir -p $(OUTPUT_DIR)/runs
	ORA_RD_RESEARCH_ARXIV_SEARCH=$(ORA_RD_RESEARCH_ARXIV_SEARCH) \
	ORA_RD_RESEARCH_CROSSREF_SEARCH=$(ORA_RD_RESEARCH_CROSSREF_SEARCH) \
	ORA_RD_RESEARCH_OPENALEX_SEARCH=$(ORA_RD_RESEARCH_OPENALEX_SEARCH) \
	ORA_RD_RESEARCH_SEARCH_TIMEOUT=$(ORA_RD_RESEARCH_SEARCH_TIMEOUT) \
	ORA_RD_ARXIV_SEARCH_ENABLED=$(ORA_RD_ARXIV_SEARCH_ENABLED) \
	ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS=$(ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS) \
	ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS=$(ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS) \
	ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS=$(ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS) \
	ORA_RD_CROSSREF_SEARCH_TIMEOUT=$(ORA_RD_CROSSREF_SEARCH_TIMEOUT) \
	ORA_RD_OPENALEX_SEARCH_TIMEOUT=$(ORA_RD_OPENALEX_SEARCH_TIMEOUT) \
	PYTHONPATH="$(shell pwd)/src" $(PYTHON) -m ora_rd_orchestrator.cli \
		--workspace $(WORKSPACE) \
		--output-dir $(OUTPUT_DIR)/runs \
		--output-name $(OUTPUT_NAME) \
		--top $(TOP) \
		--max-files $(MAX_FILES) \
		--extensions $(EXTENSIONS) \
		--focus "$(FOCUS)" \
		--version-tag $(VERSION_TAG) \
		--debate-rounds $(DEBATE_ROUNDS) \
		--orchestration-profile $(ORCHESTRATION_PROFILE) \
		--orchestration-stages "$(PIPELINE_STAGES)" \
		--service-scope "$(if $(strip $(PIPELINE_SERVICES)),$(PIPELINE_SERVICES),$(PIPELINE_ALLOWED_SERVICES))" \
		--feature-scope "$(PIPELINE_FEATURES)" \
		--llm-deliberation-timeout $(LLM_DELIBERATION_TIMEOUT) \
		--llm-consensus-timeout $(LLM_CONSENSUS_TIMEOUT) \
		--llm-deliberation-cmd "$(LLM_DELIBERATION_CMD)" \
		--llm-consensus-cmd "$(LLM_CONSENSUS_CMD)"

run-direct-single:
	@$(MAKE) run-direct TOP=1 FOCUS="$(FOCUS)" VERSION_TAG="$(VERSION_TAG)" DEBATE_ROUNDS="$(DEBATE_ROUNDS)"

run-focus-deep:
	@$(MAKE) run-focus \
		TOP=10 \
		MAX_FILES=3600 \
		EXTENSIONS=$(RUN_EXTENSIONS_DEEP)

run-cycle:
	PYTHON_BIN=$(if $(wildcard .venv/bin/python),.venv/bin/python,$(PYTHON)) \
	TOP=$(TOP) \
	RUN_NAME=$(RUN_NAME) \
	FOCUS="$(FOCUS)" \
	VERSION_TAG=$(VERSION_TAG) \
	DEBATE_ROUNDS=$(DEBATE_ROUNDS) \
	ORCHESTRATION_PROFILE=$(ORCHESTRATION_PROFILE) \
	PIPELINE_STAGES="$(PIPELINE_STAGES)" \
	PIPELINE_ALLOWED_SERVICES="$(PIPELINE_ALLOWED_SERVICES)" \
	PIPELINE_SERVICES="$(PIPELINE_SERVICES)" \
	PIPELINE_FEATURES="$(PIPELINE_FEATURES)" \
	LLM_DELIBERATION_CMD='$(LLM_DELIBERATION_CMD)' \
	LLM_DELIBERATION_TIMEOUT=$(LLM_DELIBERATION_TIMEOUT) \
	LLM_CONSENSUS_CMD='$(LLM_CONSENSUS_CMD)' \
	LLM_CONSENSUS_TIMEOUT=$(LLM_CONSENSUS_TIMEOUT) \
	ORA_RD_LLM_PROVIDER=$(ORA_RD_LLM_PROVIDER) \
	ORA_RD_GEMINI_DISABLE_VERTEX=$(ORA_RD_GEMINI_DISABLE_VERTEX) \
	GOOGLE_CLOUD_PROJECT_ID=$(GOOGLE_CLOUD_PROJECT_ID) \
	GOOGLE_CLOUD_LOCATION=$(GOOGLE_CLOUD_LOCATION) \
	GEMINI_MODEL=$(GEMINI_MODEL) \
	MCP_GEMINI_MODEL=$(MCP_GEMINI_MODEL) \
	EMBEDDING_LOCATION=$(EMBEDDING_LOCATION) \
	GOOGLE_CLOUD_FALLBACK_LOCATIONS=$(GOOGLE_CLOUD_FALLBACK_LOCATIONS) \
	GOOGLE_APPLICATION_CREDENTIALS=$(GOOGLE_APPLICATION_CREDENTIALS) \
	PIPELINE_EXECUTION_COMMAND='$(PIPELINE_EXECUTION_COMMAND)' \
	PIPELINE_ROLLBACK_COMMAND='$(PIPELINE_ROLLBACK_COMMAND)' \
	PIPELINE_RETRY_MAX=$(PIPELINE_RETRY_MAX) \
	PIPELINE_RETRY_DELAY=$(PIPELINE_RETRY_DELAY) \
	PIPELINE_FAIL_DEFAULT=$(PIPELINE_FAIL_DEFAULT) \
	ORA_RD_ARXIV_SEARCH_ENABLED=$(ORA_RD_ARXIV_SEARCH_ENABLED) \
	ORA_RD_RESEARCH_ARXIV_SEARCH=$(ORA_RD_RESEARCH_ARXIV_SEARCH) \
	ORA_RD_RESEARCH_CROSSREF_SEARCH=$(ORA_RD_RESEARCH_CROSSREF_SEARCH) \
	ORA_RD_RESEARCH_OPENALEX_SEARCH=$(ORA_RD_RESEARCH_OPENALEX_SEARCH) \
	ORA_RD_RESEARCH_SEARCH_TIMEOUT=$(ORA_RD_RESEARCH_SEARCH_TIMEOUT) \
	ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS=$(ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS) \
	ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS=$(ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS) \
	ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS=$(ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS) \
	ORA_RD_CROSSREF_SEARCH_TIMEOUT=$(ORA_RD_CROSSREF_SEARCH_TIMEOUT) \
	ORA_RD_OPENALEX_SEARCH_TIMEOUT=$(ORA_RD_OPENALEX_SEARCH_TIMEOUT) \
	RUN_MAX_FILES=$(RUN_MAX_FILES) \
	RUN_EXTENSIONS=$(RUN_EXTENSIONS) \
	VERIFY_SCOPE=$(VERIFY_SCOPE) \
	VERIFY_MAX_FILES=$(VERIFY_MAX_FILES) \
	HISTORY_MAX_FILES=$(HISTORY_MAX_FILES) \
	KEEP_LAST_RUNS=$(KEEP_LAST_RUNS) \
	PERSIST_CYCLE_ARTIFACTS=$(PERSIST_CYCLE_ARTIFACTS) \
	RUN_CYCLES=$(RUN_CYCLES) \
	VERIFY_ROUNDS=$(VERIFY_ROUNDS) \
	VERIFY_TIMEOUT=$(VERIFY_TIMEOUT) \
	VERIFY_RETRY_DELAY=$(VERIFY_RETRY_DELAY) \
	bash scripts/run_collaboration_cycle.sh

run-cycle-deep:
	@$(MAKE) run-cycle \
		TOP=10 \
		RUN_CYCLES=$(RUN_CYCLES) \
		RUN_MAX_FILES=2400 \
		RUN_EXTENSIONS="$(RUN_EXTENSIONS_DEEP)" \
		VERIFY_ROUNDS=5 \
		VERIFY_SCOPE=recent \
		VERIFY_MAX_FILES=12 \
		KEEP_LAST_RUNS=8 \
		HISTORY_MAX_FILES=6

run-cycle-verify:
	$(MAKE) run-cycle

run-loop:
	$(MAKE) run-cycle

run-loop-deep:
	$(MAKE) run-cycle-deep

verify-sources:
	@if [ -z "$(strip $(VERIFY_SOURCE_FILES))" ]; then \
		echo "[error] VERIFY_SOURCE_FILES가 비어있습니다.\n\t  예: make verify-sources VERIFY_SOURCE_FILES='path/to/research_sources.json'"; \
		exit 1; \
	fi
	@for source_file in $(VERIFY_SOURCE_FILES); do \
		$(PYTHON) scripts/verify_sources.py \
			--in-place \
			--source "$${source_file}" \
			--rounds $(VERIFY_ROUNDS) \
			--timeout $(VERIFY_TIMEOUT) \
			--retry-delay $(VERIFY_RETRY_DELAY); \
	done

clean:
	rm -rf $(OUTPUT_DIR)/$(RUN_NAME)
	rm -rf $(OUTPUT_DIR)/runs

api-up:
	$(COMPOSE) up -d --build

api-down:
	$(COMPOSE) down

api-reset:
	$(COMPOSE) down -v

api-logs:
	$(COMPOSE) logs -f api db rabbitmq worker-ceo worker-pm worker-researcher worker-engineer worker-qa

api-ps:
	$(COMPOSE) ps

api-health:
	curl -sS $(API_BASE_URL)/health

docker-build:
	docker build --file $(DOCKERFILE) --tag $(DOCKER_IMAGE) .

docker-run:
	mkdir -p $(DOCKER_OUTPUT_HOST_DIR)
	docker run --rm \
		-v $(DOCKER_HOST_WORKSPACE):/workspace/Ora \
		-v $(DOCKER_OUTPUT_HOST_DIR):$(DOCKER_OUTPUT_DIR) \
		-e WORKSPACE=/workspace/Ora \
		-e OUTPUT_DIR=$(DOCKER_OUTPUT_DIR) \
		$(DOCKER_IMAGE) \
		make run-direct $(DOCKER_MAKE_COMMON_ARGS)

docker-run-cycle:
	mkdir -p $(DOCKER_OUTPUT_HOST_DIR)
	docker run --rm \
		-v $(DOCKER_HOST_WORKSPACE):/workspace/Ora \
		-v $(DOCKER_OUTPUT_HOST_DIR):$(DOCKER_OUTPUT_DIR) \
		-e WORKSPACE=/workspace/Ora \
		-e OUTPUT_DIR=$(DOCKER_OUTPUT_DIR) \
		-e RUN_CYCLES=$(RUN_CYCLES) \
		-e VERIFY_ROUNDS=$(VERIFY_ROUNDS) \
		-e VERIFY_TIMEOUT=$(VERIFY_TIMEOUT) \
		-e VERIFY_RETRY_DELAY=$(VERIFY_RETRY_DELAY) \
		-e VERIFY_SCOPE=$(VERIFY_SCOPE) \
		-e VERIFY_MAX_FILES=$(VERIFY_MAX_FILES) \
		-e KEEP_LAST_RUNS=$(KEEP_LAST_RUNS) \
		-e HISTORY_MAX_FILES=$(HISTORY_MAX_FILES) \
		$(DOCKER_IMAGE) \
		bash -lc "make run-cycle TOP='$(TOP)' FOCUS='$(FOCUS)' VERSION_TAG='$(VERSION_TAG)' RUN_MAX_FILES='$(RUN_MAX_FILES)' RUN_EXTENSIONS='$(RUN_EXTENSIONS)' RUN_CYCLES='$(RUN_CYCLES)' DEBATE_ROUNDS='$(DEBATE_ROUNDS)' ORCHESTRATION_PROFILE='$(ORCHESTRATION_PROFILE)' PIPELINE_STAGES='$(PIPELINE_STAGES)' PIPELINE_ALLOWED_SERVICES='$(PIPELINE_ALLOWED_SERVICES)' PIPELINE_SERVICES='$(PIPELINE_SERVICES)' PIPELINE_FEATURES='$(PIPELINE_FEATURES)' LLM_DELIBERATION_CMD='$(LLM_DELIBERATION_CMD)' LLM_DELIBERATION_TIMEOUT='$(LLM_DELIBERATION_TIMEOUT)' LLM_CONSENSUS_CMD='$(LLM_CONSENSUS_CMD)' LLM_CONSENSUS_TIMEOUT='$(LLM_CONSENSUS_TIMEOUT)' PIPELINE_EXECUTION_COMMAND='$(PIPELINE_EXECUTION_COMMAND)' PIPELINE_ROLLBACK_COMMAND='$(PIPELINE_ROLLBACK_COMMAND)' PIPELINE_RETRY_MAX='$(PIPELINE_RETRY_MAX)' PIPELINE_RETRY_DELAY='$(PIPELINE_RETRY_DELAY)' PIPELINE_FAIL_DEFAULT='$(PIPELINE_FAIL_DEFAULT)' VERIFY_ROUNDS='$(VERIFY_ROUNDS)' VERIFY_TIMEOUT='$(VERIFY_TIMEOUT)' VERIFY_RETRY_DELAY='$(VERIFY_RETRY_DELAY)' VERIFY_SCOPE='$(VERIFY_SCOPE)' VERIFY_MAX_FILES='$(VERIFY_MAX_FILES)' KEEP_LAST_RUNS='$(KEEP_LAST_RUNS)' HISTORY_MAX_FILES='$(HISTORY_MAX_FILES)' ORA_RD_RESEARCH_ARXIV_SEARCH='$(ORA_RD_RESEARCH_ARXIV_SEARCH)' ORA_RD_RESEARCH_CROSSREF_SEARCH='$(ORA_RD_RESEARCH_CROSSREF_SEARCH)' ORA_RD_RESEARCH_OPENALEX_SEARCH='$(ORA_RD_RESEARCH_OPENALEX_SEARCH)' ORA_RD_RESEARCH_SEARCH_TIMEOUT='$(ORA_RD_RESEARCH_SEARCH_TIMEOUT)' ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS='$(ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS)' ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS='$(ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS)' ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS='$(ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS)' ORA_RD_RESEARCH_CROSSREF_SEARCH_TIMEOUT='$(ORA_RD_RESEARCH_CROSSREF_SEARCH_TIMEOUT)' ORA_RD_RESEARCH_OPENALEX_SEARCH_TIMEOUT='$(ORA_RD_RESEARCH_OPENALEX_SEARCH_TIMEOUT)' ORA_RD_ARXIV_SEARCH_ENABLED='$(ORA_RD_ARXIV_SEARCH_ENABLED)' ORA_RD_ARXIV_SEARCH_MAX_RESULTS='$(ORA_RD_ARXIV_SEARCH_MAX_RESULTS)' ORA_RD_ARXIV_SEARCH_TIMEOUT='$(ORA_RD_ARXIV_SEARCH_TIMEOUT)' ORA_RD_CROSSREF_SEARCH_TIMEOUT='$(ORA_RD_CROSSREF_SEARCH_TIMEOUT)' ORA_RD_OPENALEX_SEARCH_TIMEOUT='$(ORA_RD_OPENALEX_SEARCH_TIMEOUT)'"

docker-run-loop:
	$(MAKE) docker-run-cycle RUN_CYCLES=$(RUN_CYCLES)

e2e-install:
	@E2E_PROJECT_DIR='$(E2E_PROJECT_DIR)' \
	E2E_PM='$(E2E_PM)' \
	E2E_TOOL='$(E2E_TOOL)' \
	E2E_MODE=install \
	bash scripts/run_e2e_cypress.sh

e2e-playwright-install:
	@E2E_PROJECT_DIR='$(E2E_PROJECT_DIR)' \
	E2E_PM='$(E2E_PM)' \
	E2E_TOOL=playwright \
	E2E_MODE=install \
	bash scripts/run_e2e_playwright.sh

e2e-open:
	@E2E_PROJECT_DIR='$(E2E_PROJECT_DIR)' \
	E2E_PM='$(E2E_PM)' \
	E2E_TOOL='$(E2E_TOOL)' \
	E2E_MODE=open \
	E2E_BASE_URL='$(E2E_BASE_URL)' \
	E2E_CONFIG_FILE='$(E2E_CONFIG_FILE)' \
	E2E_SPEC_FILE='$(E2E_SPEC_FILE)' \
	if [ "$(E2E_TOOL)" = "playwright" ]; then \
		bash scripts/run_e2e_playwright.sh; \
	else \
		bash scripts/run_e2e_cypress.sh; \
	fi

e2e-run:
	@E2E_PROJECT_DIR='$(E2E_PROJECT_DIR)' \
	E2E_PM='$(E2E_PM)' \
	E2E_TOOL='$(E2E_TOOL)' \
	E2E_MODE=run \
	E2E_BASE_URL='$(E2E_BASE_URL)' \
	E2E_CONFIG_FILE='$(E2E_CONFIG_FILE)' \
	E2E_SPEC_FILE='$(E2E_SPEC_FILE)' \
	if [ "$(E2E_TOOL)" = "playwright" ]; then \
		bash scripts/run_e2e_playwright.sh; \
	else \
		bash scripts/run_e2e_cypress.sh; \
	fi

e2e-service:
	@SERVICE_NAME='$(if $(strip $(SERVICE)),$(SERVICE),$(E2E_SERVICE))'; \
	E2E_SERVICE="$$SERVICE_NAME" \
	E2E_PROJECT_DIR='$(E2E_PROJECT_DIR)' \
	E2E_PM='$(E2E_PM)' \
	E2E_MODE='$(E2E_SERVICE_MODE)' \
	E2E_BASE_URL='$(E2E_BASE_URL)' \
	E2E_CONFIG_FILE='$(E2E_CONFIG_FILE)' \
	E2E_SPEC_FILE='$(E2E_SPEC_FILE)' \
	E2E_TOOL='$(E2E_TOOL)' \
	E2E_CMD='$(E2E_CMD)' \
	E2E_PYTEST_ARGS='$(E2E_PYTEST_ARGS)' \
	E2E_FORCE_CYPRESS='$(E2E_FORCE_CYPRESS)' \
	bash scripts/run_e2e_service.sh

e2e-service-all:
	@overall=0; \
	results=""; \
	for service in $(E2E_SERVICE_LIST); do \
		echo "[e2e-service-all] service=$$service"; \
		if $(MAKE) e2e-service E2E_SERVICE=$$service; then \아
			results="$$results\n- $$service: OK"; \
		else \
			results="$$results\n- $$service: FAILED"; \
			overall=1; \
			if [ "$(E2E_FAIL_FAST)" = "1" ]; then \
				echo "⛔ e2e-service-all: 즉시 중단"; \
				echo -e "$$results"; \
				exit 1; \
			fi; \
		fi; \
	done; \
	echo "============================"; \
	echo "E2E orchestration result"; \
	echo -e "$$results"; \
	exit $$overall

e2e-service-list:
	@echo "b2b - OraB2bServer Gradle e2e test"
	@echo "b2b-android - OraB2bAndroid Android 테스트 (Gradle :app:test)"
	@echo "b2c - OraWebAppFrontend UI/서비스 회귀 테스트"
	@echo "android - OraB2bAndroid Android 테스트 (Gradle test)"
	@echo "ai - OraAiServer(LLM/TTS) Python pytest e2e 시나리오"
	@echo "telecom - OraServer 통신 서버 Gradle test"

qa-program:
	@QA_SERVICES='$(QA_SERVICES)' \
	QA_RETRY_MAX='$(QA_RETRY_MAX)' \
	QA_RETRY_DELAY='$(QA_RETRY_DELAY)' \
	QA_FAIL_FAST='$(QA_FAIL_FAST)' \
	QA_OUTPUT_ROOT='$(QA_OUTPUT_ROOT)' \
	QA_RUN_NAME='$(QA_RUN_NAME)' \
	E2E_SERVICE_MODE='$(E2E_SERVICE_MODE)' \
	E2E_TOOL='$(E2E_TOOL)' \
	E2E_PM='$(E2E_PM)' \
	E2E_BASE_URL='$(E2E_BASE_URL)' \
	E2E_CONFIG_FILE='$(E2E_CONFIG_FILE)' \
	E2E_SPEC_FILE='$(E2E_SPEC_FILE)' \
	E2E_CMD='$(E2E_CMD)' \
	E2E_PYTEST_ARGS='$(E2E_PYTEST_ARGS)' \
	E2E_FORCE_CYPRESS='$(E2E_FORCE_CYPRESS)' \
	bash scripts/run_qa_program.sh

qa-program-loop:
	@cycle=1; \
	overall=0; \
	while [ $$cycle -le $(QA_LOOP_CYCLES) ]; do \
		echo "[qa-program-loop] cycle=$$cycle/$(QA_LOOP_CYCLES)"; \
		if ! $(MAKE) qa-program QA_RUN_NAME="qa_cycle_$$(printf '%02d' $$cycle)_$$(date +%Y%m%d_%H%M%S)"; then \
			overall=1; \
			if [ "$(QA_FAIL_FAST)" = "1" ]; then \
				echo "[qa-program-loop] fail-fast stop"; \
				break; \
			fi; \
		fi; \
		cycle=$$((cycle + 1)); \
	done; \
	exit $$overall

qa-report-latest:
	@latest="$$(ls -t $(QA_OUTPUT_ROOT)/*/qa_summary.md 2>/dev/null | head -n 1 || true)"; \
	if [ -z "$$latest" ]; then \
		echo "[qa-report-latest] no qa report found under $(QA_OUTPUT_ROOT)"; \
		exit 1; \
	fi; \
	echo "$$latest"

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build
