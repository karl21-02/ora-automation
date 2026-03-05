# API Reference / API 레퍼런스

ora-automation FastAPI 서버의 전체 엔드포인트 문서입니다.

**Base URL**: `http://localhost:8000`

---

## Table of Contents / 목차

- [Health Check](#health-check)
- [Chat / 채팅](#chat--채팅)
- [Conversations / 대화](#conversations--대화)
- [Orchestrations / 오케스트레이션](#orchestrations--오케스트레이션)
- [LLM Planner](#llm-planner)
- [Reports / 리포트](#reports--리포트)
- [Projects / 프로젝트](#projects--프로젝트)
- [Schemas / 스키마](#schemas--스키마)
- [Error Handling / 에러 처리](#error-handling--에러-처리)

---

## Health Check

### `GET /health`

서비스 상태를 확인합니다. DB 연결 및 설정 정보를 반환합니다.

**Response**

```json
{
  "status": "ok",
  "database": "ok",
  "queue": "rabbitmq",
  "llm_planner_configured": true,
  "automation_root": "/workspace/Ora/ora-automation",
  "allowed_targets": ["run", "run-cycle", "run-loop", "e2e-service", ...],
  "agent_roles": ["ceo", "pm", "researcher", "engineer", "qa"]
}
```

---

## Chat / 채팅

Gemini 기반 대화형 인터페이스입니다. 자연어로 오케스트레이션 실행 계획을 생성합니다.

### `POST /api/v1/chat`

비스트리밍 채팅 요청. Gemini를 호출하고 전체 응답을 한 번에 반환합니다.

**Request Body**: [`ChatRequest`](#chatrequest)

```json
{
  "message": "AI 서버 E2E 테스트를 실행해줘",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "history": [
    {"role": "user", "content": "안녕하세요"},
    {"role": "assistant", "content": "안녕하세요! 무엇을 도와드릴까요?"}
  ]
}
```

**Response**: [`ChatResponse`](#chatresponse)

```json
{
  "reply": "AI 서버 E2E 테스트를 준비하겠습니다.",
  "plan": {
    "target": "e2e-service",
    "env": {"SERVICE": "ai"},
    "label": ""
  },
  "plans": null,
  "choices": null,
  "project_select": null,
  "run_id": null
}
```

**Status Codes**

| Code | Description / 설명 |
|---|---|
| 200 | 성공 |
| 503 | Gemini LLM 호출 실패 |

---

### `POST /api/v1/chat/stream`

SSE(Server-Sent Events) 스트리밍 채팅 요청. 토큰 단위로 응답을 실시간 전송합니다.

**Request Body**: [`ChatRequest`](#chatrequest) (동일)

**Response**: `text/event-stream`

스트리밍 이벤트 형식:

```
# 토큰 전송 (반복)
data: {"type": "token", "content": "안녕"}

# 완료 (plan/choices 포함 가능)
data: {"type": "done", "full_reply": "안녕하세요! 무엇을 도와드릴까요?", "plan": {...}}

# 종료 시그널
data: [DONE]

# 에러 발생 시
data: {"type": "error", "content": "LLM call failed: ..."}
```

**`done` 이벤트 필드**:

| Field | Type | Description / 설명 |
|---|---|---|
| `type` | `"done"` | 이벤트 타입 |
| `full_reply` | `string` | 전체 응답 텍스트 (JSON 블록 제거됨) |
| `plan` | `object?` | 단일 실행 계획 |
| `plans` | `array?` | 다중 실행 계획 |
| `choices` | `array?` | 사용자 선택지 |
| `project_select` | `array?` | 프로젝트 선택 UI 데이터 |

---

## Conversations / 대화

DB에 저장되는 대화 관리 CRUD API입니다.

### `GET /api/v1/conversations`

대화 목록을 조회합니다 (최신순 정렬).

**Query Parameters**

| Parameter | Type | Default | Description / 설명 |
|---|---|---|---|
| `limit` | `int` | `50` | 조회 수 (1~200) |

**Response**: [`ConversationList`](#conversationlist)

```json
{
  "items": [
    {
      "id": "550e8400-...",
      "title": "AI 서버 테스트",
      "created_at": "2025-03-05T10:00:00Z",
      "updated_at": "2025-03-05T10:30:00Z"
    }
  ],
  "total": 15
}
```

---

### `POST /api/v1/conversations`

새 대화를 생성합니다.

**Request Body**: [`ConversationCreate`](#conversationcreate)

```json
{
  "id": "custom-id-optional",
  "title": "R&D 분석 대화"
}
```

**Response** (201): [`ConversationRead`](#conversationread)

---

### `GET /api/v1/conversations/{conversation_id}`

대화 상세 조회 (메시지 포함).

**Response**: [`ConversationDetail`](#conversationdetail)

```json
{
  "id": "550e8400-...",
  "title": "AI 서버 테스트",
  "created_at": "2025-03-05T10:00:00Z",
  "updated_at": "2025-03-05T10:30:00Z",
  "messages": [
    {
      "id": 1,
      "conversation_id": "550e8400-...",
      "role": "user",
      "content": "AI 서버 E2E 테스트 실행",
      "plan": null,
      "run_id": null,
      "created_at": "2025-03-05T10:00:00Z"
    },
    {
      "id": 2,
      "conversation_id": "550e8400-...",
      "role": "assistant",
      "content": "준비하겠습니다.",
      "plan": {"target": "e2e-service", "env": {"SERVICE": "ai"}},
      "run_id": null,
      "created_at": "2025-03-05T10:00:01Z"
    }
  ]
}
```

**Status Codes**: `200` 성공, `404` 대화를 찾을 수 없음

---

### `PATCH /api/v1/conversations/{conversation_id}`

대화 제목을 수정합니다.

**Request Body**: [`ConversationCreate`](#conversationcreate)

```json
{
  "title": "새 제목"
}
```

**Response**: [`ConversationRead`](#conversationread)

---

### `DELETE /api/v1/conversations/{conversation_id}`

대화와 소속 메시지를 모두 삭제합니다.

**Response**: `204 No Content`

---

## Orchestrations / 오케스트레이션

R&D 분석, E2E 테스트, QA 프로그램 등의 실행을 관리합니다.

### `POST /api/v1/orchestrations`

새 오케스트레이션 실행을 생성하고 RabbitMQ에 enqueue합니다.

**Request Body**: [`OrchestrationRunCreate`](#orchestrationruncreate)

```json
{
  "user_prompt": "V10 R&D 리서치 1회 실행",
  "target": "run-cycle",
  "env": {
    "RUN_CYCLES": "1",
    "VERIFY_ROUNDS": "3",
    "TOP": "6"
  }
}
```

**Response** (202): [`OrchestrationRunRead`](#orchestrationrunread)

**Status Codes**

| Code | Description / 설명 |
|---|---|
| 202 | 실행 생성 및 큐 enqueue 성공 |
| 503 | RabbitMQ enqueue 실패 |

---

### `POST /api/v1/orchestrations/batch`

여러 실행을 한 번에 생성합니다 (다중 프로젝트 분석 등).

**Request Body**: [`BatchRunCreate`](#batchruncreate)

```json
{
  "user_prompt": "전체 프로젝트 R&D 분석",
  "plans": [
    {"target": "run-cycle", "env": {"FOCUS": "인증 시스템"}, "label": "OraServer"},
    {"target": "run-cycle", "env": {"FOCUS": "UI 성능"}, "label": "OraWebApp"}
  ]
}
```

**Response** (202): [`BatchRunResponse`](#batchrunresponse)

---

### `GET /api/v1/orchestrations`

실행 목록을 조회합니다 (최신순).

**Query Parameters**

| Parameter | Type | Default | Description / 설명 |
|---|---|---|---|
| `limit` | `int` | `20` | 조회 수 (1~200) |

**Response**: [`OrchestrationRunList`](#orchestrationrunlist)

---

### `GET /api/v1/orchestrations/{run_id}`

실행 상세를 조회합니다.

**Response**: [`OrchestrationRunRead`](#orchestrationrunread)

**Status Codes**: `200` 성공, `404` 실행을 찾을 수 없음

---

### `GET /api/v1/orchestrations/{run_id}/events`

실행의 stage/event 로그를 조회합니다.

**Query Parameters**

| Parameter | Type | Default | Description / 설명 |
|---|---|---|---|
| `limit` | `int` | `100` | 조회 수 (1~500) |

**Response**: [`OrchestrationEventRead[]`](#orchestrationeventread)

---

### `GET /api/v1/orchestrations/{run_id}/decision`

실행에 연결된 의사결정 객체를 조회합니다.

**Response**: [`DecisionRead`](#decisionread)

**Status Codes**: `200` 성공, `404` 실행 또는 의사결정을 찾을 수 없음

---

### `POST /api/v1/orchestrations/{run_id}/pause`

실행을 일시정지 요청합니다.

**Response**: [`RunActionResponse`](#runactionresponse)

---

### `POST /api/v1/orchestrations/{run_id}/resume`

일시정지된 실행을 재개합니다 (queued 상태로 전환 후 재-enqueue).

**Response**: [`RunActionResponse`](#runactionresponse)

---

### `POST /api/v1/orchestrations/{run_id}/cancel`

실행을 취소 요청합니다.

**Response**: [`RunActionResponse`](#runactionresponse)

---

## LLM Planner

자연어를 실행 계획으로 변환하는 LLM 플래너 API입니다.
`ORA_AUTOMATION_LLM_PLANNER_CMD` 환경변수가 설정되어야 활성화됩니다.

### `POST /api/v1/plan`

자연어 프롬프트로 실행 계획만 생성합니다 (실행하지 않음).

**Request Body**: [`LlmPlanRequest`](#llmplanrequest)

```json
{
  "prompt": "B2C 서비스 E2E를 playwright로 한 번 실행하고 실패하면 재시도 전략을 포함해 계획해줘",
  "context": {"service": "b2c"},
  "timeout_seconds": 30
}
```

**Response**: [`LlmPlanResponse`](#llmplanresponse)

```json
{
  "target": "e2e-service",
  "agent_role": "qa",
  "env": {"SERVICE": "b2c", "E2E_TOOL": "playwright"},
  "max_attempts": 2,
  "pipeline_stages": ["analysis", "execution"],
  "execution_command": null,
  "rollback_command": null,
  "decision": null,
  "planner_metadata": {}
}
```

---

### `POST /api/v1/orchestrations/from-plan`

계획을 생성하고 즉시 실행합니다.

**Request Body**: [`LlmPlanRunRequest`](#llmplanrunrequest)

```json
{
  "prompt": "OraServer와 OraAiServer를 포함한 R&D 리서치 run-cycle 1회 실행",
  "context": {"services": ["telecom", "ai"]},
  "idempotency_key": "plan-run-001",
  "dry_run": false,
  "env_overrides": {}
}
```

**Response** (202): [`OrchestrationRunRead`](#orchestrationrunread)

---

## Reports / 리포트

연구 보고서 파일을 조회/다운로드합니다.

### `GET /api/v1/reports`

리포트 목록을 조회합니다 (최신순, 최대 200개).

**Response**: [`ReportListItem[]`](#reportlistitem)

```json
[
  {
    "filename": "V10_자동회차/20250305_103000/rd_research_report.md",
    "created_at": "2025-03-05T10:30:00Z",
    "size_bytes": 45000,
    "report_type": "markdown"
  }
]
```

---

### `GET /api/v1/reports/{filename}`

리포트 파일을 다운로드합니다.

**Path Parameters**

| Parameter | Description / 설명 |
|---|---|
| `filename` | 리포트 파일 경로 (예: `V10_자동회차/20250305/report.md`) |

**Response**: 파일 내용 (`text/markdown` 또는 `application/json`)

**Status Codes**: `200` 성공, `400` 잘못된 파일명 (`..` 포함), `404` 파일 없음

---

## Projects / 프로젝트

Ora 워크스페이스의 하위 프로젝트를 스캔합니다.

### `GET /api/v1/projects`

프로젝트 목록을 조회합니다 (60초 캐싱).

**Response**: [`ProjectInfo[]`](#projectinfo)

```json
[
  {
    "name": "OraAiServer",
    "path": "/workspace/Ora/OraAiServer",
    "has_makefile": true,
    "has_dockerfile": true,
    "description": ""
  },
  {
    "name": "OraWebAppFrontend",
    "path": "/workspace/Ora/OraWebAppFrontend",
    "has_makefile": false,
    "has_dockerfile": true,
    "description": ""
  }
]
```

---

## Schemas / 스키마

### ChatRequest

| Field | Type | Required | Description / 설명 |
|---|---|---|---|
| `message` | `string` | Yes | 사용자 메시지 (1~4000자) |
| `conversation_id` | `string?` | No | 대화 ID (없으면 자동 생성) |
| `history` | `ChatMessage[]` | No | 이전 대화 히스토리 |

### ChatMessage

| Field | Type | Description / 설명 |
|---|---|---|
| `role` | `"user" \| "assistant"` | 메시지 역할 |
| `content` | `string` | 메시지 내용 (1~8000자) |

### ChatResponse

| Field | Type | Description / 설명 |
|---|---|---|
| `reply` | `string` | 어시스턴트 응답 텍스트 |
| `plan` | `ChatPlan?` | 단일 실행 계획 (plan_ready=true일 때) |
| `plans` | `ChatPlan[]?` | 다중 실행 계획 |
| `choices` | `ChatChoice[]?` | 사용자 선택지 |
| `project_select` | `ProjectInfo[]?` | 프로젝트 선택 UI 데이터 |
| `run_id` | `string?` | 생성된 실행 ID |

### ChatPlan

| Field | Type | Description / 설명 |
|---|---|---|
| `target` | `string` | Make 타깃 (예: `run-cycle`, `e2e-service`) |
| `env` | `dict[str, str]` | 환경변수 |
| `label` | `string` | 라벨 (다중 계획 시 구분용) |

### ChatChoice

| Field | Type | Description / 설명 |
|---|---|---|
| `label` | `string` | 선택지 라벨 |
| `description` | `string` | 설명 |
| `value` | `string` | 선택 시 전송되는 값 |

### ProjectInfo

| Field | Type | Description / 설명 |
|---|---|---|
| `name` | `string` | 프로젝트명 |
| `path` | `string` | 절대 경로 |
| `has_makefile` | `bool` | Makefile 존재 여부 |
| `has_dockerfile` | `bool` | Dockerfile/docker-compose.yml 존재 여부 |
| `description` | `string` | 설명 |

### OrchestrationRunCreate

| Field | Type | Required | Description / 설명 |
|---|---|---|---|
| `user_prompt` | `string` | Yes | 사용자 요청 (1~4000자) |
| `target` | `string?` | No | Make 타깃 (미지정 시 기본값 `run-cycle`) |
| `env` | `dict[str, str]` | No | 환경변수 |
| `dry_run` | `bool` | No | 드라이런 모드 (default: `false`) |
| `timeout_seconds` | `float?` | No | 타임아웃 (1~86400초) |
| `idempotency_key` | `string?` | No | 멱등성 키 (1~128자) |
| `agent_role` | `string?` | No | 에이전트 역할 (ceo/pm/researcher/engineer/qa) |
| `max_attempts` | `int?` | No | 최대 시도 횟수 (1~20) |
| `pipeline_stages` | `string[]` | No | 파이프라인 단계 (default: `["analysis", "deliberation", "execution"]`) |
| `execution_command` | `string?` | No | 커스텀 실행 명령어 |
| `rollback_command` | `string?` | No | 롤백 명령어 |
| `decision` | `DecisionCreate?` | No | 의사결정 객체 |

### OrchestrationRunRead

| Field | Type | Description / 설명 |
|---|---|---|
| `id` | `string` | 실행 UUID |
| `idempotency_key` | `string?` | 멱등성 키 |
| `user_prompt` | `string` | 사용자 요청 |
| `target` | `string` | Make 타깃 |
| `agent_role` | `string` | 에이전트 역할 |
| `command` | `string` | 실행 명령어 |
| `rollback_command` | `string?` | 롤백 명령어 |
| `env` | `dict` | 환경변수 |
| `pipeline_stages` | `list` | 파이프라인 단계 |
| `current_stage` | `string?` | 현재 단계 |
| `status` | `string` | 상태 (`queued`, `running`, `completed`, `error`, `cancelled`, `paused`, `dry-run`) |
| `fail_label` | `string` | 실패 라벨 |
| `attempt_count` | `int` | 현재 시도 횟수 |
| `max_attempts` | `int` | 최대 시도 횟수 |
| `next_retry_at` | `datetime?` | 다음 재시도 시각 |
| `pause_requested` | `bool` | 일시정지 요청 여부 |
| `cancel_requested` | `bool` | 취소 요청 여부 |
| `locked_by` | `string?` | 락 보유 워커 |
| `locked_at` | `datetime?` | 락 획득 시각 |
| `heartbeat_at` | `datetime?` | 마지막 하트비트 |
| `decision_id` | `string?` | 연결된 의사결정 ID |
| `exit_code` | `int?` | 종료 코드 |
| `stdout_path` | `string?` | stdout 파일 경로 |
| `stderr_path` | `string?` | stderr 파일 경로 |
| `error_message` | `string?` | 에러 메시지 |
| `created_at` | `datetime` | 생성 시각 |
| `updated_at` | `datetime` | 수정 시각 |
| `started_at` | `datetime?` | 시작 시각 |
| `finished_at` | `datetime?` | 완료 시각 |

### OrchestrationRunList

| Field | Type | Description / 설명 |
|---|---|---|
| `items` | `OrchestrationRunRead[]` | 실행 목록 |
| `total` | `int` | 전체 수 |

### OrchestrationEventRead

| Field | Type | Description / 설명 |
|---|---|---|
| `id` | `int` | 이벤트 ID |
| `run_id` | `string` | 실행 ID |
| `stage` | `string` | 파이프라인 단계 |
| `event_type` | `string` | 이벤트 유형 |
| `message` | `string` | 이벤트 메시지 |
| `payload` | `dict` | 추가 데이터 |
| `created_at` | `datetime` | 생성 시각 |

### DecisionCreate

| Field | Type | Required | Description / 설명 |
|---|---|---|---|
| `owner` | `string` | Yes | 의사결정 주체 (1~64자) |
| `rationale` | `string` | Yes | 의사결정 근거 (1~8000자) |
| `risk` | `string` | Yes | 리스크 분석 (1~8000자) |
| `next_action` | `string` | Yes | 다음 액션 (1~8000자) |
| `due` | `datetime?` | No | 기한 |
| `payload` | `dict` | No | 추가 데이터 |

### DecisionRead

| Field | Type | Description / 설명 |
|---|---|---|
| `id` | `string` | 의사결정 UUID |
| `run_id` | `string?` | 연결된 실행 ID |
| `owner` | `string` | 의사결정 주체 |
| `rationale` | `string` | 근거 |
| `risk` | `string` | 리스크 |
| `next_action` | `string` | 다음 액션 |
| `due` | `datetime?` | 기한 |
| `payload` | `dict` | 추가 데이터 |
| `created_at` | `datetime` | 생성 시각 |

### RunActionResponse

| Field | Type | Description / 설명 |
|---|---|---|
| `run_id` | `string` | 실행 ID |
| `status` | `string` | 현재 상태 |
| `pause_requested` | `bool` | 일시정지 요청 여부 |
| `cancel_requested` | `bool` | 취소 요청 여부 |

### BatchRunCreate

| Field | Type | Description / 설명 |
|---|---|---|
| `user_prompt` | `string` | 사용자 요청 (1~4000자) |
| `plans` | `ChatPlan[]` | 실행 계획 목록 |

### BatchRunResponse

| Field | Type | Description / 설명 |
|---|---|---|
| `runs` | `OrchestrationRunRead[]` | 생성된 실행 목록 |

### LlmPlanRequest

| Field | Type | Required | Description / 설명 |
|---|---|---|---|
| `prompt` | `string` | Yes | 자연어 프롬프트 (1~8000자) |
| `context` | `dict` | No | 추가 컨텍스트 |
| `timeout_seconds` | `float?` | No | 타임아웃 (1~300초) |

### LlmPlanResponse

| Field | Type | Description / 설명 |
|---|---|---|
| `target` | `string` | Make 타깃 |
| `agent_role` | `string?` | 에이전트 역할 |
| `env` | `dict[str, str]` | 환경변수 |
| `max_attempts` | `int?` | 최대 시도 횟수 |
| `pipeline_stages` | `string[]` | 파이프라인 단계 |
| `execution_command` | `string?` | 실행 명령어 |
| `rollback_command` | `string?` | 롤백 명령어 |
| `decision` | `dict?` | 의사결정 |
| `planner_metadata` | `dict` | 플래너 메타데이터 |

### LlmPlanRunRequest

| Field | Type | Required | Description / 설명 |
|---|---|---|---|
| `prompt` | `string` | Yes | 자연어 프롬프트 (1~8000자) |
| `context` | `dict` | No | 추가 컨텍스트 |
| `timeout_seconds` | `float?` | No | 타임아웃 (1~300초) |
| `dry_run` | `bool` | No | 드라이런 모드 |
| `idempotency_key` | `string?` | No | 멱등성 키 |
| `env_overrides` | `dict[str, str]` | No | 환경변수 오버라이드 |

### ReportListItem

| Field | Type | Description / 설명 |
|---|---|---|
| `filename` | `string` | 파일 상대 경로 |
| `created_at` | `datetime` | 생성(수정) 시각 |
| `size_bytes` | `int` | 파일 크기 |
| `report_type` | `string` | `"markdown"` 또는 `"json"` |

### ConversationRead

| Field | Type | Description / 설명 |
|---|---|---|
| `id` | `string` | 대화 UUID |
| `title` | `string` | 제목 |
| `created_at` | `datetime` | 생성 시각 |
| `updated_at` | `datetime` | 수정 시각 |

### ConversationDetail

`ConversationRead` + 메시지 목록

| Field | Type | Description / 설명 |
|---|---|---|
| `messages` | `ChatMessageRead[]` | 대화 메시지 목록 (시간순) |

### ConversationCreate

| Field | Type | Description / 설명 |
|---|---|---|
| `id` | `string?` | 커스텀 ID (미지정 시 UUID 자동 생성) |
| `title` | `string` | 제목 |

### ConversationList

| Field | Type | Description / 설명 |
|---|---|---|
| `items` | `ConversationRead[]` | 대화 목록 |
| `total` | `int` | 전체 수 |

### ChatMessageRead

| Field | Type | Description / 설명 |
|---|---|---|
| `id` | `int` | 메시지 ID |
| `conversation_id` | `string` | 대화 ID |
| `role` | `string` | `"user"` 또는 `"assistant"` |
| `content` | `string` | 메시지 내용 |
| `plan` | `dict?` | 실행 계획 (assistant 메시지) |
| `run_id` | `string?` | 연결된 실행 ID |
| `created_at` | `datetime` | 생성 시각 |

---

## Error Handling / 에러 처리

모든 에러는 아래 형식으로 반환됩니다:

```json
{
  "detail": "에러 설명 메시지"
}
```

### Common Status Codes / 공통 상태 코드

| Code | Description / 설명 |
|---|---|
| `200` | 성공 |
| `201` | 리소스 생성 성공 |
| `202` | 비동기 작업 수락 (큐 enqueue 성공) |
| `204` | 삭제 성공 (응답 본문 없음) |
| `400` | 잘못된 요청 (유효성 검사 실패) |
| `404` | 리소스를 찾을 수 없음 |
| `422` | 요청 본문 파싱 실패 (Pydantic 검증 오류) |
| `503` | 외부 서비스 실패 (Gemini LLM, RabbitMQ) |

### Allowed Targets / 허용 타깃

기본 허용 타깃 목록 (`ORA_AUTOMATION_ALLOWED_TARGETS`로 변경 가능):

```
run, run-direct, run-cycle, run-loop, run-cycle-deep, run-single,
e2e-service, e2e-service-all, qa-program, qa-program-loop, verify-sources
```

### Idempotency / 멱등성

`idempotency_key`를 지정하면 동일한 키로 중복 실행을 방지합니다. 이미 존재하는 키로 요청하면 기존 실행을 반환합니다.
