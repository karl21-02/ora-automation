"""API tests for project config endpoint."""
from __future__ import annotations

import json
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
            c._test_session_local = TestSessionLocal
            yield c

    main_module.app.dependency_overrides.clear()
    main_module.app.router.on_startup = orig_on_startup
    db_module.engine = orig_db_engine
    db_module.SessionLocal = orig_db_session_local
    test_engine.dispose()


@pytest.fixture()
def project_with_configs(client: TestClient):
    """Create a project with config files in temp directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create package.json
        pkg_json = Path(tmpdir) / "package.json"
        pkg_json.write_text(json.dumps({
            "name": "test-project",
            "version": "1.0.0",
            "dependencies": {"react": "^18.0.0"}
        }))

        # Create Makefile
        makefile = Path(tmpdir) / "Makefile"
        makefile.write_text("all:\n\techo hello\n\ntest:\n\tpytest\n")

        # Create project in DB
        session = client._test_session_local()
        project = Project(
            id=uuid4().hex,
            name="config-test-project",
            source_type="local",
            local_path=tmpdir,
        )
        session.add(project)
        session.commit()
        project_id = project.id
        session.close()

        yield {"id": project_id, "path": tmpdir}


@pytest.fixture()
def project_without_configs(client: TestClient):
    """Create a project without config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        session = client._test_session_local()
        project = Project(
            id=uuid4().hex,
            name="no-config-project",
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
    """Create a project without local path."""
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


class TestProjectConfigEndpoint:
    """Test GET /projects/{id}/config endpoint."""

    def test_get_config_with_files(self, client: TestClient, project_with_configs: dict):
        """Should return config files."""
        resp = client.get(f"/api/v1/unified-projects/{project_with_configs['id']}/config")

        assert resp.status_code == 200
        data = resp.json()

        assert "files" in data
        assert len(data["files"]) == 2

        # Check package.json
        pkg = next(f for f in data["files"] if f["name"] == "package.json")
        assert pkg["type"] == "json"
        assert pkg["content"]["name"] == "test-project"
        assert pkg["content"]["version"] == "1.0.0"

        # Check Makefile
        make = next(f for f in data["files"] if f["name"] == "Makefile")
        assert make["type"] == "text"
        assert "echo hello" in make["content"]

    def test_get_config_without_files(self, client: TestClient, project_without_configs: dict):
        """Should return empty files list when no configs exist."""
        resp = client.get(f"/api/v1/unified-projects/{project_without_configs['id']}/config")

        assert resp.status_code == 200
        data = resp.json()

        assert data["files"] == []

    def test_get_config_project_not_found(self, client: TestClient):
        """Should return 404 for non-existent project."""
        resp = client.get("/api/v1/unified-projects/nonexistent-id/config")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_config_no_local_path(self, client: TestClient, project_without_local_path: dict):
        """Should return 400 when project has no local path."""
        resp = client.get(f"/api/v1/unified-projects/{project_without_local_path['id']}/config")

        assert resp.status_code == 400
        assert "no local path" in resp.json()["detail"].lower()
