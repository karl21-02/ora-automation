"""API tests for project history endpoint."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ora_automation_api.database import Base, get_db
from ora_automation_api.models import OrchestrationRun, Project


@pytest.fixture()
def client():
    """TestClient backed by in-memory SQLite."""
    import ora_automation_api.database as db_module
    import ora_automation_api.main as main_module

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

    with patch.dict(os.environ, {"TESTING": "1"}):
        with TestClient(main_module.app) as c:
            c._test_session_local = TestSessionLocal
            yield c

    main_module.app.dependency_overrides.clear()
    main_module.app.router.on_startup = orig_on_startup
    db_module.engine = orig_db_engine
    db_module.SessionLocal = orig_db_session_local
    test_engine.dispose()


@pytest.fixture()
def project_with_history(client: TestClient):
    """Create a project with orchestration run history."""
    session = client._test_session_local()

    # Create project
    project = Project(
        id=uuid4().hex,
        name="test-project",
        source_type="local",
        local_path="/some/path",
    )
    session.add(project)
    session.flush()

    # Create some orchestration runs
    runs = []
    for i in range(5):
        run = OrchestrationRun(
            id=uuid4().hex,
            user_prompt=f"Analyze project iteration {i}",
            target="run-cycle",
            command="make run",
            status="completed" if i < 3 else "running",
            project_id=project.id,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc) if i < 3 else None,
        )
        session.add(run)
        runs.append(run)

    session.commit()
    project_id = project.id
    run_ids = [r.id for r in runs]
    session.close()

    return {"id": project_id, "run_ids": run_ids}


@pytest.fixture()
def project_without_history(client: TestClient):
    """Create a project without any history."""
    session = client._test_session_local()
    project = Project(
        id=uuid4().hex,
        name="no-history-project",
        source_type="local",
        local_path="/some/path",
    )
    session.add(project)
    session.commit()
    project_id = project.id
    session.close()

    return {"id": project_id}


class TestProjectHistoryEndpoint:
    """Test GET /projects/{id}/history endpoint."""

    def test_get_history_with_runs(self, client: TestClient, project_with_history: dict):
        """Should return orchestration runs for project."""
        resp = client.get(f"/api/v1/unified-projects/{project_with_history['id']}/history")

        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 5
        assert len(data["items"]) == 5

        # Check structure
        item = data["items"][0]
        assert "id" in item
        assert "run_type" in item
        assert "status" in item
        assert "started_at" in item
        assert "user_prompt" in item

    def test_get_history_empty(self, client: TestClient, project_without_history: dict):
        """Should return empty list when no history."""
        resp = client.get(f"/api/v1/unified-projects/{project_without_history['id']}/history")

        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 0
        assert data["items"] == []

    def test_get_history_project_not_found(self, client: TestClient):
        """Should return 404 for non-existent project."""
        resp = client.get("/api/v1/unified-projects/nonexistent-id/history")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_history_pagination(self, client: TestClient, project_with_history: dict):
        """Should support pagination."""
        # Get first 2
        resp = client.get(
            f"/api/v1/unified-projects/{project_with_history['id']}/history",
            params={"limit": 2, "offset": 0},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5  # Total count unchanged
        assert len(data["items"]) == 2  # But only 2 returned

        # Get next 2
        resp = client.get(
            f"/api/v1/unified-projects/{project_with_history['id']}/history",
            params={"limit": 2, "offset": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2

    def test_get_history_truncates_prompt(self, client: TestClient):
        """Should truncate long prompts."""
        session = client._test_session_local()

        # Create project with long prompt run
        project = Project(
            id=uuid4().hex,
            name="long-prompt-project",
            source_type="local",
            local_path="/path",
        )
        session.add(project)
        session.flush()

        long_prompt = "A" * 500  # 500 chars
        run = OrchestrationRun(
            id=uuid4().hex,
            user_prompt=long_prompt,
            target="run-cycle",
            command="make run",
            status="completed",
            project_id=project.id,
        )
        session.add(run)
        session.commit()
        project_id = project.id
        session.close()

        resp = client.get(f"/api/v1/unified-projects/{project_id}/history")
        assert resp.status_code == 200

        item = resp.json()["items"][0]
        assert len(item["user_prompt"]) == 200  # Truncated to 200
