from __future__ import annotations

import json
import logging
import math
import os
import shlex
import subprocess
import time
from dataclasses import dataclass
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
class CommandOutcome:
    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    cancelled: bool
    paused: bool


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


def _build_make_command(target: str, env: dict[str, str]) -> list[str]:
    command = ["make", target]
    for key in sorted(env.keys()):
        command.append(f"{key}={env[key]}")
    return command


def _build_command_text(target: str, env: dict[str, str], override: str | None) -> str:
    if override and override.strip():
        return override.strip()
    parts = _build_make_command(target, env)
    return " ".join(shlex.quote(part) for part in parts)


def _json_dump(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_dir(run_id: str) -> Path:
    p = settings.run_output_dir / run_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _write_output_files(run: OrchestrationRun, stdout: bytes, stderr: bytes) -> tuple[str, str]:
    run_dir = _run_dir(run.id)
    stdout_path = run_dir / "stdout.log"
    stderr_path = run_dir / "stderr.log"
    stdout_path.write_bytes(stdout or b"")
    stderr_path.write_bytes(stderr or b"")
    return str(stdout_path), str(stderr_path)


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


def _safe_parse_command(command: str) -> list[str]:
    return shlex.split(command)


def _terminate_process(proc: subprocess.Popen[bytes]) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass


def _run_with_heartbeat(
    db: Session,
    run: OrchestrationRun,
    command: str,
    timeout_seconds: float,
    worker_id: str,
) -> CommandOutcome:
    env = os.environ.copy()
    for key, value in (run.env or {}).items():
        env[str(key)] = str(value)

    proc = subprocess.Popen(
        _safe_parse_command(command),
        cwd=str(settings.automation_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    started = time.monotonic()
    next_heartbeat = started
    timed_out = False
    cancelled = False
    paused = False

    sleep_interval = 0.1  # start fast for responsive cancellation
    while True:
        if proc.poll() is not None:
            break

        now = time.monotonic()
        elapsed = now - started
        if elapsed > max(1.0, timeout_seconds):
            timed_out = True
            _terminate_process(proc)
            break

        if now >= next_heartbeat:
            db.refresh(run)
            if run.cancel_requested:
                cancelled = True
                _terminate_process(proc)
                break
            if run.pause_requested:
                paused = True
                _terminate_process(proc)
                break
            run.heartbeat_at = datetime.utcnow()
            run.locked_by = worker_id
            db.add(run)
            db.commit()
            next_heartbeat = now + max(0.5, settings.heartbeat_interval_seconds)

        # Adaptive sleep: fast early (responsive cancel), slower when stable
        if elapsed < 5.0:
            sleep_interval = 0.1
        elif elapsed < 30.0:
            sleep_interval = 0.5
        else:
            sleep_interval = 1.0
        time.sleep(sleep_interval)

    stdout, stderr = proc.communicate()
    return CommandOutcome(
        returncode=int(proc.returncode if proc.returncode is not None else -1),
        stdout=stdout or b"",
        stderr=stderr or b"",
        timed_out=timed_out,
        cancelled=cancelled,
        paused=paused,
    )


def _run_rollback(run: OrchestrationRun, worker_id: str) -> tuple[int, bytes, bytes]:
    if not run.rollback_command:
        return 0, b"", b""
    env = os.environ.copy()
    env["ORA_AUTOMATION_WORKER_ID"] = worker_id
    proc = subprocess.run(
        shlex.split(run.rollback_command),
        cwd=str(settings.automation_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=max(1.0, settings.default_timeout_seconds),
        check=False,
        env=env,
    )
    return int(proc.returncode), proc.stdout or b"", proc.stderr or b""


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


def create_run(db: Session, payload: OrchestrationRunCreate) -> tuple[OrchestrationRun, bool]:
    target = _pick_target(payload.target)
    env = _sanitize_env(payload.env)
    command = _build_command_text(target, env, payload.execution_command)
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


def execute_run(
    run_id: str,
    worker_id: str = "worker",
    timeout_seconds: float | None = None,
) -> ExecutionOutcome:
    from .database import SessionLocal

    timeout = float(timeout_seconds or settings.default_timeout_seconds)
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
        db.add(run)
        db.commit()

        _record_event(
            db,
            run.id,
            "execution",
            "started",
            "run execution started",
            {
                "attempt_count": run.attempt_count,
                "max_attempts": run.max_attempts,
                "worker_id": worker_id,
            },
        )

        stages = _normalize_stages(list(run.pipeline_stages or []))
        for stage in stages:
            run.current_stage = stage
            db.add(run)
            db.commit()

            stage_payload = {
                "run_id": run.id,
                "stage": stage,
                "status": "started",
                "target": run.target,
                "agent_role": run.agent_role,
            }
            artifact_path = _write_stage_artifact(run, stage, stage_payload)
            _record_event(
                db,
                run.id,
                stage,
                "stage_started",
                f"{stage} stage started",
                {"artifact_path": artifact_path},
            )

            if stage in {"analysis", "deliberation"}:
                stage_payload["status"] = "completed"
                stage_payload["message"] = f"{stage} artifact generated"
                _write_stage_artifact(run, stage, stage_payload)
                _record_event(db, run.id, stage, "stage_completed", f"{stage} stage completed", {"artifact_path": artifact_path})
                continue

            cmd_outcome = _run_with_heartbeat(
                db=db,
                run=run,
                command=run.command,
                timeout_seconds=timeout,
                worker_id=worker_id,
            )
            stdout_path, stderr_path = _write_output_files(run, cmd_outcome.stdout, cmd_outcome.stderr)
            run.stdout_path = stdout_path
            run.stderr_path = stderr_path
            run.exit_code = cmd_outcome.returncode

            if cmd_outcome.paused:
                run.status = "paused"
                run.fail_label = "SKIP"
                run.finished_at = datetime.utcnow()
                db.add(run)
                db.commit()
                _record_event(db, run.id, stage, "paused", "run paused during execution", {})
                return ExecutionOutcome(run_id=run.id, target=run.target, agent_role=agent_role, status="paused", fail_label="SKIP")

            if cmd_outcome.cancelled:
                run.status = "cancelled"
                run.fail_label = "STOP"
                run.finished_at = datetime.utcnow()
                db.add(run)
                db.commit()
                _record_event(db, run.id, stage, "cancelled", "run cancelled during execution", {})
                return ExecutionOutcome(
                    run_id=run.id,
                    target=run.target,
                    agent_role=agent_role,
                    status="cancelled",
                    fail_label="STOP",
                    should_dlq=True,
                    dlq_reason="cancelled during execution",
                )

            if cmd_outcome.returncode == 0 and not cmd_outcome.timed_out:
                run.status = "completed"
                run.fail_label = ""
                run.error_message = None
                run.finished_at = datetime.utcnow()
                db.add(run)
                db.commit()
                _record_event(db, run.id, stage, "stage_completed", "execution stage completed", {"exit_code": 0})
                _try_auto_publish_notion(run.id, db)
                return ExecutionOutcome(run_id=run.id, target=run.target, agent_role=agent_role, status="completed", fail_label="")

            fail_label = _resolve_fail_label(run, cmd_outcome.timed_out)
            run.fail_label = fail_label
            run.error_message = (
                f"execution failed (exit={cmd_outcome.returncode}, timed_out={cmd_outcome.timed_out})"
            )

            rollback_rc, rollback_stdout, rollback_stderr = _run_rollback(run, worker_id)
            if run.rollback_command:
                rollback_path = _run_dir(run.id) / "rollback.log"
                rollback_path.write_bytes(
                    (rollback_stdout or b"")
                    + b"\n--- stderr ---\n"
                    + (rollback_stderr or b"")
                )
                _record_event(
                    db,
                    run.id,
                    stage,
                    "rollback_executed",
                    "rollback command executed",
                    {
                        "rollback_command": run.rollback_command,
                        "rollback_exit_code": rollback_rc,
                        "rollback_log_path": str(rollback_path),
                    },
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
                _record_event(
                    db,
                    run.id,
                    stage,
                    "retry_scheduled",
                    "retry scheduled",
                    {"retry_delay_seconds": delay},
                )
                return ExecutionOutcome(
                    run_id=run.id,
                    target=run.target,
                    agent_role=agent_role,
                    status="retry",
                    fail_label="RETRY",
                    should_retry=True,
                    retry_delay_seconds=delay,
                )

            run.status = "dlq"
            run.fail_label = "STOP"
            run.finished_at = datetime.utcnow()
            db.add(run)
            db.commit()
            _record_event(
                db,
                run.id,
                stage,
                "moved_to_dlq",
                "run moved to dlq",
                {"attempt_count": run.attempt_count, "max_attempts": run.max_attempts},
            )
            return ExecutionOutcome(
                run_id=run.id,
                target=run.target,
                agent_role=agent_role,
                status="dlq",
                fail_label="STOP",
                should_dlq=True,
                dlq_reason="max attempts exceeded or stop policy",
            )

        run.status = "completed"
        run.finished_at = datetime.utcnow()
        db.add(run)
        db.commit()
        _try_auto_publish_notion(run.id, db)
        return ExecutionOutcome(run_id=run.id, target=run.target, agent_role=agent_role, status="completed", fail_label="")
    except Exception as exc:  # pragma: no cover
        run = db.get(OrchestrationRun, run_id)
        if run:
            run.status = "error"
            run.exit_code = -1
            run.fail_label = "STOP"
            run.error_message = str(exc)
            run.finished_at = datetime.utcnow()
            db.add(run)
            db.commit()
            _record_event(
                db,
                run.id,
                run.current_stage or "execution",
                "error",
                "unexpected error",
                {"error": str(exc)},
            )
            agent_role = pick_agent_role(run.target, run.agent_role)
            return ExecutionOutcome(
                run_id=run.id,
                target=run.target,
                agent_role=agent_role,
                status="error",
                fail_label="STOP",
                should_dlq=True,
                dlq_reason=str(exc),
            )
        return ExecutionOutcome(run_id=run_id, target="unknown", agent_role="engineer", status="error", fail_label="STOP", should_dlq=True, dlq_reason=str(exc))
    finally:
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
                        run_id=run.id,
                        target=run.target,
                        agent_role=role,
                        status="retry",
                        fail_label="RETRY",
                        should_retry=True,
                        retry_delay_seconds=delay,
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
                        run_id=run.id,
                        target=run.target,
                        agent_role=role,
                        status="dlq",
                        fail_label="STOP",
                        should_dlq=True,
                        dlq_reason="stale run exceeded max attempts",
                    )
                )
            _record_event(
                db,
                run.id,
                run.current_stage or "execution",
                "stale_recovered",
                "stale running job recovered",
                {"attempt_count": run.attempt_count, "max_attempts": run.max_attempts},
            )
    finally:
        db.close()
    return outcomes
