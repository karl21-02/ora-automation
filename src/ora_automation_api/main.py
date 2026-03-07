from __future__ import annotations

import argparse
import os
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from .chat_router import router as chat_router
from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .llm_planner import PlannerError, run_llm_planner
from .queue import pick_agent_role, publish_run
from .schemas import (
    BatchRunCreate,
    BatchRunResponse,
    DecisionRead,
    DecisionCreate,
    LlmPlanRequest,
    LlmPlanResponse,
    LlmPlanRunRequest,
    OrchestrationEventRead,
    OrchestrationRunCreate,
    OrchestrationRunList,
    OrchestrationRunRead,
    RunActionResponse,
)
from .service import (
    create_run,
    get_decision,
    get_run,
    list_events,
    list_runs,
    request_cancel,
    request_pause,
    request_resume,
)


app = FastAPI(
    title="Ora Automation API",
    version="0.2.0",
    description="FastAPI + Postgres + RabbitMQ orchestration backend for ora-automation",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from .notion_router import router as notion_router
from .org_router import router as org_router
from .scheduler_router import router as scheduler_router

app.include_router(chat_router)
app.include_router(notion_router)
app.include_router(org_router)
app.include_router(scheduler_router)


def _run_ddl_migrations() -> None:
    if engine.dialect.name != "postgresql":
        return
    statements = [
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(128)",
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS agent_role VARCHAR(32) NOT NULL DEFAULT 'engineer'",
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS rollback_command TEXT",
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS pipeline_stages JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS current_stage VARCHAR(32)",
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS max_attempts INTEGER NOT NULL DEFAULT 3",
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ",
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS pause_requested BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS locked_by VARCHAR(128)",
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ",
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ",
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS decision_id VARCHAR(36)",
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS dialog_context JSONB",
        "ALTER TABLE chat_conversations ADD COLUMN IF NOT EXISTS dialog_context_version INTEGER NOT NULL DEFAULT 0",
        # Notion sync state
        """CREATE TABLE IF NOT EXISTS notion_sync_state (
            id SERIAL PRIMARY KEY,
            entity_type VARCHAR(32) NOT NULL,
            entity_key VARCHAR(256) NOT NULL,
            notion_page_id VARCHAR(36) NOT NULL,
            notion_url TEXT,
            source_report_path TEXT,
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(entity_type, entity_key)
        )""",
        # Organizations
        """CREATE TABLE IF NOT EXISTS organizations (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(128) NOT NULL UNIQUE,
            description TEXT,
            is_preset BOOLEAN NOT NULL DEFAULT FALSE,
            teams JSONB NOT NULL DEFAULT '{}'::jsonb,
            flat_mode_agents JSONB NOT NULL DEFAULT '[]'::jsonb,
            agent_final_weights JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS organization_agents (
            id VARCHAR(36) PRIMARY KEY,
            org_id VARCHAR(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            agent_id VARCHAR(64) NOT NULL,
            display_name VARCHAR(128) NOT NULL,
            display_name_ko VARCHAR(128) NOT NULL DEFAULT '',
            role VARCHAR(32) NOT NULL DEFAULT '',
            tier INTEGER NOT NULL DEFAULT 1,
            domain VARCHAR(64),
            team VARCHAR(64) NOT NULL DEFAULT '',
            personality JSONB NOT NULL DEFAULT '{}'::jsonb,
            behavioral_directives JSONB NOT NULL DEFAULT '[]'::jsonb,
            constraints JSONB NOT NULL DEFAULT '[]'::jsonb,
            decision_focus JSONB NOT NULL DEFAULT '[]'::jsonb,
            weights JSONB NOT NULL DEFAULT '{}'::jsonb,
            trust_map JSONB NOT NULL DEFAULT '{}'::jsonb,
            system_prompt_template TEXT,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(org_id, agent_id)
        )""",
        "ALTER TABLE orchestration_runs ADD COLUMN IF NOT EXISTS org_id VARCHAR(36)",
        # Organization silos & chapters
        """CREATE TABLE IF NOT EXISTS organization_silos (
            id VARCHAR(36) PRIMARY KEY,
            org_id VARCHAR(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            name VARCHAR(128) NOT NULL,
            description TEXT,
            color VARCHAR(7) NOT NULL DEFAULT '#3b82f6',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(org_id, name)
        )""",
        """CREATE TABLE IF NOT EXISTS organization_chapters (
            id VARCHAR(36) PRIMARY KEY,
            org_id VARCHAR(36) NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            name VARCHAR(128) NOT NULL,
            description TEXT,
            shared_directives JSONB NOT NULL DEFAULT '[]'::jsonb,
            shared_constraints JSONB NOT NULL DEFAULT '[]'::jsonb,
            shared_decision_focus JSONB NOT NULL DEFAULT '[]'::jsonb,
            chapter_prompt TEXT NOT NULL DEFAULT '',
            color VARCHAR(7) NOT NULL DEFAULT '#8b5cf6',
            icon VARCHAR(4) NOT NULL DEFAULT '📁',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(org_id, name)
        )""",
        "ALTER TABLE organization_agents ADD COLUMN IF NOT EXISTS silo_id VARCHAR(36)",
        "ALTER TABLE organization_agents ADD COLUMN IF NOT EXISTS chapter_id VARCHAR(36)",
        "ALTER TABLE organization_agents ADD COLUMN IF NOT EXISTS is_clevel BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE organization_agents ADD COLUMN IF NOT EXISTS weight_score DOUBLE PRECISION NOT NULL DEFAULT 1.0",
        "ALTER TABLE organizations ADD COLUMN IF NOT EXISTS pipeline_params JSONB NOT NULL DEFAULT '{}'::jsonb",
        # Scheduled jobs
        """CREATE TABLE IF NOT EXISTS scheduled_jobs (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(128) NOT NULL UNIQUE,
            description TEXT,
            target VARCHAR(64) NOT NULL DEFAULT 'run-cycle',
            env JSONB NOT NULL DEFAULT '{}'::jsonb,
            interval_minutes INTEGER,
            cron_expression VARCHAR(128),
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            auto_publish_notion BOOLEAN NOT NULL DEFAULT FALSE,
            last_run_at TIMESTAMPTZ,
            last_run_status VARCHAR(32),
            last_run_id VARCHAR(36),
            next_run_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def _seed_preset_org() -> None:
    """Seed the default preset organization from YAML persona files (idempotent)."""
    import logging

    _logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        from .models import Organization, OrganizationAgent

        PRESET_NAME = "Default (Toss Silo)"
        existing = db.query(Organization).filter(Organization.name == PRESET_NAME).first()
        if existing:
            return

        from uuid import uuid4

        from ora_rd_orchestrator.config import (
            AGENT_FINAL_WEIGHTS,
            FLAT_MODE_AGENTS,
            default_persona_dir,
        )

        persona_dir = default_persona_dir()
        if not persona_dir.is_dir():
            _logger.warning("Persona directory not found for seeding: %s", persona_dir)
            return

        from ora_rd_orchestrator.personas import _load_yaml

        org_id = uuid4().hex[:36]
        org = Organization(
            id=org_id,
            name=PRESET_NAME,
            description="기본 Toss 사일로 구조 (24 에이전트). 수정 불가, 복제 가능.",
            is_preset=True,
            teams={},
            flat_mode_agents=sorted(FLAT_MODE_AGENTS),
            agent_final_weights=AGENT_FINAL_WEIGHTS,
        )
        db.add(org)
        db.flush()

        teams_set: dict[str, list[str]] = {}
        yaml_files = sorted(persona_dir.glob("*.yaml")) + sorted(persona_dir.glob("*.yml"))
        for idx, yaml_path in enumerate(yaml_files):
            try:
                data = _load_yaml(yaml_path)
                agent_id = data.get("agent_id", "")
                if not agent_id:
                    continue
                team = data.get("team", "")
                if team:
                    teams_set.setdefault(team, []).append(agent_id)
                agent = OrganizationAgent(
                    id=uuid4().hex[:36],
                    org_id=org_id,
                    agent_id=agent_id,
                    display_name=data.get("display_name", agent_id),
                    display_name_ko=data.get("display_name_ko", data.get("display_name", agent_id)),
                    role=data.get("role", ""),
                    tier=int(data.get("tier", 1)),
                    domain=data.get("domain") or None,
                    team=team,
                    personality=data.get("personality", {}),
                    behavioral_directives=data.get("behavioral_directives", []),
                    constraints=data.get("constraints", []),
                    decision_focus=data.get("decision_focus", []),
                    weights=data.get("weights", {}),
                    trust_map=data.get("trust_map", {}),
                    system_prompt_template=data.get("system_prompt_template"),
                    enabled=True,
                    sort_order=idx,
                )
                db.add(agent)
            except Exception:
                _logger.exception("Failed to seed agent from %s", yaml_path)

        org.teams = teams_set
        db.commit()
        _logger.info("Seeded preset org '%s' with agents from %d YAML files", PRESET_NAME, len(yaml_files))
    except Exception:
        _logger.exception("Failed to seed preset organization")
        db.rollback()
    finally:
        db.close()


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    _run_ddl_migrations()
    _seed_preset_org()
    settings.run_output_dir.mkdir(parents=True, exist_ok=True)

    if settings.scheduler_enabled:
        from .scheduler import OraScheduler
        app.state.scheduler = OraScheduler(SessionLocal)
        app.state.scheduler.start()


@app.on_event("shutdown")
def shutdown() -> None:
    if hasattr(app.state, "scheduler"):
        app.state.scheduler.stop()


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database": "ok",
        "queue": "rabbitmq",
        "llm_planner_configured": bool(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
            and os.getenv("GOOGLE_CLOUD_PROJECT_ID", "").strip()
        ),
        "automation_root": str(settings.automation_root),
        "allowed_targets": list(settings.allowed_targets),
        "agent_roles": list(settings.agent_roles),
    }


@app.post("/api/v1/orchestrations", response_model=OrchestrationRunRead, status_code=202)
def create_orchestration_run(
    payload: OrchestrationRunCreate,
    db: Session = Depends(get_db),
) -> OrchestrationRunRead:
    run, created = create_run(db, payload)
    if run.status != "dry-run" and created:
        try:
            role = pick_agent_role(run.target, run.agent_role)
            publish_run(run.id, role=role, target=run.target)
        except Exception as exc:
            run.status = "error"
            run.fail_label = "STOP"
            run.exit_code = -1
            run.error_message = f"queue enqueue failed: {exc}"
            run.finished_at = datetime.utcnow()
            db.add(run)
            db.commit()
            db.refresh(run)
            raise HTTPException(status_code=503, detail="failed to enqueue orchestration run")
    return OrchestrationRunRead.model_validate(run)


@app.post("/api/v1/orchestrations/batch", response_model=BatchRunResponse, status_code=202)
def create_batch_runs(
    payload: BatchRunCreate,
    db: Session = Depends(get_db),
) -> BatchRunResponse:
    runs = []
    for plan in payload.plans:
        run_payload = OrchestrationRunCreate(
            user_prompt=payload.user_prompt,
            target=plan.target,
            env=plan.env,
        )
        run, created = create_run(db, run_payload)
        if run.status != "dry-run" and created:
            try:
                role = pick_agent_role(run.target, run.agent_role)
                publish_run(run.id, role=role, target=run.target)
            except Exception as exc:
                run.status = "error"
                run.fail_label = "STOP"
                run.exit_code = -1
                run.error_message = f"queue enqueue failed: {exc}"
                run.finished_at = datetime.utcnow()
                db.add(run)
                db.commit()
                db.refresh(run)
        runs.append(OrchestrationRunRead.model_validate(run))
    return BatchRunResponse(runs=runs)


@app.post("/api/v1/plan", response_model=LlmPlanResponse)
def llm_plan(payload: LlmPlanRequest) -> LlmPlanResponse:
    try:
        plan = run_llm_planner(
            prompt=payload.prompt,
            context=payload.context,
            timeout_seconds=payload.timeout_seconds,
        )
    except PlannerError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return LlmPlanResponse.model_validate(plan)


@app.post("/api/v1/orchestrations/from-plan", response_model=OrchestrationRunRead, status_code=202)
def create_orchestration_from_plan(
    payload: LlmPlanRunRequest,
    db: Session = Depends(get_db),
) -> OrchestrationRunRead:
    try:
        plan = run_llm_planner(
            prompt=payload.prompt,
            context=payload.context,
            timeout_seconds=payload.timeout_seconds,
        )
    except PlannerError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    merged_env = dict(plan.get("env") or {})
    for k, v in (payload.env_overrides or {}).items():
        merged_env[str(k)] = str(v)

    decision_payload = plan.get("decision")
    decision_obj = None
    if isinstance(decision_payload, dict) and decision_payload:
        try:
            decision_obj = DecisionCreate.model_validate(decision_payload)
        except Exception:
            decision_obj = DecisionCreate(
                owner=str(decision_payload.get("owner", "PM") or "PM"),
                rationale=str(decision_payload.get("rationale", "LLM planner decision fallback")),
                risk=str(decision_payload.get("risk", "unspecified")),
                next_action=str(decision_payload.get("next_action", f"execute {plan.get('target', 'run-cycle')}")),
                payload=decision_payload.get("payload", {}) if isinstance(decision_payload.get("payload", {}), dict) else {},
            )

    run_payload = OrchestrationRunCreate(
        user_prompt=payload.prompt,
        target=str(plan.get("target")),
        env=merged_env,
        dry_run=payload.dry_run,
        idempotency_key=payload.idempotency_key,
        agent_role=plan.get("agent_role"),
        max_attempts=plan.get("max_attempts"),
        pipeline_stages=plan.get("pipeline_stages") or ["analysis", "deliberation", "execution"],
        execution_command=plan.get("execution_command"),
        rollback_command=plan.get("rollback_command"),
        decision=decision_obj,
    )
    run, created = create_run(db, run_payload)
    if run.status != "dry-run" and created:
        try:
            role = pick_agent_role(run.target, run.agent_role)
            publish_run(run.id, role=role, target=run.target)
        except Exception as exc:
            run.status = "error"
            run.fail_label = "STOP"
            run.exit_code = -1
            run.error_message = f"queue enqueue failed: {exc}"
            run.finished_at = datetime.utcnow()
            db.add(run)
            db.commit()
            db.refresh(run)
            raise HTTPException(status_code=503, detail="failed to enqueue orchestration run")
    return OrchestrationRunRead.model_validate(run)


@app.get("/api/v1/orchestrations/{run_id}", response_model=OrchestrationRunRead)
def get_orchestration_run(run_id: str, db: Session = Depends(get_db)) -> OrchestrationRunRead:
    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return OrchestrationRunRead.model_validate(run)


@app.get("/api/v1/orchestrations", response_model=OrchestrationRunList)
def list_orchestration_runs(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> OrchestrationRunList:
    items = [OrchestrationRunRead.model_validate(item) for item in list_runs(db, limit=limit)]
    return OrchestrationRunList(items=items, total=len(items))


@app.get("/api/v1/orchestrations/{run_id}/events", response_model=list[OrchestrationEventRead])
def list_orchestration_events(
    run_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[OrchestrationEventRead]:
    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return [OrchestrationEventRead.model_validate(e) for e in list_events(db, run_id=run_id, limit=limit)]


@app.get("/api/v1/orchestrations/{run_id}/decision", response_model=DecisionRead)
def get_orchestration_decision(run_id: str, db: Session = Depends(get_db)) -> DecisionRead:
    run = get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    decision = get_decision(db, run.decision_id)
    if not decision:
        raise HTTPException(status_code=404, detail="decision not found")
    return DecisionRead.model_validate(decision)


@app.post("/api/v1/orchestrations/{run_id}/cancel", response_model=RunActionResponse)
def cancel_orchestration_run(run_id: str, db: Session = Depends(get_db)) -> RunActionResponse:
    run = request_cancel(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return RunActionResponse(
        run_id=run.id,
        status=run.status,
        pause_requested=run.pause_requested,
        cancel_requested=run.cancel_requested,
    )


@app.post("/api/v1/orchestrations/{run_id}/pause", response_model=RunActionResponse)
def pause_orchestration_run(run_id: str, db: Session = Depends(get_db)) -> RunActionResponse:
    run = request_pause(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return RunActionResponse(
        run_id=run.id,
        status=run.status,
        pause_requested=run.pause_requested,
        cancel_requested=run.cancel_requested,
    )


@app.post("/api/v1/orchestrations/{run_id}/resume", response_model=RunActionResponse)
def resume_orchestration_run(run_id: str, db: Session = Depends(get_db)) -> RunActionResponse:
    run = request_resume(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status == "queued":
        role = pick_agent_role(run.target, run.agent_role)
        publish_run(run.id, role=role, target=run.target)
    return RunActionResponse(
        run_id=run.id,
        status=run.status,
        pause_requested=run.pause_requested,
        cancel_requested=run.cancel_requested,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Ora Automation FastAPI server.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    import uvicorn

    uvicorn.run("ora_automation_api.main:app", host=args.host, port=args.port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
