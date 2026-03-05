"""DB-backed job scheduler integrated with FastAPI via APScheduler."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .config import settings
from .models import ScheduledJob

logger = logging.getLogger(__name__)


class OraScheduler:
    """Polls scheduled_jobs table and creates orchestration runs for due jobs."""

    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory
        self._scheduler = BackgroundScheduler(daemon=True)
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        interval = max(10, settings.scheduler_poll_seconds)
        self._scheduler.add_job(
            self._poll_scheduled_jobs,
            "interval",
            seconds=interval,
            id="ora_poll_jobs",
            replace_existing=True,
        )
        self._scheduler.start()
        self._running = True
        logger.info("OraScheduler started (poll every %ds)", interval)

    def stop(self) -> None:
        if not self._running:
            return
        self._scheduler.shutdown(wait=False)
        self._running = False
        logger.info("OraScheduler stopped")

    def _poll_scheduled_jobs(self) -> None:
        db: Session = self._session_factory()
        try:
            now = datetime.utcnow()
            stmt = select(ScheduledJob).where(
                ScheduledJob.enabled.is_(True),
                ScheduledJob.next_run_at.isnot(None),
                ScheduledJob.next_run_at <= now,
            )
            due_jobs = list(db.scalars(stmt).all())
            for job in due_jobs:
                try:
                    self._execute_job(db, job)
                except Exception as exc:
                    logger.error("Scheduler failed to execute job %s: %s", job.id, exc)
                    job.last_run_status = "failed"
                    job.last_run_at = now
                    db.add(job)
                    db.commit()
        except Exception as exc:
            logger.error("Scheduler poll error: %s", exc)
        finally:
            db.close()

    def _execute_job(self, db: Session, job: ScheduledJob) -> None:
        from .queue import pick_agent_role, publish_run
        from .schemas import OrchestrationRunCreate
        from .service import create_run

        now = datetime.utcnow()

        payload = OrchestrationRunCreate(
            user_prompt=f"[Scheduled] {job.name}",
            target=job.target,
            env=dict(job.env or {}),
        )
        run, created = create_run(db, payload)

        if created and run.status != "dry-run":
            try:
                role = pick_agent_role(run.target, run.agent_role)
                publish_run(run.id, role=role, target=run.target)
            except Exception as exc:
                logger.error("Scheduler: queue enqueue failed for job %s: %s", job.id, exc)
                run.status = "error"
                run.error_message = f"queue enqueue failed: {exc}"
                run.finished_at = now
                db.add(run)
                db.commit()

        job.last_run_at = now
        job.last_run_status = "running" if created else "skipped"
        job.last_run_id = run.id
        job.next_run_at = self._calculate_next_run(job)
        db.add(job)
        db.commit()

        logger.info("Scheduler executed job %s → run %s", job.name, run.id)

    @staticmethod
    def _calculate_next_run(job: ScheduledJob) -> datetime | None:
        now = datetime.utcnow()

        if job.interval_minutes and job.interval_minutes > 0:
            return now + timedelta(minutes=job.interval_minutes)

        if job.cron_expression:
            try:
                from apscheduler.triggers.cron import CronTrigger
                trigger = CronTrigger.from_crontab(job.cron_expression)
                next_fire = trigger.get_next_fire_time(None, now)
                return next_fire
            except Exception as exc:
                logger.warning("Invalid cron expression '%s' for job %s: %s", job.cron_expression, job.id, exc)
                return None

        return None
