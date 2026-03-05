# Architecture / 아키텍처 문서

ora-automation 시스템의 아키텍처, 컴포넌트 관계, 데이터 흐름, 기술 결정에 대한 문서입니다.

---

## Table of Contents / 목차

- [System Overview / 시스템 개요](#system-overview--시스템-개요)
- [Component Architecture / 컴포넌트 아키텍처](#component-architecture--컴포넌트-아키텍처)
- [Data Flow / 데이터 흐름](#data-flow--데이터-흐름)
- [Database Schema / 데이터베이스 스키마](#database-schema--데이터베이스-스키마)
- [Message Queue Topology / 메시지 큐 토폴로지](#message-queue-topology--메시지-큐-토폴로지)
- [LLM Integration / LLM 통합](#llm-integration--llm-통합)
- [Agent Persona System / 에이전트 페르소나 시스템](#agent-persona-system--에이전트-페르소나-시스템)
- [R&D Pipeline / R&D 파이프라인](#rd-pipeline--rd-파이프라인)
- [Frontend Architecture / 프론트엔드 아키텍처](#frontend-architecture--프론트엔드-아키텍처)
- [Deployment Topology / 배포 토폴로지](#deployment-topology--배포-토폴로지)
- [Key Design Decisions / 핵심 설계 결정](#key-design-decisions--핵심-설계-결정)

---

## System Overview / 시스템 개요

ora-automation은 멀티 에이전트 R&D 리서치 오케스트레이터로, 세 가지 실행 경로를 지원합니다:

1. **CLI** — 로컬 환경에서 직접 파이프라인 실행 (개발/디버깅용)
2. **REST API** — Docker 환경에서 HTTP 요청으로 비동기 실행
3. **Chatbot UI** — 자연어 대화를 통한 인터랙티브 오케스트레이션

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Interface Layer                      │
├─────────────┬─────────────────────┬─────────────────────────────┤
│    CLI      │    React Chatbot    │     REST API (curl, etc.)   │
│ (cli.py)    │  (Vite + React 19)  │                             │
└──────┬──────┴──────────┬──────────┴──────────────┬──────────────┘
       │                 │                          │
       │           ┌─────▼──────────────────────────▼───┐
       │           │         FastAPI Server (:8000)      │
       │           │  ┌──────────┐  ┌─────────────────┐  │
       │           │  │chat_router│  │   main.py       │  │
       │           │  │(Gemini)  │  │ (orchestrations) │  │
       │           │  └────┬─────┘  └────────┬────────┘  │
       │           │       │                  │           │
       │           │  ┌────▼──────────────────▼────┐     │
       │           │  │     PostgreSQL (:5432)      │     │
       │           │  └────────────────────────────┘     │
       │           │       │                              │
       │           │  ┌────▼──────────────────────┐      │
       │           │  │    RabbitMQ (:5672)        │      │
       │           │  └────────────┬──────────────┘      │
       │           └───────────────┼──────────────────────┘
       │                           │
       │            ┌──────────────┼──────────────┐
       │            ▼              ▼               ▼
       │      worker-ceo    worker-pm     worker-{researcher,
       │                                   engineer, qa}
       │            │              │               │
       ▼            └──────────────┼──────────────┘
 ┌─────────────┐                   │
 │  Pipeline   │◄──────────────────┘
 │ (pipeline.py)│
 └──────┬──────┘
        │
   ┌────▼────┐   ┌──────────┐   ┌───────────┐
   │ Scoring │──>│Delibera- │──>│ Consensus │
   │         │   │  tion    │   │           │
   └─────────┘   └──────────┘   └─────┬─────┘
                                       │
                              ┌────────▼────────┐
                              │  Report Builder  │
                              │   (MD + JSON)    │
                              └─────────────────┘
```

---

## Component Architecture / 컴포넌트 아키텍처

### Backend Components / 백엔드 컴포넌트

#### 1. FastAPI Server (`ora_automation_api/`)

제어면(Control Plane) 역할을 하는 REST API 서버입니다.

| Module / 모듈 | Responsibility / 책임 |
|---|---|
| `main.py` | FastAPI 앱 초기화, 라우터 등록, DDL 마이그레이션 |
| `chat_router.py` | Gemini 챗봇 (비스트리밍 + SSE 스트리밍), 대화/리포트/프로젝트 API |
| `schemas.py` | Pydantic request/response 모델 (30+ 스키마) |
| `models.py` | SQLAlchemy ORM 모델 (5 테이블) |
| `database.py` | DB 세션 관리 (SessionLocal, engine) |
| `config.py` | 환경변수 기반 설정 (Settings 싱글턴) |
| `service.py` | 실행 생성/조회/제어 비즈니스 로직 |
| `queue.py` | RabbitMQ 발행 (exchange/routing key 관리) |
| `worker.py` | 에이전트 워커 프로세스 (큐 소비 → Make 타깃 실행) |
| `llm_planner.py` | 외부 LLM 플래너 프로세스 호출 어댑터 |

#### 2. R&D Orchestrator (`ora_rd_orchestrator/`)

핵심 오케스트레이션 엔진입니다. 모듈형 파이프라인 설계를 따릅니다.

| Module / 모듈 | Responsibility / 책임 |
|---|---|
| `pipeline.py` | 메인 진입점 `generate_report()` — 전체 파이프라인 조율 |
| `cli.py` | CLI 진입점, argparse 기반 |
| `config.py` | 상수, 환경변수, 프로파일 (standard/strict) |
| `types.py` | 모든 데이터클래스 정의 |
| `workspace.py` | 파일 스캔, `analyze_workspace()` |
| `topic_discovery.py` | LLM 토픽 발견 + 레거시 폴백 |
| `scoring.py` | 멀티 에이전트 스코어링 + 레거시 공식 |
| `deliberation.py` | 다중 라운드 디베이트 (수렴 기반 조기 종료) |
| `consensus.py` | 최종 합의 + 하드 게이트 |
| `research.py` | ArXiv, Crossref, OpenAlex API 클라이언트 |
| `web_sources.py` | 웹 스크래핑 유틸리티 |
| `report_builder.py` | Markdown + JSON 리포트 생성 |
| `llm_client.py` | `run_llm_command()` 서브프로세스 래퍼 |
| `llm_provider.py` | LLM 인터페이스 추상화 |
| `gemini_provider.py` | Google Gemini (Vertex AI) 구현 |
| `chatbot.py` | 챗봇 유틸리티 (plan 추출, 허용 타깃/키) |
| `personas.py` | PersonaRegistry (20 YAML → Agent 변환) |
| `engine.py` | 레거시 모놀리스 (~4600줄, 하위 호환) |

### Frontend Components / 프론트엔드 컴포넌트

| Component / 컴포넌트 | Responsibility / 책임 |
|---|---|
| `App.tsx` | 앱 상태 관리 (대화 목록, 현재 대화, 라우팅) |
| `Sidebar.tsx` | 대화 목록, 검색, 날짜별 그룹핑 |
| `ChatWindow.tsx` | 메시지 렌더링, 입력 폼, SSE 스트리밍 처리 |
| `MessageBubble.tsx` | 개별 메시지 렌더링 (plan/choices/project_select 포함) |
| `ProjectSelectCard.tsx` | 프로젝트 선택 UI (체크박스) |
| `api.ts` | 타입 안전한 API 클라이언트 |
| `types.ts` | 공유 TypeScript 타입 정의 |

---

## Data Flow / 데이터 흐름

### 1. Chatbot Flow / 챗봇 흐름

사용자 대화로부터 오케스트레이션 실행까지의 흐름:

```
User Input
    │
    ▼
React UI ──(POST /api/v1/chat/stream)──> FastAPI
    │                                        │
    │                                   Build system prompt
    │                                   (projects, targets, env keys)
    │                                        │
    │                                   Call Gemini Vertex AI
    │                                   (SSE streaming)
    │                                        │
    │                                   Extract plan from reply
    │                                   (JSON block parsing)
    │                                        │
    │                                   Apply action gate
    │                                   (첫 턴에서 premature plan 차단)
    │                                        │
    │                                   Inject project select
    │                                   (텍스트 내 프로젝트명 감지 → UI 전환)
    │                                        │
    │◄──(SSE: token events)──────────── Stream tokens back
    │◄──(SSE: done event)────────────── Final reply + plan/choices
    │
    ▼
[Plan Ready?]──Yes──> POST /api/v1/orchestrations
    │                      │
    No                     ▼
    │              Create run + Enqueue to RabbitMQ
    ▼                      │
Continue chat              ▼
                     Worker picks up job
                           │
                           ▼
                     Execute make target
                           │
                           ▼
                     Store results in DB + filesystem
```

### 2. R&D Pipeline Flow / R&D 파이프라인 흐름

```
Workspace Scan
    │
    ▼
Topic Discovery (LLM)
    │
    ▼
Multi-Agent Scoring
    │  ┌─ CEO: 시장성/수주성/사업성
    ├──┤  Planner: 품질/확장성/로드맵
    │  └─ Developer: 재사용성/난이도/실현성
    │     + 17 additional personas
    ▼
Multi-Round Debate
    │  Round 1: 초기 입장 발표
    ├─ Round 2: 반론 및 근거 제시
    │  Round N: 수렴 시 조기 종료
    ▼
Consensus (Hard Gates)
    │  가중 합의 투표
    │  최소 threshold 미달 시 제외
    ▼
Research Source Collection
    │  ArXiv API
    ├─ Crossref API
    │  OpenAlex API
    ▼
Report Generation
    │  Markdown (.md)
    └─ JSON (.json)
```

### 3. Orchestration Execution Flow / 오케스트레이션 실행 흐름

```
API Request
    │
    ▼
Create OrchestrationRun (DB)
    │  status: queued
    ▼
Publish to RabbitMQ
    │  exchange: ora.automation
    │  routing_key: agent.<role>
    ▼
Worker Consumes Message
    │  Lock run (optimistic)
    │  Update status: running
    ▼
Execute Make Target
    │  Subprocess: make <target> ENV=...
    │  Heartbeat every 2s
    │  stdout/stderr → file
    ▼
[Success?]
    │
    ├── Yes ──> status: completed
    │
    └── No
         │
    [Retry?]
         │
         ├── Yes ──> Publish to retry exchange
         │           (exponential backoff)
         │
         └── No ──> status: error
                    (move to DLQ)
```

---

## Database Schema / 데이터베이스 스키마

PostgreSQL 16에 5개 테이블을 사용합니다.

```
┌──────────────────────┐     ┌──────────────────────────┐
│  chat_conversations  │     │  orchestration_decisions  │
├──────────────────────┤     ├──────────────────────────┤
│ id (PK)              │     │ id (PK)                  │
│ title                │     │ run_id (FK)              │
│ created_at           │     │ owner                    │
│ updated_at           │     │ rationale                │
└──────────┬───────────┘     │ risk                     │
           │                 │ next_action              │
           │ 1:N             │ due                      │
           │                 │ payload (JSON)           │
┌──────────▼───────────┐     │ created_at               │
│   chat_messages      │     └─────────────┬────────────┘
├──────────────────────┤                   │
│ id (PK, auto)        │                   │ 1:1
│ conversation_id (FK) │                   │
│ role                 │     ┌─────────────▼────────────┐
│ content              │     │   orchestration_runs     │
│ plan (JSON)          │     ├──────────────────────────┤
│ run_id               │     │ id (PK)                  │
│ created_at           │     │ idempotency_key          │
└──────────────────────┘     │ user_prompt              │
                             │ target                   │
                             │ agent_role               │
                             │ command                  │
                             │ rollback_command         │
                             │ env (JSON)               │
                             │ pipeline_stages (JSON)   │
                             │ current_stage            │
                             │ status                   │
                             │ fail_label               │
                             │ attempt_count            │
                             │ max_attempts             │
                             │ pause/cancel_requested   │
                             │ locked_by / locked_at    │
                             │ heartbeat_at             │
                             │ decision_id (FK)         │
                             │ exit_code                │
                             │ stdout/stderr_path       │
                             │ error_message            │
                             │ created/updated_at       │
                             │ started/finished_at      │
                             └──────────────┬───────────┘
                                            │
                                            │ 1:N
                                            │
                             ┌──────────────▼───────────┐
                             │  orchestration_events    │
                             ├──────────────────────────┤
                             │ id (PK, auto)            │
                             │ run_id (FK)              │
                             │ stage                    │
                             │ event_type               │
                             │ message                  │
                             │ payload (JSON)           │
                             │ created_at               │
                             └──────────────────────────┘
```

### Run Status Lifecycle / 실행 상태 생명주기

```
         ┌──────────────────────────────────┐
         │                                  │
         ▼                                  │
    ┌─────────┐    enqueue    ┌─────────┐   │ retry
    │ queued  │──────────────>│ running │───┘
    └────┬────┘               └────┬────┘
         │                         │
         │                    ┌────▼────┐
         │                    │completed│
         │                    └─────────┘
         │
    ┌────▼────┐               ┌─────────┐
    │ paused  │               │  error  │
    └────┬────┘               └─────────┘
         │
    ┌────▼─────┐              ┌──────────┐
    │ resumed  │              │cancelled │
    │(→queued) │              └──────────┘
    └──────────┘

    ┌──────────┐
    │ dry-run  │  (실행하지 않음)
    └──────────┘
```

---

## Message Queue Topology / 메시지 큐 토폴로지

RabbitMQ를 사용한 3-tier 큐 구조입니다.

```
┌────────────────────────────────────────────────────────────────────┐
│                        RabbitMQ Broker                              │
│                                                                     │
│  ┌─────────────────────┐                                           │
│  │  ora.automation      │  (main exchange, topic)                  │
│  │  routing: agent.*    │                                          │
│  └──────────┬──────────┘                                           │
│             │                                                       │
│     ┌───────┼───────┬───────────┬──────────────┐                   │
│     ▼       ▼       ▼           ▼              ▼                   │
│  agent.ceo agent.pm agent.researcher agent.engineer agent.qa       │
│  (queue)   (queue)  (queue)      (queue)      (queue)              │
│             │                                                       │
│             │ (on failure, if retries remain)                      │
│             ▼                                                       │
│  ┌─────────────────────────┐                                       │
│  │ ora.automation.retry     │  (retry exchange, exponential delay) │
│  └──────────┬──────────────┘                                       │
│             │                                                       │
│             │ (after max_attempts exhausted)                        │
│             ▼                                                       │
│  ┌─────────────────────────┐                                       │
│  │ ora.automation.dlx       │  (dead letter exchange)              │
│  └─────────────────────────┘                                       │
│                                                                     │
└────────────────────────────────────────────────────────────────────┘
```

### Agent Role Routing / 에이전트 역할 라우팅

각 실행의 `target`에 따라 적절한 에이전트 역할이 자동 선택됩니다:

| Target | Default Agent / 기본 에이전트 |
|---|---|
| `run-cycle`, `run-loop`, `run` | `researcher` |
| `e2e-service`, `e2e-service-all` | `qa` |
| `qa-program` | `qa` |
| 기타 | `engineer` |

---

## LLM Integration / LLM 통합

### Gemini (Vertex AI) — Primary / 기본

Google Gemini를 Vertex AI를 통해 호출합니다.

```
Application
    │
    ▼
gemini_provider.py
    │
    ├── _get_gemini_token()  ←── GCP Service Account JSON
    │
    ├── _call_gemini()       ←── Non-streaming (chat endpoint)
    │   URL: https://{location}-aiplatform.googleapis.com/v1/
    │        projects/{project}/locations/{location}/
    │        publishers/google/models/{model}:generateContent
    │
    └── _stream_gemini()     ←── SSE Streaming (chat/stream endpoint)
        URL: .../:streamGenerateContent?alt=sse
```

**Location Fallback / 리전 폴백**: Primary location 실패 시 fallback locations로 순차 재시도합니다.

```
asia-northeast3 → us-central1 → us-east1 → europe-west1
```

### LLM Fallback Pattern / LLM 폴백 패턴

모든 LLM 의존 모듈은 동일한 폴백 패턴을 따릅니다:

```python
try:
    result = run_llm_command(cmd, input_data, timeout)  # LLM 호출
except Exception:
    result = legacy_hardcoded_logic(input_data)          # 하드코딩 폴백
```

적용 모듈:
- `topic_discovery.py` — LLM 토픽 발견 / 레거시 키워드 매칭
- `scoring.py` — LLM 스코어링 / 레거시 공식 계산
- `deliberation.py` — LLM 디베이트 / 고정 응답
- `consensus.py` — LLM 합의 / 가중 평균

---

## Agent Persona System / 에이전트 페르소나 시스템

20개의 YAML 기반 에이전트가 `src/ora_rd_orchestrator/personas/` 에 정의되어 있습니다.

### Persona Structure / 페르소나 구조

```yaml
# 예: ceo.yaml
name: CEO
team: strategy
role: Chief Executive Officer
expertise:
  - 시장성 평가
  - 사업 전략
  - 경쟁 분석
scoring_criteria:
  - 시장 영향력
  - 수익 잠재력
  - 사업 리스크
weight: 1.5  # 합의 투표 가중치
```

### Team Composition / 팀 구성

```
Strategy Team        Product Team         Engineering Team
├── CEO              ├── PM               ├── Backend Dev
└── Planner          ├── Market Analyst   ├── Frontend Dev
                     └── Finance Analyst  └── DevOps

Research Team        QA Team              Operations Team
├── Researcher       ├── QA Lead          ├── Ops
├── Data Scientist   ├── QA              └── DevOps SRE
└── Linguist         └── Search Evaluator

Governance
└── Debate Supervisor
```

### PersonaRegistry / 페르소나 레지스트리

`PersonaRegistry`는 YAML 파일을 로드하고 `AgentDefinition` 목록으로 변환합니다:

```python
registry = PersonaRegistry()
agents = registry.to_agent_definitions()
# → [AgentDefinition(name="CEO", team="strategy", ...), ...]
```

---

## R&D Pipeline / R&D 파이프라인

### Pipeline Stages / 파이프라인 단계

`pipeline.py`의 `generate_report()` 함수가 아래 단계를 순차적으로 실행합니다:

| Stage | Module | Description / 설명 |
|---|---|---|
| 1. Workspace Scan | `workspace.py` | 프로젝트 디렉토리 스캔, 파일 분석 |
| 2. Topic Discovery | `topic_discovery.py` | LLM으로 R&D 주제 후보 발견 |
| 3. Multi-Agent Scoring | `scoring.py` | 20개 에이전트가 독립적으로 점수 부여 |
| 4. Deliberation | `deliberation.py` | N라운드 토론 (지지/반대/근거 제시) |
| 5. Consensus | `consensus.py` | 가중 투표 + 하드 게이트로 최종 합의 |
| 6. Research Collection | `research.py` | 학술 DB에서 관련 논문/자료 수집 |
| 7. Source Verification | `verify_sources.py` | URL 접근성 + API 교차 검증 |
| 8. Report Generation | `report_builder.py` | MD + JSON 리포트 생성 |

### Deliberation Protocol / 토론 프로토콜

```
Round 1: 각 에이전트가 TopN 전략에 대한 초기 평가를 제시
         (confidence score, supporting evidence)
                │
                ▼
Round 2: 다른 에이전트의 평가에 대한 반론/지지
         (agree/disagree, counter-evidence)
                │
                ▼
Round N: 수렴도 체크 → threshold 이상이면 조기 종료
         (convergence = Δscores < epsilon)
                │
                ▼
Consensus: 가중 투표로 최종 순위 결정
           (hard gate: 최소 3 에이전트 지지 필요)
```

---

## Frontend Architecture / 프론트엔드 아키텍처

React 19 + Vite 7 기반 SPA입니다.

### State Management / 상태 관리

React의 `useState`/`useEffect` 훅 기반으로 상태를 관리합니다 (외부 상태 라이브러리 없음).

```
App.tsx
├── conversations: ConversationRead[]     # 대화 목록
├── currentConversation: string | null    # 현재 선택된 대화 ID
├── messages: ChatMessageRead[]           # 현재 대화 메시지
└── isStreaming: boolean                  # SSE 스트리밍 중 여부
```

### API Client / API 클라이언트

`lib/api.ts`가 타입 안전한 API 함수를 제공합니다:

```typescript
// 채팅 (SSE 스트리밍)
streamChat(message, conversationId, history, onToken, onDone)

// 대화 CRUD
listConversations(limit?)
createConversation(title?)
getConversation(id)
deleteConversation(id)

// 오케스트레이션
createOrchestration(payload)
createBatchOrchestrations(prompt, plans)

// 조회
listReports()
listProjects()
```

### Chat Response Handling / 채팅 응답 처리

Gemini의 응답에서 특수 JSON 블록을 파싱하여 UI 컴포넌트로 변환합니다:

| JSON Payload | UI Component / UI 컴포넌트 |
|---|---|
| `plan` | 실행 확인 버튼 (단일 계획) |
| `plans` | 실행 확인 버튼 (다중 계획) |
| `choices` | 선택지 버튼 그룹 |
| `project_select` | 프로젝트 체크박스 카드 |

---

## Deployment Topology / 배포 토폴로지

### Docker Compose Services / Docker Compose 서비스

```
docker-compose.yml
│
├── db (postgres:16-alpine)
│   └── Volume: ora_automation_pgdata
│
├── rabbitmq (rabbitmq:3.13-management)
│   └── Management UI: :15672
│
├── api (Dockerfile → Python 3.11-slim)
│   ├── depends_on: db, rabbitmq
│   ├── Port: 8000
│   └── Volume: ..:/workspace/Ora (host workspace mount)
│
├── frontend (frontend/Dockerfile → Nginx)
│   ├── depends_on: api
│   └── Port: 5173 → 80
│
├── worker-ceo (Dockerfile)
│   └── cmd: python -m ora_automation_api.worker --agent-role ceo
│
├── worker-pm (Dockerfile)
│   └── cmd: python -m ora_automation_api.worker --agent-role pm
│
├── worker-researcher (Dockerfile)
│   └── cmd: python -m ora_automation_api.worker --agent-role researcher
│
├── worker-engineer (Dockerfile)
│   └── cmd: python -m ora_automation_api.worker --agent-role engineer
│
└── worker-qa (Dockerfile)
    └── cmd: python -m ora_automation_api.worker --agent-role qa
```

### Network / 네트워크

모든 서비스는 Docker의 기본 브리지 네트워크에서 통신합니다:
- DB: `db:5432`
- RabbitMQ: `rabbitmq:5672`
- API: `api:8000`

외부 노출 포트: `5432`, `5672`, `15672`, `8000`, `5173`

### Volume Mount / 볼륨 마운트

워커와 API는 호스트의 Ora 워크스페이스 전체를 마운트합니다:
```yaml
volumes:
  - ..:/workspace/Ora
```

이를 통해 워커가 프로젝트 소스를 직접 읽고, Make 타깃을 실행할 수 있습니다.

---

## Key Design Decisions / 핵심 설계 결정

### 1. Modular Pipeline vs. Monolith / 모듈형 파이프라인 vs. 모놀리스

**결정**: 모듈형 파이프라인(`pipeline.py`) + 레거시 모놀리스(`engine.py`) 병행

**이유**:
- `engine.py`는 ~4600줄의 초기 프로토타입으로, 단일 파일에 모든 로직이 있음
- `pipeline.py`는 각 단계를 독립 모듈로 분리하여 테스트/유지보수 용이
- 하위 호환을 위해 `engine.py`를 유지하되, 신규 개발은 모듈형으로 진행

### 2. RabbitMQ + Worker Pattern / RabbitMQ + 워커 패턴

**결정**: RabbitMQ 기반 비동기 작업 큐 + 역할별 전용 워커

**이유**:
- R&D 분석은 수 분~수십 분 소요되어 동기 HTTP로는 처리 불가
- 에이전트 역할별 큐 분리로 워크로드 격리 및 스케일링 용이
- 3-tier 구조(main/retry/dlx)로 실패 재시도 및 데드레터 처리

### 3. Gemini Direct Call / Gemini 직접 호출

**결정**: Google SDK 대신 `urllib` 직접 HTTP 호출

**이유**:
- 의존성 최소화 (google-cloud-aiplatform SDK 불필요)
- SSL/프록시 환경에서의 제어력 향상
- SSE 스트리밍을 저수준으로 직접 구현하여 지연 최소화
- 리전 폴백을 직접 제어 가능

### 4. LLM Fallback Pattern / LLM 폴백 패턴

**결정**: 모든 LLM 의존 모듈에 하드코딩된 폴백 로직 구현

**이유**:
- LLM API 장애/rate-limit 시에도 파이프라인이 중단되지 않음
- 레거시 공식 기반 결과라도 리포트를 생성할 수 있음
- 점진적 마이그레이션 가능 (폴백 → LLM 전환)

### 5. Chatbot Action Gate / 챗봇 액션 게이트

**결정**: 첫 턴에서 premature plan/project_select 차단

**이유**:
- Gemini가 시스템 프롬프트의 "clarification-first" 지시를 무시하는 경우가 있음
- 사용자가 충분한 정보를 제공하기 전에 실행 계획이 생성되는 것을 방지
- FOCUS가 명시적으로 있는 경우에만 첫 턴 실행을 허용

### 6. Frontend: No State Library / 프론트엔드: 상태 라이브러리 미사용

**결정**: React 내장 훅만으로 상태 관리

**이유**:
- 챗봇 UI의 상태 복잡도가 낮음 (대화 목록 + 현재 메시지)
- Redux/Zustand 등의 오버헤드 불필요
- 향후 복잡도 증가 시 도입 가능
