"""Tests for GitHub and Projects API routers."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ora_automation_api.database import Base, get_db
from ora_automation_api.models import GithubInstallation, GithubRepo, Project


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def client():
    """TestClient with in-memory SQLite database."""
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

    # Save originals
    orig_db_engine = db_module.engine
    orig_db_session_local = db_module.SessionLocal

    # Patch
    db_module.engine = test_engine
    db_module.SessionLocal = TestSessionLocal
    main_module.app.dependency_overrides[get_db] = override_get_db

    # Skip startup
    orig_on_startup = list(main_module.app.router.on_startup)
    main_module.app.router.on_startup = []

    with patch.dict(os.environ, {"TESTING": "1"}):
        with TestClient(main_module.app) as c:
            yield c

    # Restore
    main_module.app.dependency_overrides.clear()
    main_module.app.router.on_startup = orig_on_startup
    db_module.engine = orig_db_engine
    db_module.SessionLocal = orig_db_session_local
    test_engine.dispose()


@pytest.fixture()
def db_session(client):
    """Get a database session from the test client."""
    import ora_automation_api.database as db_module
    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ── GitHub Router Tests ──────────────────────────────────────────────


def test_get_install_url(client):
    """Test GET /api/v1/github/install-url."""
    resp = client.get("/api/v1/github/install-url")
    assert resp.status_code == 200
    data = resp.json()
    assert "url" in data
    assert "github.com/apps" in data["url"]


def test_list_installations_empty(client):
    """Test GET /api/v1/github/installations with no data."""
    resp = client.get("/api/v1/github/installations")
    assert resp.status_code == 200
    assert resp.json() == []


def test_webhook_installation_created(client, db_session):
    """Test POST /api/v1/github/webhook for installation.created."""
    payload = {
        "action": "created",
        "installation": {
            "id": 12345,
            "account": {
                "type": "Organization",
                "login": "test-org",
                "id": 67890,
                "avatar_url": "https://avatars.githubusercontent.com/u/67890",
            },
        },
    }
    resp = client.post(
        "/api/v1/github/webhook",
        json=payload,
        headers={"X-GitHub-Event": "installation"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "created"

    # Verify installation was saved
    inst = db_session.query(GithubInstallation).filter_by(installation_id=12345).first()
    assert inst is not None
    assert inst.account_login == "test-org"


def test_webhook_installation_deleted(client, db_session):
    """Test POST /api/v1/github/webhook for installation.deleted."""
    # First create an installation
    inst = GithubInstallation(
        id="inst-001",
        installation_id=12345,
        account_type="Organization",
        account_login="test-org",
        account_id=67890,
        status="active",
    )
    db_session.add(inst)
    db_session.commit()

    # Send delete webhook
    payload = {
        "action": "deleted",
        "installation": {"id": 12345},
    }
    resp = client.post(
        "/api/v1/github/webhook",
        json=payload,
        headers={"X-GitHub-Event": "installation"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # Verify status changed
    db_session.expire_all()
    inst = db_session.query(GithubInstallation).filter_by(installation_id=12345).first()
    assert inst.status == "deleted"


def test_list_installations_with_data(client, db_session):
    """Test GET /api/v1/github/installations with data."""
    inst = GithubInstallation(
        id="inst-001",
        installation_id=12345,
        account_type="Organization",
        account_login="test-org",
        account_id=67890,
        status="active",
    )
    db_session.add(inst)
    db_session.commit()

    resp = client.get("/api/v1/github/installations")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["account_login"] == "test-org"


def test_delete_installation(client, db_session):
    """Test DELETE /api/v1/github/installations/{id}."""
    inst = GithubInstallation(
        id="inst-001",
        installation_id=12345,
        account_type="Organization",
        account_login="test-org",
        account_id=67890,
        status="active",
    )
    db_session.add(inst)
    db_session.commit()

    resp = client.delete("/api/v1/github/installations/inst-001")
    assert resp.status_code == 204

    # Verify soft delete
    db_session.expire_all()
    inst = db_session.query(GithubInstallation).filter_by(id="inst-001").first()
    assert inst.status == "deleted"


def test_list_repos_empty(client):
    """Test GET /api/v1/github/repos with no data."""
    resp = client.get("/api/v1/github/repos")
    assert resp.status_code == 200
    assert resp.json() == []


# ── Projects Router Tests ──────────────────────────────────────────────


def test_list_projects_empty(client):
    """Test GET /api/v1/unified-projects with no data."""
    resp = client.get("/api/v1/unified-projects")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_create_project(client):
    """Test POST /api/v1/unified-projects."""
    payload = {
        "name": "TestProject",
        "description": "A test project",
        "source_type": "local",
        "local_path": "/workspace/TestProject",
        "language": "Python",
    }
    resp = client.post("/api/v1/unified-projects", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "TestProject"
    assert data["source_type"] == "local"
    assert data["local_path"] == "/workspace/TestProject"


def test_create_project_duplicate_path(client):
    """Test POST /api/v1/unified-projects with duplicate local_path."""
    payload = {
        "name": "TestProject",
        "local_path": "/workspace/TestProject",
    }
    resp = client.post("/api/v1/unified-projects", json=payload)
    assert resp.status_code == 201

    # Try to create another with same path
    payload["name"] = "TestProject2"
    resp = client.post("/api/v1/unified-projects", json=payload)
    assert resp.status_code == 409


def test_get_project(client, db_session):
    """Test GET /api/v1/unified-projects/{id}."""
    project = Project(
        id="proj-001",
        name="TestProject",
        source_type="local",
        local_path="/workspace/TestProject",
    )
    db_session.add(project)
    db_session.commit()

    resp = client.get("/api/v1/unified-projects/proj-001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "TestProject"


def test_get_project_not_found(client):
    """Test GET /api/v1/unified-projects/{id} with invalid ID."""
    resp = client.get("/api/v1/unified-projects/nonexistent")
    assert resp.status_code == 404


def test_update_project(client, db_session):
    """Test PATCH /api/v1/unified-projects/{id}."""
    project = Project(
        id="proj-001",
        name="TestProject",
        source_type="local",
        local_path="/workspace/TestProject",
    )
    db_session.add(project)
    db_session.commit()

    resp = client.patch(
        "/api/v1/unified-projects/proj-001",
        json={"name": "UpdatedProject", "enabled": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "UpdatedProject"
    assert data["enabled"] is False


def test_delete_project(client, db_session):
    """Test DELETE /api/v1/unified-projects/{id}."""
    project = Project(
        id="proj-001",
        name="TestProject",
        source_type="local",
    )
    db_session.add(project)
    db_session.commit()

    resp = client.delete("/api/v1/unified-projects/proj-001")
    assert resp.status_code == 204

    # Verify deletion
    db_session.expire_all()
    project = db_session.query(Project).filter_by(id="proj-001").first()
    assert project is None


def test_list_projects_with_filters(client, db_session):
    """Test GET /api/v1/unified-projects with filters."""
    projects = [
        Project(id="proj-001", name="LocalProject", source_type="local", enabled=True),
        Project(id="proj-002", name="GitHubProject", source_type="github", enabled=True),
        Project(id="proj-003", name="DisabledProject", source_type="local", enabled=False),
    ]
    db_session.add_all(projects)
    db_session.commit()

    # Filter by source_type
    resp = client.get("/api/v1/unified-projects?source_type=local")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2

    # Filter by enabled
    resp = client.get("/api/v1/unified-projects?enabled=true")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2

    # Search by name
    resp = client.get("/api/v1/unified-projects?search=GitHub")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["name"] == "GitHubProject"


def test_scan_local_returns_result(client):
    """Test POST /api/v1/unified-projects/scan-local returns result format."""
    with patch("ora_automation_api.projects_router.sync_local_workspace") as mock_sync:
        mock_sync.return_value = {"created": 2, "updated": 1, "unchanged": 3}
        resp = client.post("/api/v1/unified-projects/scan-local")
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] == 2
        assert data["updated"] == 1
        assert data["unchanged"] == 3
