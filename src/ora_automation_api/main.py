from __future__ import annotations

import argparse
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
from .scheduler_router import router as scheduler_router

app.include_router(chat_router)
app.include_router(notion_router)
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


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    _run_ddl_migrations()
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
        "llm_planner_configured": bool(settings.llm_planner_cmd.strip()),
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
