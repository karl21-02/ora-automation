"""Tests for the scheduler CRUD API and poll logic."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ora_automation_api.database import Base, get_db
from ora_automation_api.models import ScheduledJob


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def client():
    """FastAPI TestClient backed by in-memory SQLite."""
    import ora_automation_api.database as db_module
    import ora_automation_api.main as main_module
    from fastapi.testclient import TestClient

    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(test_engine)
    TestSessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False,
    )

    def override_get_db():
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    orig_db_engine = db_module.engine
    orig_db_session_local = db_module.SessionLocal
    db_module.engine = test_engine
    db_module.SessionLocal = TestSessionLocal
    main_module.app.dependency_overrides[get_db] = override_get_db
    orig_on_startup = list(main_module.app.router.on_startup)
    main_module.app.router.on_startup = []

    with TestClient(main_module.app) as c:
        yield c

    main_module.app.dependency_overrides.clear()
    main_module.app.router.on_startup = orig_on_startup
    db_module.engine = orig_db_engine
    db_module.SessionLocal = orig_db_session_local
    test_engine.dispose()


@pytest.fixture()
def scheduler_db():
    """In-memory SQLite with all tables for direct scheduler testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ── CRUD API tests ────────────────────────────────────────────────────


def test_create_job(client):
    """POST /scheduler/jobs should create a new job."""
    resp = client.post("/api/v1/scheduler/jobs", json={
        "name": "Daily R&D",
        "target": "run-cycle",
        "interval_minutes": 120,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Daily R&D"
    assert data["target"] == "run-cycle"
    assert data["interval_minutes"] == 120
    assert data["enabled"] is True
    assert data["id"]


def test_list_jobs(client):
    """GET /scheduler/jobs should return all jobs."""
    client.post("/api/v1/scheduler/jobs", json={"name": "Job A", "interval_minutes": 60})
    client.post("/api/v1/scheduler/jobs", json={"name": "Job B", "interval_minutes": 120})

    resp = client.get("/api/v1/scheduler/jobs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


def test_toggle_job(client):
    """PATCH enabled=False should disable the job."""
    create_resp = client.post("/api/v1/scheduler/jobs", json={
        "name": "Toggle Test",
        "interval_minutes": 60,
    })
    job_id = create_resp.json()["id"]

    resp = client.patch(f"/api/v1/scheduler/jobs/{job_id}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False
    assert resp.json()["next_run_at"] is None


def test_delete_job(client):
    """DELETE should remove the job."""
    create_resp = client.post("/api/v1/scheduler/jobs", json={
        "name": "Delete Test",
        "interval_minutes": 60,
    })
    job_id = create_resp.json()["id"]

    del_resp = client.delete(f"/api/v1/scheduler/jobs/{job_id}")
    assert del_resp.status_code == 204

    get_resp = client.get(f"/api/v1/scheduler/jobs/{job_id}")
    assert get_resp.status_code == 404


@patch("ora_automation_api.scheduler_router.publish_run")
@patch("ora_automation_api.scheduler_router.pick_agent_role", return_value="engineer")
def test_manual_trigger(mock_role, mock_publish, client):
    """POST /jobs/{id}/run should create and enqueue a run."""
    create_resp = client.post("/api/v1/scheduler/jobs", json={
        "name": "Trigger Test",
        "interval_minutes": 60,
    })
    job_id = create_resp.json()["id"]

    resp = client.post(f"/api/v1/scheduler/jobs/{job_id}/run")
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] in ("queued", "dry-run")
    assert "[Manual trigger]" in data["user_prompt"]


# ── Poll logic tests ──────────────────────────────────────────────────


@patch("ora_automation_api.scheduler.publish_run")
@patch("ora_automation_api.scheduler.pick_agent_role", return_value="engineer")
def test_poll_executes_due_jobs(mock_role, mock_publish, scheduler_db):
    """_poll_scheduled_jobs should execute jobs where next_run_at <= now."""
    from uuid import uuid4
    from ora_automation_api.scheduler import OraScheduler

    job = ScheduledJob(
        id=str(uuid4()),
        name="Due Job",
        target="run-cycle",
        env={},
        interval_minutes=60,
        enabled=True,
        next_run_at=datetime.utcnow() - timedelta(minutes=5),
    )
    scheduler_db.add(job)
    scheduler_db.commit()

    SessionFactory = sessionmaker(bind=scheduler_db.get_bind())
    scheduler = OraScheduler(SessionFactory)
    scheduler._poll_scheduled_jobs()

    scheduler_db.refresh(job)
    assert job.last_run_status is not None
    assert job.next_run_at is not None
    assert job.next_run_at > datetime.utcnow()


def test_poll_skips_disabled(scheduler_db):
    """_poll_scheduled_jobs should skip disabled jobs."""
    from uuid import uuid4
    from ora_automation_api.scheduler import OraScheduler

    job = ScheduledJob(
        id=str(uuid4()),
        name="Disabled Job",
        target="run-cycle",
        env={},
        interval_minutes=60,
        enabled=False,
        next_run_at=datetime.utcnow() - timedelta(minutes=5),
    )
    scheduler_db.add(job)
    scheduler_db.commit()

    SessionFactory = sessionmaker(bind=scheduler_db.get_bind())
    scheduler = OraScheduler(SessionFactory)
    scheduler._poll_scheduled_jobs()

    scheduler_db.refresh(job)
    assert job.last_run_status is None  # Not executed


# ── Next-run calculation tests ────────────────────────────────────────


def test_interval_next_run():
    """interval_minutes should produce correct next_run_at."""
    from ora_automation_api.scheduler import OraScheduler

    job = MagicMock()
    job.interval_minutes = 120
    job.cron_expression = None

    next_run = OraScheduler._calculate_next_run(job)
    assert next_run is not None
    diff = (next_run - datetime.utcnow()).total_seconds()
    assert 7100 < diff < 7300  # ~120 minutes


def test_cron_next_run():
    """cron_expression should produce a valid future next_run_at."""
    from ora_automation_api.scheduler import OraScheduler

    job = MagicMock()
    job.interval_minutes = None
    job.cron_expression = "0 */6 * * *"  # every 6 hours
    job.id = "test"

    next_run = OraScheduler._calculate_next_run(job)
    assert next_run is not None
    assert next_run > datetime.utcnow()
