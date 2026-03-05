# ora-automation

Multi-Agent R&D Research Orchestrator / 멀티 에이전트 R&D 리서치 오케스트레이터

`ora-automation`은 Ora 프로젝트 워크스페이스를 스캔하고, 다중 에이전트 토론(스코어링, 디베이트, 컨센서스)을 수행하여 구조화된 리서치 리포트를 생성하는 자동화 플랫폼입니다. CLI, REST API, 또는 챗봇 UI를 통해 오케스트레이션을 실행할 수 있습니다.

## Table of Contents / 목차

- [Architecture / 아키텍처](#architecture--아키텍처)
- [Tech Stack / 기술 스택](#tech-stack--기술-스택)
- [Project Structure / 프로젝트 구조](#project-structure--프로젝트-구조)
- [Quick Start / 빠른 시작](#quick-start--빠른-시작)
- [Running with Docker Compose / Docker 실행](#running-with-docker-compose--docker-실행)
- [CLI Usage / CLI 사용법](#cli-usage--cli-사용법)
- [Makefile Targets / Make 타깃](#makefile-targets--make-타깃)
- [Agent Persona System / 에이전트 페르소나 시스템](#agent-persona-system--에이전트-페르소나-시스템)
- [Research Source Verification / 리서치 소스 검증](#research-source-verification--리서치-소스-검증)
- [E2E Testing / E2E 테스트](#e2e-testing--e2e-테스트)
- [QA Program / QA 프로그램](#qa-program--qa-프로그램)
- [Output / 출력물](#output--출력물)
- [Environment Variables / 환경변수](#environment-variables--환경변수)
- [Documentation / 문서](#documentation--문서)

## Architecture / 아키텍처

```
┌─────────────────┐     ┌──────────────┐     ┌────────────┐
│  React UI       │────>│  FastAPI      │────>│ PostgreSQL │
│  (Vite, :5173)  │     │  (:8000)      │     │  (:5432)   │
└─────────────────┘     └──────┬───────┘     └────────────┘
                               │
                        ┌──────┴───────┐
                        │   RabbitMQ   │
                        │  (:5672)     │
                        └──────┬───────┘
              ┌────────────────┼────────────────┐
              ▼                ▼                 ▼
         worker-ceo     worker-pm     worker-{researcher,engineer,qa}
              │                │                 │
              └────────────────┼────────────────┘
                               ▼
                     Google Gemini (Vertex AI)
                               ▼
                     Research Reports (MD + JSON)
```

9개 서비스(PostgreSQL, RabbitMQ, FastAPI, React Frontend, 5 Agent Workers)가 Docker Compose로 오케스트레이션됩니다.

상세 아키텍처 문서: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Tech Stack / 기술 스택

| Component / 구성 요소 | Technology / 기술 | Version / 버전 |
|---|---|---|
| Backend | Python, FastAPI, SQLAlchemy 2, Pydantic 2 | 3.10+ / 0.115+ |
| Frontend | React, TypeScript, Vite | 19 / 5.9 / 7.3 |
| Database | PostgreSQL | 16 |
| Message Queue | RabbitMQ | 3.13 |
| LLM | Google Gemini (Vertex AI) | 2.5-flash |
| Container | Docker Compose | - |

## Project Structure / 프로젝트 구조

```
ora-automation/
├── src/
│   ├── ora_rd_orchestrator/      # Core orchestration engine / 핵심 오케스트레이션 엔진
│   │   ├── pipeline.py           # Main pipeline: generate_report()
│   │   ├── cli.py                # CLI entry point / CLI 진입점
│   │   ├── config.py             # Constants, env vars, profiles
│   │   ├── types.py              # All dataclasses
│   │   ├── llm_client.py         # LLM subprocess wrapper
│   │   ├── llm_provider.py       # LLM interface abstraction
│   │   ├── gemini_provider.py    # Google Gemini implementation
│   │   ├── workspace.py          # File scanning, analyze_workspace()
│   │   ├── topic_discovery.py    # LLM topic discovery + fallback
│   │   ├── scoring.py            # Multi-agent scoring + legacy formula
│   │   ├── deliberation.py       # Multi-round debate / 다중 라운드 토론
│   │   ├── consensus.py          # Final consensus + hard gates
│   │   ├── research.py           # ArXiv/Crossref/OpenAlex clients
│   │   ├── web_sources.py        # Web scraping utilities
│   │   ├── report_builder.py     # Markdown + JSON report generation
│   │   ├── chatbot.py            # Gemini chatbot interface
│   │   ├── personas.py           # PersonaRegistry (20 YAML personas)
│   │   ├── personas/             # 20 YAML agent definitions
│   │   ├── agent/                # Agent module
│   │   └── engine.py             # Legacy monolith (~4600 lines, backward compat)
│   │
│   └── ora_automation_api/       # FastAPI backend / FastAPI 백엔드
│       ├── main.py               # App entry, router registration
│       ├── chat_router.py        # Chat + conversations + reports + projects
│       ├── schemas.py            # Pydantic request/response models
│       ├── models.py             # SQLAlchemy ORM models
│       ├── database.py           # DB session management
│       ├── config.py             # API settings (env vars)
│       ├── service.py            # Run execution logic
│       ├── queue.py              # RabbitMQ message routing
│       ├── worker.py             # Agent worker process
│       └── llm_planner.py        # LLM plan adapter
│
├── frontend/                     # React + Vite SPA
│   └── src/
│       ├── App.tsx               # Main app (conversation state)
│       ├── components/
│       │   ├── Sidebar.tsx       # Conversation list, search, date groups
│       │   ├── ChatWindow.tsx    # Message display + input
│       │   ├── MessageBubble.tsx # Single message rendering
│       │   └── ProjectSelectCard.tsx # Project selection UI
│       ├── lib/
│       │   ├── api.ts            # Typed API client
│       │   └── constants.ts      # App constants
│       └── types.ts              # Shared TypeScript types
│
├── scripts/                      # Shell + Python utilities
├── automations/                  # Orchestration configs (research, e2e, qa)
├── research_reports/             # Output directory / 출력 디렉토리
├── docs/                         # Documentation / 문서
│   ├── ARCHITECTURE.md           # Architecture document / 아키텍처 문서
│   └── API_REFERENCE.md          # API reference / API 레퍼런스
├── Makefile                      # 30+ targets (primary build tool)
├── docker-compose.yml            # 9-service stack
├── pyproject.toml                # Python package metadata
└── Dockerfile                    # Python 3.11-slim + system deps
```

## Quick Start / 빠른 시작

### Prerequisites / 사전 준비

- Python 3.10+
- Docker & Docker Compose
- Node.js 18+ (프론트엔드 로컬 개발 시)
- GCP Service Account JSON (Gemini API용)

### Setup / 설정

```bash
# 1) Python 환경 설정
make setup                  # .venv 생성 + pip install -e .

# 2) 환경변수 확인 (Gemini)
# google-service-account.json이 프로젝트 루트에 있어야 합니다
# Makefile 기본값으로 GOOGLE_CLOUD_PROJECT_ID, GEMINI_MODEL 등이 설정됩니다

# 3) 1회 R&D 분석 실행
make run

# 4) 반복 러너 실행
make run-cycle
```

## Running with Docker Compose / Docker 실행

전체 스택(API + DB + RabbitMQ + 에이전트 워커 + 프론트엔드)을 한 번에 기동합니다.

```bash
# 전체 서비스 기동
make api-up

# 상태 확인
make api-ps
make api-health

# 로그 확인
make api-logs

# 중지
make api-down

# DB 볼륨까지 초기화
make api-reset
```

### Services / 서비스 목록

| Service | Container | Port | Description / 설명 |
|---|---|---|---|
| `db` | ora-automation-db | 5432 | PostgreSQL 16 (실행 이력, 대화, 의사결정 저장) |
| `rabbitmq` | ora-automation-rabbitmq | 5672, 15672 | 메시지 브로커 (main/retry/dlq 큐 라우팅) |
| `api` | ora-automation-api | 8000 | FastAPI 제어면 (REST + SSE 스트리밍) |
| `frontend` | ora-automation-frontend | 5173 | React 챗봇 UI (Nginx 서빙) |
| `worker-ceo` | ora-automation-worker-ceo | - | CEO 에이전트 워커 |
| `worker-pm` | ora-automation-worker-pm | - | PM 에이전트 워커 |
| `worker-researcher` | ora-automation-worker-researcher | - | Researcher 에이전트 워커 |
| `worker-engineer` | ora-automation-worker-engineer | - | Engineer 에이전트 워커 |
| `worker-qa` | ora-automation-worker-qa | - | QA 에이전트 워커 |

## CLI Usage / CLI 사용법

```bash
# 기본 실행 (TOP 6개 전략, 2라운드 토론)
python3 src/ora_rd_orchestrator/cli.py \
  --workspace /path/to/Ora \
  --output-dir ./research_reports/runs/manual \
  --output-name rd_research_report_$(date +%Y%m%d_%H%M%S) \
  --top 6 \
  --debate-rounds 3

# 단일 전략 포커스 리포트
python3 src/ora_rd_orchestrator/cli.py \
  --workspace /path/to/Ora \
  --output-dir ./research_reports/runs/manual \
  --output-name rd_research_report_$(date +%Y%m%d_%H%M%S) \
  --single-strategy \
  --focus OraB2bAndroid \
  --version-tag V10
```

## Makefile Targets / Make 타깃

### R&D Analysis / R&D 분석

| Command | Description / 설명 |
|---|---|
| `make run` | 1회 R&D 분석 (TOP=6, DEBATE_ROUNDS=2) |
| `make run-cycle` | 반복 러너 + 소스 검증 |
| `make run-cycle-deep` | 확장 스캔 + 강한 검증 (TOP=8, MAX_FILES=2400) |
| `make run-focus FOCUS=<label>` | 특정 전략 포커스 분석 |
| `make run-single FOCUS=<label>` | 단일 전략 리포트 |
| `make run-loop RUN_CYCLES=N` | N회 반복 실행 |

### E2E & QA

| Command | Description / 설명 |
|---|---|
| `make e2e-service SERVICE=<name>` | 서비스별 E2E 테스트 |
| `make e2e-service-all` | 전체 서비스 E2E 실행 |
| `make qa-program` | QA 파이프라인 실행 + 리포트 생성 |
| `make verify-sources` | 리서치 소스 URL 검증 |

### Infrastructure / 인프라

| Command | Description / 설명 |
|---|---|
| `make setup` | Python venv 생성 + 의존성 설치 |
| `make api-up` | Docker Compose 전체 기동 |
| `make api-down` | Docker 서비스 중지 |
| `make api-reset` | Docker 중지 + DB 볼륨 삭제 |
| `make api-logs` | Docker 로그 추적 |
| `make api-health` | 헬스체크 |
| `make frontend-dev` | 프론트엔드 개발 서버 (:5173) |
| `make frontend-build` | 프론트엔드 프로덕션 빌드 |

### Parameter Override / 파라미터 오버라이드

```bash
make run TOP=5 WORKSPACE=/path/to/Ora OUTPUT_DIR=/tmp/output
make run-cycle DEBATE_ROUNDS=4
make run-cycle-deep RUN_CYCLES=3 VERIFY_ROUNDS=5
```

## Agent Persona System / 에이전트 페르소나 시스템

20개의 YAML 기반 에이전트 페르소나가 팀별로 구성되어 있습니다.

| Team / 팀 | Personas / 페르소나 |
|---|---|
| Strategy / 전략 | CEO, Planner |
| Product / 제품 | PM, Market Analyst, Finance Analyst |
| Engineering / 엔지니어링 | Backend Developer, Frontend Developer, DevOps |
| Research / 연구 | Researcher, Data Scientist, Linguist |
| QA | QA Lead, QA, Search Evaluator |
| Operations / 운영 | Ops, DevOps SRE |
| Governance / 거버넌스 | Debate Supervisor |

각 에이전트는 독립된 스코어링 기준과 관점을 가지고 토론에 참여하며, 최종 합의를 도출합니다.

## Research Source Verification / 리서치 소스 검증

`verify_sources.py`는 생성된 리서치 리포트의 출처를 자동 검증합니다.

- URL 접근성 확인 (HTTP 상태 코드)
- arXiv API 교차 검증 (`verified_by_arxiv_api`)
- Crossref API / OpenAlex API fallback 검증
- 미검증 항목 자동 재시도 (`--rounds`, `--retry-delay`)

```bash
make verify-sources VERIFY_SOURCE_FILES="path/to/research_sources.json"
```

## E2E Testing / E2E 테스트

서비스별 E2E 테스트를 Cypress 또는 Playwright로 실행합니다.

```bash
# 서비스별 실행
make e2e-service SERVICE=b2b       # OraB2bServer (Gradle)
make e2e-service SERVICE=b2c       # OraWebAppFrontend (npm)
make e2e-service SERVICE=ai        # OraAiServer (pytest)
make e2e-service SERVICE=android   # OraB2bAndroid (Gradle)
make e2e-service SERVICE=telecom   # OraServer (Gradle)

# 전체 서비스 일괄 실행
make e2e-service-all

# Playwright로 전환
make e2e-service SERVICE=b2c E2E_TOOL=playwright
```

## QA Program / QA 프로그램

서비스별 E2E 실행 + 결과 리포트를 자동 생성합니다.

```bash
make qa-program                      # 1회 실행
make qa-program-loop QA_LOOP_CYCLES=3  # 3회 반복
make qa-report-latest                # 최신 리포트 경로
```

출력: `research_reports/qa_runs/<run_name>/`
- `qa_summary.md` — 요약 보고서
- `qa_summary.json` — 구조화 결과
- `<service>_attemptN.log` — 서비스별 실행 로그

## Output / 출력물

| File / 파일 | Description / 설명 |
|---|---|
| `rd_research_report_*.md` | Markdown 리서치 리포트 |
| `rd_research_report_*.json` | 구조화 JSON (점수, 토론 로그, 합의) |
| `research_sources.json` | 검증된 출처 URL 목록 |

### JSON Key Fields / JSON 핵심 필드

- `ranked` — 통합 점수 순위
- `agent_scores` — 에이전트별 점수 (토론 후)
- `agent_scores_initial` — 토론 전 초기 점수
- `debate_rounds_executed` — 실제 수행 토론 라운드 수
- `consensus` — 가중 합의 후보
- `discussion` — 라운드별 토론 로그 (지지/반대, confidence, evidence)

## Environment Variables / 환경변수

### LLM (Gemini)

| Variable | Description / 설명 | Default |
|---|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | GCP 서비스 계정 JSON 경로 | - |
| `GOOGLE_CLOUD_PROJECT_ID` | GCP 프로젝트 ID | - |
| `GOOGLE_CLOUD_LOCATION` | Primary region | `asia-northeast3` |
| `GOOGLE_CLOUD_FALLBACK_LOCATIONS` | Fallback regions (콤마 구분) | `us-central1,us-east1,europe-west1` |
| `GEMINI_MODEL` | Gemini 모델명 | `gemini-2.5-flash` |

### API

| Variable | Description / 설명 | Default |
|---|---|---|
| `DATABASE_URL` | PostgreSQL 연결 문자열 | `postgresql+psycopg://ora:ora@db:5432/ora_automation` |
| `RABBITMQ_URL` | AMQP 연결 문자열 | `amqp://guest:guest@rabbitmq:5672/%2F` |
| `ORA_AUTOMATION_ROOT` | ora-automation 루트 경로 | `/workspace/Ora/ora-automation` |
| `ORA_PROJECTS_ROOT` | 프로젝트 스캔 상위 디렉토리 | `ORA_AUTOMATION_ROOT`의 상위 |

### Orchestration Tuning / 오케스트레이션 튜닝

| Variable | Description / 설명 | Default |
|---|---|---|
| `ORCHESTRATION_PROFILE` | `standard` 또는 `strict` | `standard` |
| `DEBATE_ROUNDS` | 토론 라운드 수 | `2` |
| `TOP` | 분석할 상위 전략 수 | `6` |

### Research Source API

| Variable | Description / 설명 | Default |
|---|---|---|
| `ORA_RD_RESEARCH_ARXIV_SEARCH` | arXiv 검색 활성화 (`1`/`0`) | `1` |
| `ORA_RD_RESEARCH_CROSSREF_SEARCH` | Crossref 검색 활성화 | `1` |
| `ORA_RD_RESEARCH_OPENALEX_SEARCH` | OpenAlex 검색 활성화 | `1` |
| `ORA_RD_RESEARCH_SEARCH_TIMEOUT` | 검색 타임아웃 (초) | `10` |

## Documentation / 문서

- [Architecture / 아키텍처 문서](docs/ARCHITECTURE.md) — 시스템 아키텍처, 컴포넌트 관계, 데이터 흐름
- [API Reference / API 레퍼런스](docs/API_REFERENCE.md) — 전체 엔드포인트 상세 문서 (요청/응답 스키마, 예시)
- [GitHub Workflow / 깃허브 활용 규칙](docs/GITHUB_WORKFLOW.md) — 브랜치 전략, 커밋 컨벤션, PR/이슈/리뷰 규칙

## License

Private project.
