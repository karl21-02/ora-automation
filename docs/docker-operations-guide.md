# Ora R&D Automation — Docker 운영 가이드

> **Last updated:** 2026-03-04
> **Scope:** Docker Compose 기반 API + Worker 클러스터의 구성, 실행, 트러블슈팅

---

## 1. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│  Client (curl / UI)                                             │
│  POST /api/v1/orchestrations { user_prompt, target, env, ... }  │
└──────────────┬──────────────────────────────────────────────────┘
               │ HTTP 202 Accepted
               ▼
┌──────────────────────┐      ┌──────────────────────────┐
│  api  (FastAPI)       │─────▶│  db  (PostgreSQL 16)      │
│  :8000                │      │  :5432                    │
│  uvicorn              │      │  ora_automation DB        │
└──────────┬───────────┘      └──────────────────────────┘
           │ AMQP publish
           ▼
┌──────────────────────────────────────────────────┐
│  rabbitmq  (3.13-management)                      │
│  :5672 (AMQP)   :15672 (Management UI)            │
│                                                    │
│  Exchanges                                         │
│  ├─ ora.automation        (direct) ── main         │
│  ├─ ora.automation.retry  (direct) ── retry + TTL  │
│  └─ ora.automation.dlx    (direct) ── dead letter   │
│                                                    │
│  Queues (per role)                                 │
│  ├─ ora.automation.agent.{role}                    │
│  ├─ ora.automation.agent.{role}.retry              │
│  └─ ora.automation.agent.{role}.dlq                │
└──────────┬───────────────────────────────────────┘
           │ AMQP consume
           ▼
┌────────────────────────────────────────────────────┐
│  Workers (5 containers)                             │
│                                                     │
│  worker-ceo         ← ora.automation.agent.ceo      │
│  worker-pm          ← ora.automation.agent.pm       │
│  worker-researcher  ← ora.automation.agent.researcher│
│  worker-engineer    ← ora.automation.agent.engineer  │
│  worker-qa          ← ora.automation.agent.qa       │
│                                                     │
│  각 Worker:                                         │
│  1. RabbitMQ 큐에서 메시지 소비                      │
│  2. execute_run(run_id) → subprocess: make {target}  │
│  3. 결과 DB 기록 + stdout/stderr 파일 저장           │
│  4. 실패 시 retry queue 또는 DLQ로 라우팅            │
└────────────────────────────────────────────────────┘
```

### 1.1 메시지 흐름

| 단계 | 컴포넌트 | 동작 |
|------|----------|------|
| 1 | Client | `POST /api/v1/orchestrations` 호출 |
| 2 | API | DB에 `OrchestrationRun` 레코드 생성 (status=`queued`) |
| 3 | API | `publish_run()` → RabbitMQ main exchange로 메시지 발행 |
| 4 | API | 즉시 `202 Accepted` + `run_id` 반환 (비동기) |
| 5 | Worker | 큐에서 메시지 수신, `execute_run()` 호출 |
| 6 | Worker | `make run-cycle` (또는 지정 target) subprocess 실행 |
| 7 | Worker | 성공 → ACK, 실패 → retry queue (재시도) 또는 DLQ (포기) |
| 8 | Client | `GET /api/v1/orchestrations/{run_id}` 로 상태 폴링 |

### 1.2 역할 기반 라우팅

API가 `target` 값을 보고 적절한 Worker 역할을 자동 선택합니다:

| Target 패턴 | 선택되는 Worker |
|---|---|
| `run-cycle`, `run-loop`, `run-direct` 등 R&D 분석 | `engineer` |
| `verify-sources` 등 연구 검증 | `researcher` |
| `qa-program`, `e2e-service` 등 QA 작업 | `qa` |
| 명시적 `agent_role` 파라미터 | 지정된 역할 |

---

## 2. 서비스 구성

### 2.1 컨테이너 목록

| 서비스 | 이미지 | 포트 | 역할 |
|--------|--------|------|------|
| `db` | `postgres:16-alpine` | 5432 | 실행 이력, 이벤트, 의사결정 저장 |
| `rabbitmq` | `rabbitmq:3.13-management` | 5672, 15672 | 메시지 큐 + 관리 UI |
| `api` | `ora-automation` (빌드) | 8000 | REST API 서버 |
| `worker-ceo` | `ora-automation` (빌드) | - | CEO 역할 작업 처리 |
| `worker-pm` | `ora-automation` (빌드) | - | PM 역할 작업 처리 |
| `worker-researcher` | `ora-automation` (빌드) | - | 연구 분석 작업 처리 |
| `worker-engineer` | `ora-automation` (빌드) | - | 엔지니어링 작업 처리 (기본) |
| `worker-qa` | `ora-automation` (빌드) | - | QA/E2E 테스트 작업 처리 |

### 2.2 Docker 이미지 구성

```dockerfile
FROM python:3.11-slim

# 시스템 패키지: ca-certificates, curl, git, make, JRE, Node.js
# Python 패키지: pip install -e . (pyproject.toml 기반)

WORKDIR /workspace/Ora/ora-automation

COPY pyproject.toml Makefile README.md ./
COPY src/ scripts/ automations/ research_reports/ ./
```

- `.venv` 없음 — 시스템 Python에 직접 설치
- 볼륨 마운트 `..:/workspace/Ora` 로 호스트 전체 워크스페이스 접근

### 2.3 환경 변수

#### 공통 (API + Workers)

| 변수 | 값 | 설명 |
|------|---|------|
| `DATABASE_URL` | `postgresql+psycopg://ora:ora@db:5432/ora_automation` | PostgreSQL 접속 |
| `RABBITMQ_URL` | `amqp://guest:guest@rabbitmq:5672/%2F` | RabbitMQ 접속 |
| `RABBITMQ_EXCHANGE` | `ora.automation` | 메인 exchange |
| `RABBITMQ_RETRY_EXCHANGE` | `ora.automation.retry` | 재시도 exchange |
| `RABBITMQ_DLX_EXCHANGE` | `ora.automation.dlx` | Dead Letter exchange |
| `RABBITMQ_QUEUE_PREFIX` | `ora.automation.agent` | 큐 이름 접두사 |
| `ORA_AUTOMATION_ROOT` | `/workspace/Ora/ora-automation` | 자동화 루트 디렉토리 |
| `ORA_AUTOMATION_RUN_OUTPUT` | `.../research_reports/api_runs` | 실행 결과 출력 경로 |
| `PYTHONUNBUFFERED` | `1` | 로그 즉시 출력 |

#### Worker 전용 — LLM / Gemini

| 변수 | 값 | 설명 |
|------|---|------|
| `ORA_RD_LLM_PROVIDER` | `gemini` | LLM 프로바이더 |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini 모델명 |
| `GOOGLE_CLOUD_PROJECT_ID` | `ora-project-474413` | GCP 프로젝트 |
| `GOOGLE_CLOUD_LOCATION` | `asia-northeast3` | 기본 리전 |
| `GOOGLE_APPLICATION_CREDENTIALS` | `/workspace/Ora/ora-automation/google-service-account.json` | 서비스 계정 키 |
| `ORA_RD_GEMINI_DISABLE_VERTEX` | `0` | Vertex AI 사용 여부 |
| `GOOGLE_CLOUD_FALLBACK_LOCATIONS` | `us-central1,us-east1,europe-west1` | 폴백 리전 |
| `EMBEDDING_LOCATION` | `asia-northeast3` | 임베딩 리전 |
| `MCP_GEMINI_MODEL` | `gemini-2.5-flash` | MCP용 Gemini 모델 |

> `GOOGLE_APPLICATION_CREDENTIALS` 경로는 호스트의 볼륨 마운트(`..:/workspace/Ora`)를 통해 접근합니다.
> 호스트의 `ora-automation/google-service-account.json` 파일이 존재해야 합니다.

---

## 3. 실행 방법

### 3.1 기본 명령어

```bash
# 전체 스택 기동 (빌드 포함)
make api-up

# 상태 확인
make api-ps

# 헬스체크
make api-health
# → {"status":"ok","database":"ok","queue":"rabbitmq",...}

# 로그 확인 (실시간)
make api-logs

# 중지
make api-down

# 중지 + DB 볼륨 삭제 (초기화)
make api-reset
```

### 3.2 API로 R&D 파이프라인 실행

```bash
# 1. Orchestration 생성 (비동기)
curl -s -X POST http://localhost:8000/api/v1/orchestrations \
  -H "Content-Type: application/json" \
  -d '{
    "user_prompt": "Ora 앱 전략 분석",
    "target": "run-cycle",
    "env": {
      "TOP": "6",
      "DEBATE_ROUNDS": "2",
      "VERSION_TAG": "V10"
    }
  }' | python3 -m json.tool

# → { "id": "abc-123-...", "status": "queued", ... }

# 2. 상태 폴링
curl -s http://localhost:8000/api/v1/orchestrations/{run_id} | python3 -m json.tool

# 3. 이벤트 로그 조회
curl -s http://localhost:8000/api/v1/orchestrations/{run_id}/events | python3 -m json.tool

# 4. 취소
curl -s -X POST http://localhost:8000/api/v1/orchestrations/{run_id}/cancel
```

### 3.3 Docker 단독 실행 (API 없이)

```bash
# 1회 분석
make docker-run

# run-cycle 실행
make docker-run-cycle

# 반복 실행
make docker-run-loop RUN_CYCLES=3
```

---

## 4. Makefile — Python 경로 자동 감지

Docker 컨테이너에는 `.venv`가 없습니다. LLM 커맨드의 Python 경로가 자동으로 조정됩니다:

```makefile
LLM_DELIBERATION_CMD ?= $(if $(shell .venv/bin/python --version 2>/dev/null),.venv/bin/python,python3) scripts/llm_round_openai.py
LLM_CONSENSUS_CMD   ?= $(if $(shell .venv/bin/python --version 2>/dev/null),.venv/bin/python,python3) scripts/llm_round_openai.py
```

| 환경 | `.venv/bin/python --version` | 선택되는 경로 |
|------|-----|------|
| 로컬 (macOS) | `Python 3.10.x` (성공) | `.venv/bin/python` |
| Docker 컨테이너 | 실행 실패 (macOS 바이너리 또는 부재) | `python3` |

> 호스트의 `.venv`가 볼륨 마운트로 컨테이너에 노출되지만, macOS 바이너리이므로 Linux에서 실행 불가합니다.
> `$(wildcard)` 대신 `$(shell ... --version)`을 사용하여 **실행 가능 여부**를 판단합니다.

---

## 5. API 엔드포인트 레퍼런스

| Method | Path | 설명 | 응답 |
|--------|------|------|------|
| `GET` | `/health` | 헬스체크 (DB, Queue, LLM 상태) | 200 |
| `POST` | `/api/v1/orchestrations` | 새 실행 생성 | 202 |
| `GET` | `/api/v1/orchestrations` | 실행 목록 (페이지네이션) | 200 |
| `GET` | `/api/v1/orchestrations/{id}` | 실행 상태 조회 | 200 |
| `GET` | `/api/v1/orchestrations/{id}/events` | 이벤트 로그 | 200 |
| `GET` | `/api/v1/orchestrations/{id}/decision` | 의사결정 메타데이터 | 200 |
| `POST` | `/api/v1/orchestrations/{id}/cancel` | 취소 요청 | 200 |
| `POST` | `/api/v1/orchestrations/{id}/pause` | 일시정지 요청 | 200 |
| `POST` | `/api/v1/orchestrations/{id}/resume` | 재개 요청 | 200 |
| `POST` | `/api/v1/plan` | LLM 기반 실행 계획 생성 | 200 |
| `POST` | `/api/v1/orchestrations/from-plan` | 계획 기반 실행 생성 | 202 |

### 5.1 OrchestrationRunCreate 스키마

```json
{
  "user_prompt": "string (필수)",
  "target": "run-cycle | run-direct | run-loop | ...",
  "env": { "TOP": "6", "DEBATE_ROUNDS": "2" },
  "dry_run": false,
  "timeout_seconds": 600,
  "agent_role": "engineer",
  "max_attempts": 3,
  "pipeline_stages": "analysis,deliberation,execution",
  "decision": { "owner": "...", "rationale": "..." }
}
```

### 5.2 실행 상태 (Run Status)

```
queued → running → success
                 → error → (retry) → queued
                         → (dlq)   → 종료
queued → paused → running (resume)
queued → cancelled
running → cancelled
```

---

## 6. 재시도 및 Dead Letter 처리

### 6.1 재시도 흐름

```
Worker 실행 실패 (should_retry=true)
    │
    ▼
publish_retry(run_id, role, delay_seconds)
    │
    ▼
ora.automation.agent.{role}.retry  (TTL = delay_seconds × 1000ms)
    │  TTL 만료
    ▼
x-dead-letter-exchange → ora.automation (main)
    │
    ▼
ora.automation.agent.{role}  ← 다시 Worker가 소비
```

- `max_attempts` 도달 시 DLQ로 전환
- 기본 `PIPELINE_RETRY_MAX=2`, `PIPELINE_RETRY_DELAY=1.2s`

### 6.2 Dead Letter 큐

DLQ에 도달한 메시지는 자동 재처리되지 않습니다. 수동 확인이 필요합니다:

```bash
# RabbitMQ Management UI
open http://localhost:15672
# guest / guest

# DLQ 메시지 확인
# Queues → ora.automation.agent.{role}.dlq → Get Messages
```

### 6.3 Stale Run 복구

Worker는 주기적으로 (heartbeat 간격 × 2) stale run을 감지합니다:

- `locked_at`이 `stale_timeout_seconds`보다 오래된 run → 자동 재발행 또는 DLQ 전송
- Worker 비정상 종료 시에도 작업이 유실되지 않음

---

## 7. 트러블슈팅

### 7.1 `.venv/bin/python: not found`

**증상:** Worker 로그에서 `make run-cycle` 실행 시 `.venv/bin/python` 파일을 찾을 수 없음

**원인:** Makefile 기본값이 `.venv/bin/python`을 하드코딩하고 있었음

**해결:** Makefile의 `$(shell .venv/bin/python --version 2>/dev/null)` 조건부 로직으로 자동 폴백

### 7.2 LLM 호출 실패 (Worker)

**증상:** Worker에서 Gemini API 호출 시 인증 오류 또는 환경변수 미설정

**확인:**
```bash
# Worker 환경변수 확인
docker exec ora-automation-worker-engineer env | grep -E 'GEMINI|GOOGLE|ORA_RD_LLM'

# 서비스 계정 파일 존재 확인
docker exec ora-automation-worker-engineer \
  ls -la /workspace/Ora/ora-automation/google-service-account.json
```

**원인:** `docker-compose.yml`에 LLM 환경변수 누락

**해결:** worker-ceo에 `&worker-env` YAML anchor로 정의, 나머지 worker는 `<<: *worker-env`로 상속

### 7.3 DB 연결 실패

```bash
# DB 헬스체크
docker exec ora-automation-db pg_isready -U ora -d ora_automation

# DB 로그
docker compose logs db

# DB 초기화 (데이터 삭제)
make api-reset
```

### 7.4 RabbitMQ 연결 실패

```bash
# RabbitMQ 헬스체크
docker exec ora-automation-rabbitmq rabbitmq-diagnostics -q ping

# 큐 상태 확인
docker exec ora-automation-rabbitmq rabbitmqctl list_queues name messages consumers

# Management UI
open http://localhost:15672  # guest / guest
```

### 7.5 Worker 로그 확인

```bash
# 전체 Worker 로그
docker compose logs -f worker-ceo worker-pm worker-researcher worker-engineer worker-qa

# 특정 Worker
docker compose logs -f worker-engineer --tail=100

# Worker 내부에서 직접 실행 테스트
docker exec -it ora-automation-worker-engineer bash
cd /workspace/Ora/ora-automation
make -n run-cycle  # dry-run으로 커맨드 확인
```

### 7.6 포트 충돌

| 서비스 | 포트 | 충돌 시 |
|--------|------|---------|
| PostgreSQL | 5432 | 로컬 PostgreSQL 중지 또는 포트 변경 |
| RabbitMQ | 5672 / 15672 | 로컬 RabbitMQ 중지 |
| API | 8000 | `docker-compose.yml`에서 포트 매핑 변경 |

---

## 8. 운영 체크리스트

### 배포 전

- [ ] `google-service-account.json` 파일이 `ora-automation/` 디렉토리에 존재
- [ ] Docker Desktop 실행 중
- [ ] 포트 5432, 5672, 8000, 15672 사용 가능
- [ ] 디스크 여유 공간 확인 (이미지 빌드 + 리포트 출력)

### 기동 후

- [ ] `make api-health` → `{"status":"ok"}`
- [ ] `make api-ps` → 8개 컨테이너 모두 `Up`
- [ ] RabbitMQ UI (`:15672`) 에서 5개 큐 생성 확인
- [ ] Worker 로그에 `Connection workflow succeeded` 메시지 확인

### 정기 관리

- [ ] DLQ 메시지 확인 및 처리 (RabbitMQ UI → Queues → `*.dlq`)
- [ ] 오래된 실행 결과 정리: `research_reports/api_runs/`
- [ ] DB 볼륨 크기 모니터링
- [ ] `docker compose logs` 로 에러 패턴 확인
