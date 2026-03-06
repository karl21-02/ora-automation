# CLAUDE.md — ora-automation

This file provides context for AI assistants (Claude Code, Copilot, Cursor, etc.) working on this codebase.

## What is this project?

**ora-automation** is a multi-agent R&D research orchestrator. It scans a workspace of projects, runs multi-agent deliberation (scoring, debate, consensus), and produces structured research reports — all orchestrated via CLI, REST API, or a chatbot UI.

Key capabilities:
- **R&D Analysis**: Multi-agent scoring and deliberation on project strategies
- **E2E Testing**: Orchestrated Cypress/Playwright test execution across multiple services
- **QA Program**: Automated QA pipeline with reporting
- **Chatbot**: Gemini-powered assistant that understands user intent and triggers orchestration runs
- **Natural Language Scheduling**: Chat-based scheduling — "매일 아침 9시에 보안 트렌드 분석해줘" → ScheduledJob 자동 생성

## Architecture

```
┌─────────────┐     ┌──────────┐     ┌────────────┐
│  React UI   │────>│ FastAPI   │────>│ PostgreSQL │
│  (Vite)     │     │  :8000    │     │  :5432     │
└─────────────┘     └────┬─────┘     └────────────┘
                         │
                    ┌────┴─────┐
                    │ RabbitMQ │      ┌────────────┐
                    │  :5672   │      │ Notion API │
                    └────┬─────┘      └─────┬──────┘
              ┌──────────┼──────────┐       │
              ▼          ▼          ▼       │
         worker-ceo  worker-pm  worker-*    │
              │                             │
              ▼                             │
         ┌──────────────┐    ┌──────────────┘
         │  Scheduler   │───>│ auto-publish
         │ (APScheduler)│    │ on completion
         └──────────────┘    └──────────────
```

### Autonomous Pipeline

```
Scheduler (poll DB) ──> create_run() ──> RabbitMQ ──> Worker
                                                        │
                                                   run completed?
                                                   & auto_publish?
                                                        │
                                                        ▼
                                                  Notion Publisher
                                                  (report → pages)
```

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, SQLAlchemy 2, Pydantic 2, RabbitMQ (pika), APScheduler
- **Frontend**: React 19, TypeScript 5.9, Vite 7
- **Database**: PostgreSQL 16
- **LLM**: Google Gemini (Vertex AI) — primary; OpenAI — fallback scripts
- **External**: Notion API (report publishing)
- **Infrastructure**: Docker Compose (8 services), Make

## Project Structure

```
ora-automation/
├── src/
│   ├── ora_rd_orchestrator/      # Core orchestration engine (12+ modules)
│   │   ├── pipeline.py           # Main entry: generate_report()
│   │   ├── engine.py             # Legacy monolith (backward compat)
│   │   ├── cli.py                # CLI entry point
│   │   ├── config.py             # Constants, env vars, profiles
│   │   ├── types.py              # All dataclasses
│   │   ├── llm_client.py         # run_llm_command() subprocess wrapper
│   │   ├── personas.py           # PersonaRegistry (20 YAML personas)
│   │   ├── workspace.py          # File scanning, analyze_workspace()
│   │   ├── topic_discovery.py    # LLM topic discovery + legacy fallback
│   │   ├── scoring.py            # LLM scoring + legacy formula
│   │   ├── deliberation.py       # Multi-round debate
│   │   ├── consensus.py          # Final consensus with hard gates
│   │   ├── research.py           # ArXiv/Crossref/OpenAlex clients
│   │   ├── report_builder.py     # Markdown + JSON report gen
│   │   └── personas/             # 24 YAML agent definitions (Toss silo structure)
│   │
│   └── ora_automation_api/       # FastAPI backend
│       ├── main.py               # App entry, router registration, DDL migration
│       ├── chat_router.py        # Chat + conversations + reports + projects
│       ├── notion_client.py      # Notion REST API client (retry, backoff)
│       ├── notion_publisher.py   # Report JSON → Notion pages/blocks
│       ├── notion_router.py      # Notion endpoints (setup, publish, sync, status)
│       ├── scheduler.py          # APScheduler DB-polling job scheduler
│       ├── scheduler_router.py   # Scheduler CRUD API
│       ├── scheduling_handler.py # NL scheduling → ScheduledJob (validate + create)
│       ├── schemas.py            # Pydantic request/response models
│       ├── models.py             # SQLAlchemy ORM (+ NotionSyncState, ScheduledJob)
│       ├── database.py           # DB session management
│       ├── config.py             # API settings (env vars)
│       ├── service.py            # Run execution logic + auto-publish hook
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
│       │   └── SchedulerPanel.tsx # Scheduled job management UI
│       ├── lib/api.ts            # Typed API client
│       └── types.ts              # Shared TypeScript types
│
├── scripts/                      # Shell + Python utilities
├── automations/                  # Orchestration config (research, e2e, qa)
├── research_reports/             # Output directory
├── Makefile                      # 30+ targets (primary build tool)
├── docker-compose.yml            # 8-service stack
├── pyproject.toml                # Python package metadata
└── Dockerfile                    # Python 3.11-slim + system deps
```

## Quick Start

```bash
# Python setup
make setup                  # Create .venv + pip install -e .

# Run everything with Docker Compose
make api-up                 # Start all 8 services
make api-logs               # Follow logs
make api-health             # Health check
make api-down               # Stop all

# Frontend dev (local)
make frontend-install       # npm install
make frontend-dev           # vite dev server on :5173

# R&D analysis (local)
make run                    # Single analysis pass
make run-cycle              # Repeating runner with verification
make run-cycle-deep         # Extended scanning + validation
```

## Common Commands

| Command | Description |
|---------|-------------|
| `make run` | Single R&D analysis (TOP=6, DEBATE_ROUNDS=2) |
| `make run-cycle` | Repeating runner with source verification |
| `make run-deep` | Extended scan (TOP=8, MAX_FILES=2400) |
| `make run-focus FOCUS=<label>` | Focused strategy analysis |
| `make e2e-service SERVICE=ai` | Service-specific E2E test |
| `make e2e-service-all` | Run all service E2E tests |
| `make qa-program` | Full QA pipeline with report |
| `make api-up` | Docker Compose up (all services) |
| `make api-reset` | Stop + delete DB volume |
| `make verify-sources` | Validate research source URLs |

## Key Patterns

### LLM Fallback
All LLM-dependent modules follow the same pattern:
```python
try:
    result = run_llm_command(cmd, input_data, timeout)  # Try LLM
except Exception:
    result = legacy_hardcoded_logic(input_data)          # Fallback
```

### Persona System (Toss Silo Structure)
- 24 YAML personas in `src/ora_rd_orchestrator/personas/`
- Mission silos: `research_intelligence`, `product_realization`, `platform_infrastructure`, `quality_assurance`, `strategy`, `governance`
- 5 agents added: DataAnalyst, ProductDesigner, ComplianceOfficer, TechLead, GrowthHacker
- UXVoiceDesigner removed (replaced by ProductDesigner)
- ComplianceOfficer: governance gate (risk ≥ 7.0 + feasibility < 4.0 → veto)
- `PersonaRegistry.to_agent_definitions()` bridges to legacy format
- See `docs/TOSS_REORG_PLAN.md` for full reorganization plan

### Idempotent Sync (Notion)
- `notion_sync_state` table tracks all Notion page/DB IDs with `(entity_type, entity_key)` unique constraint
- Setup, publish, sync endpoints all check existing state before creating — safe to call repeatedly
- Entity types: `hub_page`, `reports_db`, `topics_db`, `dashboard_page`, `report`, `topic`

### DB-backed Scheduler
- `scheduled_jobs` table stores job definitions (interval or cron, target, env, enabled flag)
- APScheduler `BackgroundScheduler` polls every N seconds for due jobs
- Each job creates an `OrchestrationRun` via `create_run()` + `publish_run()` — same path as manual API calls
- `auto_publish_notion` flag on job → auto-publishes report to Notion on completion

### Natural Language Scheduling (UPCE Dialog Engine)
- UPCE dialog engine의 `SCHEDULING` 인텐트가 자연어 시간 표현을 cron/interval로 변환
- Stage 1 (Gemini JSON-mode)이 "매일 아침 9시" → `cron_expression: "0 9 * * *"` 직접 추출
- `scheduling_handler.py`가 APScheduler CronTrigger로 LLM 출력을 deterministic 검증
- 확인(confirmation) 시 `ScheduledJob` DB row 생성 → 기존 스케줄러가 자동 실행
- 검증 실패 시 `SLOT_FILLING` 상태로 복귀하여 재입력 유도

### API Endpoints

**Chat & Conversations:**
- `POST /api/v1/chat` — Send message (non-streaming)
- `POST /api/v1/chat/stream` — SSE streaming chat
- `GET/POST/DELETE/PATCH /api/v1/conversations[/{id}]` — CRUD

**Orchestration:**
- `POST /api/v1/orchestrations` — Create run
- `GET /api/v1/orchestrations[/{id}]` — List/get runs
- `POST /api/v1/orchestrations/{id}/{cancel|pause|resume}` — Control

**Reports & Projects:**
- `GET /api/v1/reports` — List research reports
- `GET /api/v1/reports/{filename}` — Download report
- `GET /api/v1/projects` — List Ora sub-projects

**Notion Integration:**
- `POST /api/v1/notion/setup` — Create Hub + DBs in Notion (idempotent)
- `POST /api/v1/notion/publish/{path}` — Publish report to Notion (idempotent)
- `GET /api/v1/notion/status` — Connection & sync status
- `POST /api/v1/notion/sync` — Bulk-publish all unsynced reports

**Scheduler:**
- `POST /api/v1/scheduler/jobs` — Create scheduled job
- `GET /api/v1/scheduler/jobs` — List all jobs
- `GET/PATCH/DELETE /api/v1/scheduler/jobs/{id}` — Get/update/delete job
- `POST /api/v1/scheduler/jobs/{id}/run` — Manual trigger

**Health:**
- `GET /health` — API health check

## Environment Variables

### Required for LLM (Gemini)
- `GOOGLE_APPLICATION_CREDENTIALS` — Path to GCP service account JSON
- `GOOGLE_CLOUD_PROJECT_ID` — GCP project ID
- `GOOGLE_CLOUD_LOCATION` — Primary region (e.g., `asia-northeast3`)
- `GEMINI_MODEL` — Model name (default: `gemini-2.5-flash`)

### API Configuration
- `DATABASE_URL` — PostgreSQL connection string
- `RABBITMQ_URL` — AMQP connection string
- `ORA_AUTOMATION_ROOT` — Path to ora-automation directory
- `ORA_PROJECTS_ROOT` — Parent directory for project scanning

### Orchestration Tuning
- `ORCHESTRATION_PROFILE` — `standard` or `strict`
- `DEBATE_ROUNDS` — Number of debate rounds (default: 2)
- `TOP` — Number of top strategies to analyze (default: 6)

### Notion Integration
- `NOTION_API_TOKEN` — Notion internal integration token
- `NOTION_API_VERSION` — API version (default: `2022-06-28`)
- `NOTION_AUTO_PUBLISH` — Auto-publish on run completion (`1`/`true` to enable)

### Scheduler
- `ORA_SCHEDULER_ENABLED` — Enable background scheduler (`1`/`true` to enable)
- `ORA_SCHEDULER_POLL_SECONDS` — DB poll interval (default: `60`, min: `10`)

## Development Notes

- Use `python3`, not `python` (venv is Python 3.10)
- Set `PYTHONPATH=src` when running tests or scripts outside Make
- The frontend proxies `/api` to `localhost:8000` in dev mode (vite.config.ts)
- In Docker, the workspace is mounted at `/workspace/Ora`
- `engine.py` is the legacy monolith (~4600 lines) — kept for backward compat, prefer the modular pipeline

## Testing

```bash
# All Python tests (96 tests — chat, dialog, notion, scheduler, scheduling, upce)
PYTHONPATH=src python3 -m pytest tests/ -v

# TypeScript type check
cd frontend && npx tsc --noEmit

# Frontend build
cd frontend && npx vite build

# Python import check
PYTHONPATH=src python3 -c "from ora_automation_api.config import settings; print(settings.database_url)"

# E2E tests
make e2e-service SERVICE=ai
make qa-program
```

### Test Mocking Notes
- Notion tests patch `ora_automation_api.notion_router.settings` directly (not `os.environ`)
- Scheduler poll tests patch `ora_automation_api.queue.publish_run` (lazy import via `from . import queue as _queue`)
- Scheduling intent tests use in-memory SQLite directly (no API mock needed — pure logic + DB)
- All Notion API calls are mocked — no real API calls in tests

## Git Commit Rules

- Follow [Conventional Commits](https://www.conventionalcommits.org/): `<type>(<scope>): <subject>`
- Do NOT append `Co-Authored-By` lines to commit messages
- See [docs/GITHUB_WORKFLOW.md](docs/GITHUB_WORKFLOW.md) for full branch/PR/review rules
