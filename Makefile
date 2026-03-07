.PHONY: help setup verify-sources e2e-install e2e-open e2e-run e2e-playwright-install e2e-service e2e-service-all e2e-service-list qa-program qa-program-loop qa-report-latest api-up api-down api-reset api-logs api-ps api-health docker-build clean frontend-install frontend-dev frontend-build

PYTHON ?= python3
TOP ?= 6
WORKSPACE ?= $(realpath $(CURDIR)/..)
OUTPUT_DIR ?= $(CURDIR)/research_reports
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
GOOGLE_CLOUD_PROJECT_ID ?=
GOOGLE_CLOUD_LOCATION ?= asia-northeast3
GEMINI_MODEL ?= gemini-2.5-flash
MCP_GEMINI_MODEL ?= gemini-2.5-flash
EMBEDDING_LOCATION ?= asia-northeast3
GOOGLE_CLOUD_FALLBACK_LOCATIONS ?= us-central1,us-east1,europe-west1
GOOGLE_APPLICATION_CREDENTIALS ?= $(CURDIR)/google-service-account.json
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
VERIFY_SOURCE_FILES ?= $(CURDIR)/research_reports/V9_대화흐름혁신_업무자동화_신뢰성강화/research_sources.json
DOCKER_IMAGE ?= ora-automation:local
DOCKER_HOST_WORKSPACE ?= $(realpath $(CURDIR)/..)
DOCKER_OUTPUT_DIR ?= /workspace/Ora/ora-automation/research_reports/runs/docker
DOCKER_OUTPUT_HOST_DIR ?= $(DOCKER_HOST_WORKSPACE)/ora-automation/research_reports/runs/docker
DOCKERFILE ?= Dockerfile
COMPOSE ?= docker compose
API_BASE_URL ?= http://localhost:8000

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
	@echo "make verify-sources           : 지정한 소스 파일만 URL 검증."
	@echo "make clean                    : 임시 실행 결과 정리."
	@echo ""
	@echo "R&D 분석은 API 경로로만 실행됩니다 (POST /api/v1/orchestrations)"
	@echo ""
	@echo "FastAPI + Postgres + RabbitMQ (Docker Compose)"
	@echo "make api-up                   : API + DB + RabbitMQ + 워커 기동"
	@echo "make api-down                 : API/DB/RabbitMQ/워커 중지"
	@echo "make api-reset                : 전체 중지 + DB 볼륨 삭제"
	@echo "make api-ps                   : Compose 상태 확인"
	@echo "make api-logs                 : API/DB 로그 팔로우"
	@echo "make api-health               : API 헬스체크 호출"
	@echo ""
	@echo "Docker 빌드"
	@echo "make docker-build             : ora-automation 도커 이미지 빌드"
	@echo ""
	@echo "E2E(Cypress/Playwright)"
	@echo "make e2e-install             : 지정 프로젝트에서 cypress 설치(npm/pnpm/yarn)"
	@echo "make e2e-playwright-install  : 지정 프로젝트에서 Playwright 설치(npm/pnpm/yarn)"
	@echo "make e2e-open E2E_PROJECT_DIR=<front 폴더>     : npm install 후 npx cypress open 실행."
	@echo "make e2e-run E2E_PROJECT_DIR=<front 폴더>      : npm install 후 npx cypress run 실행."
	@echo "make e2e-service SERVICE=<서비스> : 서비스별 E2E 실행."
	@echo "make e2e-service-all          : 기본 슬롯(E2E_SERVICE_LIST) 순차 실행."
	@echo "make e2e-service-list         : 서비스별 E2E 지원 목록 출력."
	@echo "make qa-program               : 서비스별 E2E + md/json 리포트 생성."
	@echo "make qa-program-loop QA_LOOP_CYCLES=3 : QA 파이프라인 반복 실행."
	@echo "make qa-report-latest         : 최신 QA md 리포트 경로 출력."
	@echo ""
	@echo "Frontend"
	@echo "make frontend-install         : npm install"
	@echo "make frontend-dev             : vite dev server"
	@echo "make frontend-build           : vite build"

setup:
	$(PYTHON) -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -e .

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
