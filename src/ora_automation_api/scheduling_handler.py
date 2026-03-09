"""Scheduling intent handler — validate slots and create ScheduledJob rows."""
from __future__ import annotations

import logging
import re
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import ScheduledJob

logger = logging.getLogger(__name__)


class ScheduleValidationError(Exception):
    """Raised when scheduling slots fail validation."""

    pass


def validate_cron(expr: str) -> str:
    """Validate a cron expression using APScheduler's CronTrigger.

    Returns the expression if valid, raises ScheduleValidationError otherwise.
    """
    if not expr or not expr.strip():
        raise ScheduleValidationError("cron_expression이 비어 있습니다.")
    expr = expr.strip()
    try:
        from apscheduler.triggers.cron import CronTrigger

        CronTrigger.from_crontab(expr)
    except Exception as exc:
        raise ScheduleValidationError(f"유효하지 않은 cron 표현식입니다: '{expr}' ({exc})")
    return expr


def validate_interval(minutes: int) -> int:
    """Validate interval is within 5–10080 minutes (1 week).

    Returns the value if valid, raises ScheduleValidationError otherwise.
    """
    if minutes < 5:
        raise ScheduleValidationError(
            f"interval_minutes는 최소 5분이어야 합니다. (입력값: {minutes})"
        )
    if minutes > 10080:
        raise ScheduleValidationError(
            f"interval_minutes는 최대 10080분(1주)입니다. (입력값: {minutes})"
        )
    return minutes


_UNSAFE_CHARS = re.compile(r"[^\w가-힣\s\-]")


def build_job_name(topic: str, human_readable: str | None = None) -> str:
    """Build a clean job name from topic and human-readable schedule."""
    parts = [topic.strip()]
    if human_readable:
        parts.append(human_readable.strip())
    raw = " - ".join(parts)
    cleaned = _UNSAFE_CHARS.sub("", raw).strip()
    if not cleaned:
        cleaned = f"scheduled-job-{uuid4().hex[:8]}"
    return cleaned[:128]


def create_scheduled_job_from_slots(
    db: Session,
    slots: dict,
) -> ScheduledJob:
    """Create a ScheduledJob from accumulated dialog slots.

    Required slots: topic, frequency_type, and either cron_expression or interval_minutes.
    Raises ScheduleValidationError on invalid input.
    """
    topic = slots.get("topic")
    if not topic:
        raise ScheduleValidationError("분석 주제(topic)가 지정되지 않았습니다.")

    frequency_type = slots.get("frequency_type", "cron")
    cron_expr: str | None = None
    interval_min: int | None = None

    if frequency_type == "cron":
        raw_cron = slots.get("cron_expression")
        if not raw_cron:
            raise ScheduleValidationError("cron_expression이 필요합니다.")
        cron_expr = validate_cron(raw_cron)
    elif frequency_type == "interval":
        raw_interval = slots.get("interval_minutes")
        if raw_interval is None:
            raise ScheduleValidationError("interval_minutes가 필요합니다.")
        interval_min = validate_interval(int(raw_interval))
    else:
        raise ScheduleValidationError(
            f"frequency_type은 'cron' 또는 'interval'이어야 합니다. (입력값: {frequency_type})"
        )

    human_readable = slots.get("human_readable")
    target = slots.get("target", "run-cycle")
    auto_publish = bool(slots.get("auto_publish", False))
    projects = slots.get("projects", [])

    name = build_job_name(topic, human_readable)

    # Check for duplicate name
    existing = db.query(ScheduledJob).filter(ScheduledJob.name == name).first()
    if existing:
        raise ScheduleValidationError(
            f"동일한 이름의 스케줄이 이미 존재합니다: '{name}'"
        )

    env: dict = {"FOCUS": topic}
    if projects:
        env["PROJECTS"] = ",".join(projects)

    job = ScheduledJob(
        id=str(uuid4()),
        name=name,
        description=f"[자동 생성] {topic} ({human_readable or frequency_type})",
        target=target,
        env=env,
        interval_minutes=interval_min,
        cron_expression=cron_expr,
        enabled=True,
        auto_publish_notion=auto_publish,
    )

    # Calculate initial next_run_at
    from .scheduler import OraScheduler

    job.next_run_at = OraScheduler._calculate_next_run(job)

    db.add(job)

    # Handle race condition: another request might have created the same name
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        # Check if it's a unique constraint violation on name
        if "name" in str(exc).lower() or "unique" in str(exc).lower():
            raise ScheduleValidationError(
                f"동일한 이름의 스케줄이 이미 존재합니다: '{name}'"
            ) from None
        raise  # Re-raise other integrity errors

    logger.info("Created scheduled job '%s' (id=%s)", name, job.id)
    return job
