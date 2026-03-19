"""API tests for project env endpoint."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ora_automation_api.database import Base, get_db
from ora_automation_api.models import Project


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
            # Store session for test setup
            c._test_session_local = TestSessionLocal
            yield c

    main_module.app.dependency_overrides.clear()
    main_module.app.router.on_startup = orig_on_startup
    db_module.engine = orig_db_engine
    db_module.SessionLocal = orig_db_session_local
    test_engine.dispose()


@pytest.fixture()
def project_with_env(client: TestClient):
    """Create a project with .env file in temp directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create .env file
        env_file = Path(tmpdir) / ".env"
        env_file.write_text(
            "DATABASE_URL=postgres://localhost:5432/db\n"
            "API_KEY=secret_key_12345\n"
            "DEBUG=true\n"
        )

        # Create .env.example
        example_file = Path(tmpdir) / ".env.example"
        example_file.write_text(
            "DATABASE_URL=postgres://localhost:5432/your_db\n"
            "API_KEY=your_api_key_here\n"
            "DEBUG=false\n"
        )

        # Create project in DB
        session = client._test_session_local()
        project = Project(
            id=uuid4().hex,
            name="test-project",
            source_type="local",
            local_path=tmpdir,
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        project_id = project.id
        session.close()

        yield {"id": project_id, "path": tmpdir}


@pytest.fixture()
def project_without_env(client: TestClient):
    """Create a project without .env file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        session = client._test_session_local()
        project = Project(
            id=uuid4().hex,
            name="no-env-project",
            source_type="local",
            local_path=tmpdir,
        )
        session.add(project)
        session.commit()
        project_id = project.id
        session.close()

        yield {"id": project_id, "path": tmpdir}


@pytest.fixture()
def project_without_local_path(client: TestClient):
    """Create a project without local path (github_only)."""
    session = client._test_session_local()
    project = Project(
        id=uuid4().hex,
        name="github-only-project",
        source_type="github_only",
        local_path=None,
    )
    session.add(project)
    session.commit()
    project_id = project.id
    session.close()

    return {"id": project_id}


class TestProjectEnvEndpoint:
    """Test GET /projects/{id}/env endpoint."""

    def test_get_env_with_both_files(self, client: TestClient, project_with_env: dict):
        """Should return both .env and .env.example contents."""
        resp = client.get(f"/api/v1/unified-projects/{project_with_env['id']}/env")

        assert resp.status_code == 200
        data = resp.json()

        assert data["has_env"] is True
        assert data["has_env_example"] is True

        # .env content (sensitive values masked)
        assert data["env_content"]["DATABASE_URL"] == "postgres://localhost:5432/db"
        assert data["env_content"]["API_KEY"] == "se••••45"  # Masked
        assert data["env_content"]["DEBUG"] == "true"

        # .env.example content (not masked)
        assert data["env_example_content"]["API_KEY"] == "your_api_key_here"

    def test_get_env_without_env_files(self, client: TestClient, project_without_env: dict):
        """Should return empty content when no .env files exist."""
        resp = client.get(f"/api/v1/unified-projects/{project_without_env['id']}/env")

        assert resp.status_code == 200
        data = resp.json()

        assert data["has_env"] is False
        assert data["has_env_example"] is False
        assert data["env_content"] == {}
        assert data["env_example_content"] is None

    def test_get_env_project_not_found(self, client: TestClient):
        """Should return 404 for non-existent project."""
        resp = client.get("/api/v1/unified-projects/nonexistent-id/env")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_env_no_local_path(self, client: TestClient, project_without_local_path: dict):
        """Should return 400 when project has no local path."""
        resp = client.get(f"/api/v1/unified-projects/{project_without_local_path['id']}/env")

        assert resp.status_code == 400
        assert "no local path" in resp.json()["detail"].lower()
