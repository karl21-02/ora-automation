"""Scheduler CRUD API endpoints."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import ScheduledJob
from .scheduler import OraScheduler
from .schemas import (
    OrchestrationRunRead,
    ScheduledJobCreate,
    ScheduledJobRead,
    ScheduledJobUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scheduler", tags=["scheduler"])


def _calculate_initial_next_run(job_data: ScheduledJobCreate | ScheduledJob) -> datetime | None:
    now = datetime.utcnow()
    interval = getattr(job_data, "interval_minutes", None)
    cron = getattr(job_data, "cron_expression", None)

    if interval and interval > 0:
        return now + timedelta(minutes=interval)

    if cron:
        try:
            from apscheduler.triggers.cron import CronTrigger
            trigger = CronTrigger.from_crontab(cron)
            return trigger.get_next_fire_time(None, now)
        except Exception:
            return None

    return None


# ── POST /jobs ────────────────────────────────────────────────────────


@router.post("/jobs", response_model=ScheduledJobRead, status_code=201)
def create_job(payload: ScheduledJobCreate, db: Session = Depends(get_db)) -> ScheduledJobRead:
    """Create a new scheduled job."""
    if not payload.interval_minutes and not payload.cron_expression:
        raise HTTPException(
            status_code=422,
            detail="Either interval_minutes or cron_expression is required",
        )

    # Check name uniqueness
    existing = db.scalar(select(ScheduledJob).where(ScheduledJob.name == payload.name))
    if existing:
        raise HTTPException(status_code=409, detail=f"Job name '{payload.name}' already exists")

    # Validate target
    if payload.target not in settings.allowed_targets:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid target '{payload.target}'. Allowed: {list(settings.allowed_targets)}",
        )

    job = ScheduledJob(
        id=str(uuid4()),
        name=payload.name.strip(),
        description=payload.description,
        target=payload.target,
        env=payload.env or {},
        interval_minutes=payload.interval_minutes,
        cron_expression=payload.cron_expression,
        enabled=payload.enabled,
        auto_publish_notion=payload.auto_publish_notion,
        next_run_at=_calculate_initial_next_run(payload) if payload.enabled else None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return ScheduledJobRead.model_validate(job)


# ── GET /jobs ─────────────────────────────────────────────────────────


@router.get("/jobs", response_model=list[ScheduledJobRead])
def list_jobs(db: Session = Depends(get_db)) -> list[ScheduledJobRead]:
    """List all scheduled jobs."""
    jobs = db.scalars(select(ScheduledJob).order_by(ScheduledJob.created_at.desc())).all()
    return [ScheduledJobRead.model_validate(j) for j in jobs]


# ── GET /jobs/{job_id} ────────────────────────────────────────────────


@router.get("/jobs/{job_id}", response_model=ScheduledJobRead)
def get_job(job_id: str, db: Session = Depends(get_db)) -> ScheduledJobRead:
    """Get a scheduled job by ID."""
    job = db.get(ScheduledJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return ScheduledJobRead.model_validate(job)


# ── PATCH /jobs/{job_id} ──────────────────────────────────────────────


@router.patch("/jobs/{job_id}", response_model=ScheduledJobRead)
def update_job(
    job_id: str,
    payload: ScheduledJobUpdate,
    db: Session = Depends(get_db),
) -> ScheduledJobRead:
    """Update a scheduled job."""
    job = db.get(ScheduledJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field_name, value in update_data.items():
        setattr(job, field_name, value)

    # Recalculate next_run_at if scheduling changed
    if any(k in update_data for k in ("interval_minutes", "cron_expression", "enabled")):
        if job.enabled:
            job.next_run_at = OraScheduler._calculate_next_run(job)
        else:
            job.next_run_at = None

    db.add(job)
    db.commit()
    db.refresh(job)
    return ScheduledJobRead.model_validate(job)


# ── DELETE /jobs/{job_id} ─────────────────────────────────────────────


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str, db: Session = Depends(get_db)) -> None:
    """Delete a scheduled job."""
    job = db.get(ScheduledJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    db.delete(job)
    db.commit()


# ── POST /jobs/{job_id}/run ───────────────────────────────────────────


@router.post("/jobs/{job_id}/run", response_model=OrchestrationRunRead, status_code=201)
def trigger_job(job_id: str, db: Session = Depends(get_db)) -> OrchestrationRunRead:
    """Immediately trigger a scheduled job (manual execution)."""
    from .queue import pick_agent_role, publish_run
    from .schemas import OrchestrationRunCreate
    from .service import create_run

    job = db.get(ScheduledJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    payload = OrchestrationRunCreate(
        user_prompt=f"[Manual trigger] {job.name}",
        target=job.target,
        env=dict(job.env or {}),
    )
    run, created = create_run(db, payload)

    if created and run.status != "dry-run":
        try:
            role = pick_agent_role(run.target, run.agent_role)
            publish_run(run.id, role=role, target=run.target)
        except Exception as exc:
            run.status = "error"
            run.error_message = f"queue enqueue failed: {exc}"
            run.finished_at = datetime.utcnow()
            db.add(run)
            db.commit()
            db.refresh(run)
            raise HTTPException(status_code=503, detail="Failed to enqueue run")

    job.last_run_at = datetime.utcnow()
    job.last_run_status = "running"
    job.last_run_id = run.id
    db.add(job)
    db.commit()

    return OrchestrationRunRead.model_validate(run)
