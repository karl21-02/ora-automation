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
- **GitHub App Integration**: Connect GitHub repos, auto-clone on-demand, unified project management

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

         ┌──────────────┐
         │  GitHub App  │───> Webhooks → DB sync
         └──────────────┘     (installations, repos)
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

### GitHub Integration Flow

```
GitHub App Install ──> Webhook ──> GithubInstallation + GithubRepo (DB)
                                          │
User selects repo ──> Project (DB) ──> prepare endpoint ──> clone_service
                                                                  │
                                                            shallow clone
                                                            (on-demand)
```

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, SQLAlchemy 2, Pydantic 2, RabbitMQ (pika), APScheduler
- **Frontend**: React 19, TypeScript 5.9, Vite 7
- **Database**: PostgreSQL 16
- **LLM**: Google Gemini (Vertex AI) — primary; OpenAI — fallback scripts
- **External**: Notion API (report publishing), GitHub App API
- **Infrastructure**: Docker Compose (8 services), Make

## Project Structure

```
ora-automation/
├── src/
│   ├── ora_rd_orchestrator/      # Core orchestration engine (15+ modules)
│   │   ├── pipeline.py           # Main entry: generate_report()
│   │   ├── convergence.py        # LangGraph 3-level convergence (chapter→silo→C-level)
│   │   ├── cli.py                # CLI entry point
│   │   ├── config.py             # Constants, env vars, profiles
│   │   ├── types.py              # All dataclasses
│   │   ├── llm_client.py         # run_llm_command() subprocess wrapper
│   │   ├── personas.py           # PersonaRegistry (24 YAML personas)
│   │   ├── workspace.py          # File scanning, analyze_workspace()
│   │   ├── topic_discovery.py    # LLM topic discovery + legacy fallback
│   │   ├── scoring.py            # LLM scoring + legacy formula
│   │   ├── deliberation.py       # Multi-round debate
│   │   ├── consensus.py          # Final consensus with hard gates
│   │   ├── research.py           # ArXiv/Crossref/OpenAlex clients
│   │   ├── report_builder.py     # Markdown + JSON report gen
│   │   └── personas/             # 24 YAML agent definitions (Toss silo structure)
│   │
│   └── ora_automation_api/       # FastAPI backend (29 modules)
│       ├── main.py               # App entry, router registration, DDL migration
│       ├── chat_router.py        # Chat + conversations + reports + projects
│       ├── org_router.py         # Organization CRUD + agents/silos/chapters
│       ├── github_router.py      # GitHub App webhooks + installation management
│       ├── github_client.py      # GitHub API client (JWT auth, installation tokens)
│       ├── projects_router.py    # Unified projects API (CRUD, scan, prepare)
│       ├── project_service.py    # Local workspace sync + GitHub matching
│       ├── clone_service.py      # On-demand shallow clone + pull
│       ├── local_scanner.py      # Git repo detection + language inference
│       ├── dialog_engine.py      # UPCE dialog engine (intent→action)
│       ├── notion_client.py      # Notion REST API client (retry, backoff)
│       ├── notion_publisher.py   # Report JSON → Notion pages/blocks
│       ├── notion_router.py      # Notion endpoints (setup, publish, sync, status)
│       ├── scheduler.py          # APScheduler DB-polling job scheduler
│       ├── scheduler_router.py   # Scheduler CRUD API
│       ├── scheduling_handler.py # NL scheduling → ScheduledJob (validate + create)
│       ├── schemas.py            # Pydantic request/response models
│       ├── models.py             # SQLAlchemy ORM (Organization, Project, GithubRepo, etc.)
│       ├── database.py           # DB session management
│       ├── config.py             # API settings (env vars)
│       ├── service.py            # Run execution logic + auto-publish hook + project prep
│       ├── plan_utils.py         # Environment key mapping for orchestration
│       ├── queue.py              # RabbitMQ message routing
│       ├── worker.py             # Agent worker process
│       ├── llm_planner.py        # LLM plan adapter
│       ├── org_templates.py      # Preset org templates (Toss, Startup, etc.)
│       ├── exceptions.py         # Custom exception classes
│       └── logging_config.py     # Structured logging setup
│
├── frontend/                     # React + Vite SPA (23 components)
│   └── src/
│       ├── App.tsx               # Main app (conversation state, routing)
│       ├── components/
│       │   ├── Sidebar.tsx           # Navigation + conversation list
│       │   ├── ChatWindow.tsx        # Message display + input
│       │   ├── ChatList.tsx          # Conversation list with search
│       │   ├── ChatContextBar.tsx    # Org/project context display
│       │   ├── MessageBubble.tsx     # Single message rendering
│       │   ├── NewChatModal.tsx      # New conversation (org/project selection)
│       │   ├── ProjectSelectCard.tsx # Project selection card (source badges)
│       │   ├── ProjectListPanel.tsx  # Project list with filters
│       │   ├── GitHubSettings.tsx    # GitHub App installation management
│       │   ├── SettingsPanel.tsx     # Settings (GitHub, Projects tabs)
│       │   ├── SchedulerPanel.tsx    # Scheduled job management UI
│       │   ├── OrgPanel.tsx          # Organization management
│       │   ├── OrgEditor.tsx         # Org detail editor
│       │   ├── OrgDesigner.tsx       # Visual org structure designer
│       │   ├── OrgChart.tsx          # Org hierarchy visualization
│       │   ├── OrgSwitcher.tsx       # Org dropdown selector
│       │   ├── OrgTemplateModal.tsx  # Org template selection
│       │   ├── AgentEditor.tsx       # Agent CRUD form
│       │   ├── ChapterEditor.tsx     # Chapter CRUD form
│       │   ├── GuestAgentPicker.tsx  # Cross-org agent borrowing
│       │   ├── ReportList.tsx        # Report file browser
│       │   ├── ReportViewer.tsx      # Markdown report viewer
│       │   └── Toast.tsx             # Notification toasts
│       ├── lib/
│       │   ├── api.ts            # Typed API client (chat, orgs, github, projects)
│       │   ├── orgTemplates.ts   # Frontend org templates
│       │   ├── sidebarConfig.ts  # Sidebar menu configuration
│       │   └── hooks/            # Custom React hooks
│       └── types.ts              # Shared TypeScript types
│
├── tests/                        # 455 pytest tests
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

### LangGraph 3-Level Convergence
- Organization-aware pipeline in `convergence.py`
- **Level 1**: Chapter-internal deliberation (parallel per chapter)
- **Level 2**: Silo-internal deliberation (parallel per silo)
- **Level 3**: C-Level + silo representatives full deliberation
- Each level loops until scores converge (max delta < threshold) or max_rounds
- Convergence check: `is_converged(prev, curr, threshold)` in `convergence.py`
- See `docs/AGENT_ORG_CUSTOMIZATION_PLAN.md` for full architecture

### Guest Agent Collaboration (V2)
- Borrow agents from other organizations for a single run
- API: `POST /api/v1/orchestrations` with `guest_agent_ids: ["org_id:agent_id", ...]`
- Guest agents are loaded via `_load_guest_agents()` in `service.py`
- Merged into org_config via `_merge_guest_agents()` before pipeline execution
- Guests participate in Level 3 deliberation (`is_clevel=True`)
- Guest agent IDs are prefixed with `guest_` and display names with `[Guest]`

### GitHub App Integration
- **Models**: `GithubInstallation`, `GithubRepo`, `Project` in `models.py`
- **Webhook handling**: `github_router.py` processes `installation`, `installation_repositories` events
- **JWT Auth**: `github_client.py` generates JWT tokens for GitHub API calls
- **On-demand clone**: `clone_service.py` performs shallow clones when project is accessed
- **Project types**:
  - `local`: Existing local directory
  - `github`: Local clone linked to GitHub repo
  - `github_only`: Remote-only, cloned on-demand via `prepare` endpoint
- **Auto-prepare**: `service.py` calls `_prepare_project_if_needed()` before orchestration runs

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

**Reports & Projects (Legacy):**
- `GET /api/v1/reports` — List research reports
- `GET /api/v1/reports/{filename}` — Download report
- `GET /api/v1/projects` — List Ora sub-projects (legacy scanner)

**Unified Projects:**
- `GET /api/v1/unified-projects` — List all projects (filter by source_type, enabled, search)
- `POST /api/v1/unified-projects` — Create project
- `GET/PATCH/DELETE /api/v1/unified-projects/{id}` — Project CRUD
- `POST /api/v1/unified-projects/scan-local` — Scan local workspace + sync to DB
- `POST /api/v1/unified-projects/{id}/prepare` — Ensure local clone exists

**GitHub Integration:**
- `GET /api/v1/github/install-url` — Get GitHub App installation URL
- `POST /api/v1/github/webhook` — GitHub webhook receiver
- `GET /api/v1/github/installations` — List connected installations
- `DELETE /api/v1/github/installations/{id}` — Remove installation
- `GET /api/v1/github/installations/{id}/repos` — List repos for installation
- `POST /api/v1/github/installations/{id}/sync` — Sync repos from GitHub

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

**Organizations:**
- `GET/POST /api/v1/orgs` — List/create organizations
- `GET/PATCH/DELETE /api/v1/orgs/{id}` — Get/update/delete org
- `POST /api/v1/orgs/{id}/clone` — Deep copy org (silos, chapters, agents)
- `POST/PATCH/DELETE /api/v1/orgs/{id}/agents/{id}` — Agent CRUD
- `POST/PATCH/DELETE /api/v1/orgs/{id}/silos/{id}` — Silo CRUD
- `POST/PATCH/DELETE /api/v1/orgs/{id}/chapters/{id}` — Chapter CRUD

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

### GitHub App Integration
- `GITHUB_APP_ID` — GitHub App ID
- `GITHUB_APP_PRIVATE_KEY` — GitHub App private key (PEM format, can be base64-encoded)
- `GITHUB_WEBHOOK_SECRET` — Webhook signature verification secret
- `ORA_CLONE_BASE_DIR` — Base directory for on-demand clones (default: `/tmp/ora-clones`)

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

## Testing

```bash
# All Python tests (455 tests — chat, dialog, notion, scheduler, orgs, convergence, guest, github, projects)
PYTHONPATH=src python3 -m pytest tests/ -v

# TypeScript type check
cd frontend && npx tsc --noEmit

# Frontend build
cd frontend && npm run build

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
- GitHub router tests use in-memory SQLite with `TESTING=1` env to skip lifespan
- Clone service tests mock `asyncio.create_subprocess_exec` for git commands
- All external API calls (Notion, GitHub) are mocked — no real API calls in tests

## Git Commit Rules

- Follow [Conventional Commits](https://www.conventionalcommits.org/): `<type>(<scope>): <subject>`
- Do NOT append `Co-Authored-By` lines to commit messages
- Do NOT add "🤖 Generated with Claude Code" or similar AI attribution messages
- Keep commit messages clean and focused on the actual changes
- See [docs/GITHUB_WORKFLOW.md](docs/GITHUB_WORKFLOW.md) for full branch/PR/review rules
