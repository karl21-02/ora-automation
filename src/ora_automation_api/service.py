from __future__ import annotations

import json
import logging
import math
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .config import settings
from .models import OrchestrationDecision, OrchestrationEvent, OrchestrationRun
from .queue import AgentRole, pick_agent_role
from .schemas import DecisionCreate, OrchestrationRunCreate


TERMINAL_STATUSES = {"completed", "failed", "dlq", "skipped", "cancelled", "error"}
RUNNABLE_STATUSES = {"queued", "retry", "dry-run"}

logger = logging.getLogger(__name__)


@dataclass
class ExecutionOutcome:
    run_id: str
    target: str
    agent_role: AgentRole
    status: str
    fail_label: str
    should_retry: bool = False
    retry_delay_seconds: float = 0.0
    should_dlq: bool = False
    dlq_reason: str = ""


@dataclass
class PipelineOutcome:
    """Result of an in-process pipeline execution."""
    result: dict = field(default_factory=dict)
    error: tuple[str, str] | None = None   # (status, message)
    timed_out: bool = False
    cancelled: bool = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _try_auto_publish_notion(run_id: str, db: Session) -> None:
    """Check if a completed run should trigger Notion auto-publish."""
    try:
        from .models import ScheduledJob
        job = db.scalar(
            select(ScheduledJob).where(ScheduledJob.last_run_id == run_id)
        )
        if job and job.auto_publish_notion:
            from .notion_publisher import auto_publish_latest_report
            auto_publish_latest_report(run_id, db)
        elif settings.notion_auto_publish:
            from .notion_publisher import auto_publish_latest_report
            auto_publish_latest_report(run_id, db)
    except Exception as exc:
        logger.warning("Auto-publish to Notion failed for run %s: %s", run_id, exc)


def _sanitize_env(payload: dict[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in payload.items():
        k = str(key).strip()
        if not k:
            continue
        cleaned[k] = str(value).strip()
    return cleaned


def _pick_target(target: str | None) -> str:
    if target and target in settings.allowed_targets:
        return target
    if settings.default_target in settings.allowed_targets:
        return settings.default_target
    return settings.allowed_targets[0]


def _normalize_stages(stages: list[str]) -> list[str]:
    raw = [str(stage).strip().lower() for stage in stages if str(stage).strip()]
    if not raw:
        return ["analysis", "deliberation", "execution"]
    normalized: list[str] = []
    for stage in raw:
        if stage not in normalized:
            normalized.append(stage)
    if "execution" not in normalized:
        normalized.append("execution")
    return normalized


def _json_dump(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_dir(run_id: str) -> Path:
    p = settings.run_output_dir / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_stage_artifact(run: OrchestrationRun, stage: str, payload: dict) -> str:
    path = _run_dir(run.id) / f"{stage}.json"
    _json_dump(path, payload)
    return str(path)


def _record_event(
    db: Session,
    run_id: str,
    stage: str,
    event_type: str,
    message: str,
    payload: dict | None = None,
) -> None:
    event = OrchestrationEvent(
        run_id=run_id,
        stage=stage,
        event_type=event_type,
        message=message,
        payload=payload or {},
    )
    db.add(event)
    db.commit()


def _resolve_fail_label(run: OrchestrationRun, timed_out: bool) -> str:
    if timed_out:
        return "RETRY"
    default_label = str((run.env or {}).get("PIPELINE_FAIL_DEFAULT", "RETRY")).strip().upper()
    if default_label not in {"SKIP", "RETRY", "STOP"}:
        return "RETRY"
    return default_label


def _retry_delay_seconds(attempt_count: int) -> float:
    base = max(1.0, settings.retry_base_seconds)
    max_delay = max(base, settings.retry_max_seconds)
    delay = base * math.pow(2.0, max(0, attempt_count - 1))
    return min(max_delay, delay)


def _create_decision(db: Session, run_id: str, decision: DecisionCreate | None) -> str | None:
    if not decision:
        return None
    decision_id = (decision.decision_id or str(uuid4())).strip()
    row = OrchestrationDecision(
        id=decision_id,
        run_id=run_id,
        owner=decision.owner.strip(),
        rationale=decision.rationale.strip(),
        risk=decision.risk.strip(),
        next_action=decision.next_action.strip(),
        due=decision.due,
        payload=decision.payload or {},
    )
    db.add(row)
    db.commit()
    return row.id


# ---------------------------------------------------------------------------
# env → generate_report() kwargs
# ---------------------------------------------------------------------------

def _env_to_pipeline_kwargs(env: dict[str, str]) -> dict:
    """Convert run.env dict to keyword arguments for generate_report()."""
    from pathlib import Path as _P

    workspace = _P(env.get("WORKSPACE", str(settings.projects_root))).resolve()
    output_dir = _P(env.get("OUTPUT_DIR", str(settings.run_output_dir))).resolve()

    def _csv(key: str, default: str = "") -> list[str]:
        return [v.strip() for v in env.get(key, default).split(",") if v.strip()]

    return {
        "workspace": workspace,
        "top_k": int(env.get("TOP", "6")),
        "output_dir": output_dir,
        "output_name": env.get("OUTPUT_NAME", "rd_research_report"),
        "max_files": int(env.get("MAX_FILES", "1500")),
        "extensions": _csv("EXTENSIONS", "md,py,java,kt,ts,tsx,toml,yml,yaml,json,properties,xml,sh,gradle,txt"),
        "ignore_dirs": set(_csv(
            "IGNORE_DIRS",
            ".git,.idea,.venv,venv,node_modules,target,build,dist,.gradle,.mvn,__pycache__,.pytest_cache",
        )),
        "history_files": [],
        "report_focus": env.get("FOCUS", ""),
        "version_tag": env.get("VERSION_TAG", "V10"),
        "debate_rounds": int(env.get("DEBATE_ROUNDS", "2")),
        "orchestration_profile": env.get("ORCHESTRATION_PROFILE", "standard"),
        "orchestration_stages": _csv("PIPELINE_STAGES", "analysis,deliberation,execution"),
        "service_scope": _csv("PIPELINE_SERVICES", env.get("PIPELINE_ALLOWED_SERVICES", "")),
        "feature_scope": _csv("PIPELINE_FEATURES", ""),
        "agent_mode": env.get("AGENT_MODE", "flat"),
    }


# ---------------------------------------------------------------------------
# In-process pipeline runner (replaces subprocess)
# ---------------------------------------------------------------------------

def _run_pipeline(
    db: Session,
    run: OrchestrationRun,
    timeout_seconds: float,
    worker_id: str,
    org_config: dict | None = None,
) -> PipelineOutcome:
    """Run generate_report() in a daemon thread with heartbeat + cancel support."""
    from ora_rd_orchestrator.pipeline import generate_report
    from ora_rd_orchestrator.types import PipelineCancelled

    cancel_event = threading.Event()
    result_holder: dict = {}
    error_holder: list[tuple[str, str]] = []

    def _target() -> None:
        try:
            kwargs = _env_to_pipeline_kwargs(run.env or {})
            # Override output_dir to run-specific directory
            kwargs["output_dir"] = Path(_run_dir(run.id))
            result = generate_report(
                **kwargs,
                cancel_event=cancel_event,
                org_config=org_config,
            )
            result_holder.update(result)
        except PipelineCancelled:
            error_holder.append(("cancelled", "cancelled via cancel_event"))
        except Exception as exc:
            error_holder.append(("error", str(exc)))

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()

    started = time.monotonic()
    while thread.is_alive():
        elapsed = time.monotonic() - started
        if elapsed > max(1.0, timeout_seconds):
            cancel_event.set()
            thread.join(timeout=10)
            return PipelineOutcome(timed_out=True)

        db.refresh(run)
        if run.cancel_requested:
            cancel_event.set()
            thread.join(timeout=10)
            return PipelineOutcome(cancelled=True)

        run.heartbeat_at = datetime.utcnow()
        run.locked_by = worker_id
        db.add(run)
        db.commit()

        thread.join(timeout=max(0.5, settings.heartbeat_interval_seconds))

    thread.join()

    if error_holder:
        status, msg = error_holder[0]
        if status == "cancelled":
            return PipelineOutcome(cancelled=True)
        return PipelineOutcome(error=(status, msg))

    return PipelineOutcome(result=result_holder)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_run(db: Session, payload: OrchestrationRunCreate) -> tuple[OrchestrationRun, bool]:
    target = _pick_target(payload.target)
    env = _sanitize_env(payload.env)
    command = f"in-process:{target}"
    rollback_command = payload.rollback_command.strip() if payload.rollback_command else None
    idempotency_key = payload.idempotency_key.strip() if payload.idempotency_key else None
    pipeline_stages = _normalize_stages(payload.pipeline_stages)
    agent_role = pick_agent_role(target, payload.agent_role)

    if idempotency_key:
        stmt = (
            select(OrchestrationRun)
            .where(OrchestrationRun.idempotency_key == idempotency_key)
            .order_by(desc(OrchestrationRun.created_at))
            .limit(1)
        )
        existing = db.scalar(stmt)
        if existing:
            return existing, False

    run_id = str(uuid4())
    max_attempts = payload.max_attempts or settings.default_max_attempts
    run = OrchestrationRun(
        id=run_id,
        idempotency_key=idempotency_key,
        user_prompt=payload.user_prompt.strip(),
        target=target,
        agent_role=agent_role,
        command=command,
        rollback_command=rollback_command,
        env=env,
        pipeline_stages=pipeline_stages,
        status="queued" if not payload.dry_run else "dry-run",
        attempt_count=0,
        max_attempts=max(1, int(max_attempts)),
        decision_id=None,
    )
    db.add(run)
    db.commit()
    if payload.decision:
        decision_id = _create_decision(db, run_id, payload.decision)
        run.decision_id = decision_id
        db.add(run)
        db.commit()
    db.refresh(run)
    _record_event(
        db,
        run.id,
        "init",
        "created",
        "orchestration run created",
        {
            "target": run.target,
            "agent_role": run.agent_role,
            "pipeline_stages": run.pipeline_stages,
        },
    )
    return run, True


def get_run(db: Session, run_id: str) -> OrchestrationRun | None:
    return db.get(OrchestrationRun, run_id)


def list_runs(db: Session, limit: int = 20) -> list[OrchestrationRun]:
    stmt = select(OrchestrationRun).order_by(desc(OrchestrationRun.created_at)).limit(max(1, min(limit, 200)))
    return list(db.scalars(stmt).all())


def list_events(db: Session, run_id: str, limit: int = 100) -> list[OrchestrationEvent]:
    stmt = (
        select(OrchestrationEvent)
        .where(OrchestrationEvent.run_id == run_id)
        .order_by(desc(OrchestrationEvent.created_at), desc(OrchestrationEvent.id))
        .limit(max(1, min(limit, 500)))
    )
    return list(db.scalars(stmt).all())


def get_decision(db: Session, decision_id: str | None) -> OrchestrationDecision | None:
    if not decision_id:
        return None
    return db.get(OrchestrationDecision, decision_id)


def request_cancel(db: Session, run_id: str) -> OrchestrationRun | None:
    run = db.get(OrchestrationRun, run_id)
    if not run:
        return None
    run.cancel_requested = True
    if run.status in {"queued", "retry", "paused"}:
        run.status = "cancelled"
        run.finished_at = datetime.utcnow()
        run.fail_label = "STOP"
    db.add(run)
    db.commit()
    _record_event(db, run.id, run.current_stage or "init", "cancel", "cancel requested", {})
    db.refresh(run)
    return run


def request_pause(db: Session, run_id: str) -> OrchestrationRun | None:
    run = db.get(OrchestrationRun, run_id)
    if not run:
        return None
    run.pause_requested = True
    if run.status in {"queued", "retry"}:
        run.status = "paused"
    db.add(run)
    db.commit()
    _record_event(db, run.id, run.current_stage or "init", "pause", "pause requested", {})
    db.refresh(run)
    return run


def request_resume(db: Session, run_id: str) -> OrchestrationRun | None:
    run = db.get(OrchestrationRun, run_id)
    if not run:
        return None
    run.pause_requested = False
    if run.status == "paused":
        run.status = "queued"
    db.add(run)
    db.commit()
    _record_event(db, run.id, run.current_stage or "init", "resume", "resume requested", {})
    db.refresh(run)
    return run


# ---------------------------------------------------------------------------
# Execute run (in-process pipeline)
# ---------------------------------------------------------------------------

def execute_run(
    run_id: str,
    worker_id: str = "worker",
    timeout_seconds: float | None = None,
    db: Session | None = None,
    org_config: dict | None = None,
) -> ExecutionOutcome:
    from .database import SessionLocal

    timeout = float(timeout_seconds or settings.default_timeout_seconds)
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        run = db.get(OrchestrationRun, run_id)
        if not run:
            return ExecutionOutcome(
                run_id=run_id,
                target="unknown",
                agent_role="engineer",
                status="missing",
                fail_label="STOP",
            )
        agent_role = pick_agent_role(run.target, run.agent_role)

        if run.status in TERMINAL_STATUSES:
            return ExecutionOutcome(run_id=run.id, target=run.target, agent_role=agent_role, status=run.status, fail_label=run.fail_label or "STOP")

        if run.pause_requested and run.status in {"queued", "retry", "paused"}:
            run.status = "paused"
            db.add(run)
            db.commit()
            return ExecutionOutcome(run_id=run.id, target=run.target, agent_role=agent_role, status="paused", fail_label="SKIP")

        if run.cancel_requested:
            run.status = "cancelled"
            run.fail_label = "STOP"
            run.finished_at = datetime.utcnow()
            db.add(run)
            db.commit()
            return ExecutionOutcome(run_id=run.id, target=run.target, agent_role=agent_role, status="cancelled", fail_label="STOP", should_dlq=True, dlq_reason="cancelled")

        if run.status not in RUNNABLE_STATUSES:
            return ExecutionOutcome(run_id=run.id, target=run.target, agent_role=agent_role, status=run.status, fail_label=run.fail_label or "STOP")

        run.status = "running"
        run.started_at = run.started_at or datetime.utcnow()
        run.attempt_count = int(run.attempt_count or 0) + 1
        run.locked_by = worker_id
        run.locked_at = datetime.utcnow()
        run.heartbeat_at = datetime.utcnow()
        run.current_stage = "execution"
        db.add(run)
        db.commit()

        _record_event(
            db,
            run.id,
            "execution",
            "started",
            "run execution started (in-process)",
            {
                "attempt_count": run.attempt_count,
                "max_attempts": run.max_attempts,
                "worker_id": worker_id,
            },
        )

        outcome = _run_pipeline(
            db=db,
            run=run,
            timeout_seconds=timeout,
            worker_id=worker_id,
            org_config=org_config,
        )

        if outcome.cancelled:
            run.status = "cancelled"
            run.fail_label = "STOP"
            run.finished_at = datetime.utcnow()
            db.add(run)
            db.commit()
            _record_event(db, run.id, "execution", "cancelled", "run cancelled during execution", {})
            return ExecutionOutcome(
                run_id=run.id, target=run.target, agent_role=agent_role,
                status="cancelled", fail_label="STOP",
                should_dlq=True, dlq_reason="cancelled during execution",
            )

        if outcome.timed_out or outcome.error:
            fail_label = _resolve_fail_label(run, outcome.timed_out)
            run.fail_label = fail_label
            run.error_message = (
                f"pipeline timed out after {timeout}s"
                if outcome.timed_out
                else f"pipeline error: {outcome.error[1] if outcome.error else 'unknown'}"
            )

            if fail_label == "SKIP":
                run.status = "skipped"
                run.finished_at = datetime.utcnow()
                db.add(run)
                db.commit()
                return ExecutionOutcome(run_id=run.id, target=run.target, agent_role=agent_role, status="skipped", fail_label="SKIP")

            if fail_label == "RETRY" and run.attempt_count < run.max_attempts:
                delay = _retry_delay_seconds(run.attempt_count)
                run.status = "retry"
                run.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
                run.finished_at = datetime.utcnow()
                db.add(run)
                db.commit()
                _record_event(db, run.id, "execution", "retry_scheduled", "retry scheduled", {"retry_delay_seconds": delay})
                return ExecutionOutcome(
                    run_id=run.id, target=run.target, agent_role=agent_role,
                    status="retry", fail_label="RETRY",
                    should_retry=True, retry_delay_seconds=delay,
                )

            run.status = "dlq"
            run.fail_label = "STOP"
            run.finished_at = datetime.utcnow()
            db.add(run)
            db.commit()
            _record_event(db, run.id, "execution", "moved_to_dlq", "run moved to dlq", {"attempt_count": run.attempt_count, "max_attempts": run.max_attempts})
            return ExecutionOutcome(
                run_id=run.id, target=run.target, agent_role=agent_role,
                status="dlq", fail_label="STOP",
                should_dlq=True, dlq_reason="max attempts exceeded or stop policy",
            )

        # Success
        run.status = "completed"
        run.fail_label = ""
        run.error_message = None
        run.exit_code = 0
        run.finished_at = datetime.utcnow()
        db.add(run)
        db.commit()
        _record_event(db, run.id, "execution", "stage_completed", "pipeline completed", {})

        # Save pipeline result as artifact
        if outcome.result:
            _write_stage_artifact(run, "pipeline_result", outcome.result)

        _try_auto_publish_notion(run.id, db)
        return ExecutionOutcome(run_id=run.id, target=run.target, agent_role=agent_role, status="completed", fail_label="")

    except Exception as exc:  # pragma: no cover  # noqa: BLE001
        logger.exception("Unexpected error executing run %s", run_id)
        run = db.get(OrchestrationRun, run_id)
        if run:
            run.status = "error"
            run.exit_code = -1
            run.fail_label = "STOP"
            run.error_message = str(exc)
            run.finished_at = datetime.utcnow()
            db.add(run)
            db.commit()
            _record_event(db, run.id, run.current_stage or "execution", "error", "unexpected error", {"error": str(exc)})
            agent_role = pick_agent_role(run.target, run.agent_role)
            return ExecutionOutcome(
                run_id=run.id, target=run.target, agent_role=agent_role,
                status="error", fail_label="STOP",
                should_dlq=True, dlq_reason=str(exc),
            )
        return ExecutionOutcome(run_id=run_id, target="unknown", agent_role="engineer", status="error", fail_label="STOP", should_dlq=True, dlq_reason=str(exc))
    finally:
        if own_session:
            db.close()


def recover_stale_runs(stale_after_seconds: float | None = None) -> list[ExecutionOutcome]:
    from .database import SessionLocal

    timeout = float(stale_after_seconds or settings.stale_timeout_seconds)
    threshold = datetime.utcnow() - timedelta(seconds=max(5.0, timeout))
    db = SessionLocal()
    outcomes: list[ExecutionOutcome] = []
    try:
        stmt = select(OrchestrationRun).where(
            OrchestrationRun.status == "running",
            OrchestrationRun.heartbeat_at.is_not(None),
            OrchestrationRun.heartbeat_at < threshold,
        )
        stale_runs = list(db.scalars(stmt).all())
        for run in stale_runs:
            role = pick_agent_role(run.target, run.agent_role)
            run.fail_label = "RETRY"
            if int(run.attempt_count or 0) < int(run.max_attempts or 1):
                delay = _retry_delay_seconds(int(run.attempt_count or 1))
                run.status = "retry"
                run.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
                run.locked_by = None
                run.locked_at = None
                db.add(run)
                db.commit()
                outcomes.append(
                    ExecutionOutcome(
                        run_id=run.id, target=run.target, agent_role=role,
                        status="retry", fail_label="RETRY",
                        should_retry=True, retry_delay_seconds=delay,
                    )
                )
            else:
                run.status = "dlq"
                run.fail_label = "STOP"
                run.finished_at = datetime.utcnow()
                db.add(run)
                db.commit()
                outcomes.append(
                    ExecutionOutcome(
                        run_id=run.id, target=run.target, agent_role=role,
                        status="dlq", fail_label="STOP",
                        should_dlq=True, dlq_reason="stale run exceeded max attempts",
                    )
                )
            _record_event(
                db, run.id, run.current_stage or "execution",
                "stale_recovered", "stale running job recovered",
                {"attempt_count": run.attempt_count, "max_attempts": run.max_attempts},
            )
    finally:
        db.close()
    return outcomes
