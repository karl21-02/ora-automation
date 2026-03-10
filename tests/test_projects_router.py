"""Tests for unified projects API endpoints."""
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
def db(client):
    """Get a database session from the test client."""
    import ora_automation_api.database as db_module
    session = db_module.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def github_installation(db):
    """Create a test GitHub installation."""
    inst = GithubInstallation(
        id=uuid4().hex,
        installation_id=12345,
        account_type="Organization",
        account_login="test-org",
        account_id=1234,
    )
    db.add(inst)
    db.commit()
    return inst


@pytest.fixture
def github_repo(db, github_installation):
    """Create a test GitHub repo."""
    repo = GithubRepo(
        id=uuid4().hex,
        installation_id=github_installation.id,
        repo_id=67890,
        name="test-repo",
        full_name="test-org/test-repo",
        html_url="https://github.com/test-org/test-repo",
        clone_url="https://github.com/test-org/test-repo.git",
        default_branch="main",
    )
    db.add(repo)
    db.commit()
    return repo


@pytest.fixture
def sample_project(db):
    """Create a sample project."""
    project = Project(
        id=uuid4().hex,
        name="sample-project",
        description="A sample project",
        source_type="local",
        local_path="/workspace/sample-project",
        enabled=True,
        language="Python",
    )
    db.add(project)
    db.commit()
    return project


# ── GET /unified-projects Tests ───────────────────────────────────────


def test_list_projects_empty(client):
    """Test listing projects when none exist."""
    resp = client.get("/api/v1/unified-projects")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


def test_list_projects_with_data(client, sample_project):
    """Test listing projects returns data."""
    resp = client.get("/api/v1/unified-projects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["total"] == 1
    assert data["items"][0]["name"] == "sample-project"


def test_list_projects_filter_source_type(client, db, sample_project):
    """Test filtering by source_type."""
    # Add another project with different source type
    github_project = Project(
        id=uuid4().hex,
        name="github-project",
        source_type="github",
    )
    db.add(github_project)
    db.commit()

    resp = client.get("/api/v1/unified-projects?source_type=local")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "sample-project"


def test_list_projects_filter_enabled(client, db, sample_project):
    """Test filtering by enabled status."""
    disabled_project = Project(
        id=uuid4().hex,
        name="disabled-project",
        source_type="local",
        enabled=False,
    )
    db.add(disabled_project)
    db.commit()

    resp = client.get("/api/v1/unified-projects?enabled=true")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "sample-project"


def test_list_projects_search(client, db, sample_project):
    """Test search by name."""
    other_project = Project(
        id=uuid4().hex,
        name="other-project",
        source_type="local",
    )
    db.add(other_project)
    db.commit()

    resp = client.get("/api/v1/unified-projects?search=sample")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "sample-project"


def test_list_projects_pagination(client, db):
    """Test pagination."""
    # Create 5 projects
    for i in range(5):
        p = Project(id=uuid4().hex, name=f"project-{i:02d}", source_type="local")
        db.add(p)
    db.commit()

    resp = client.get("/api/v1/unified-projects?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2
    assert data["total"] == 5

    resp = client.get("/api/v1/unified-projects?limit=2&offset=2")
    data = resp.json()
    assert len(data["items"]) == 2


# ── POST /unified-projects Tests ──────────────────────────────────────


def test_create_project(client):
    """Test creating a new project."""
    resp = client.post("/api/v1/unified-projects", json={
        "name": "new-project",
        "description": "A new project",
        "source_type": "local",
        "local_path": "/workspace/new-project",
        "language": "Go",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "new-project"
    assert data["source_type"] == "local"
    assert data["language"] == "Go"


def test_create_project_duplicate_path(client, sample_project):
    """Test creating project with duplicate local_path fails."""
    resp = client.post("/api/v1/unified-projects", json={
        "name": "another-project",
        "local_path": "/workspace/sample-project",  # Same as sample_project
    })
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_create_project_with_github_repo(client, github_repo):
    """Test creating project linked to GitHub repo."""
    resp = client.post("/api/v1/unified-projects", json={
        "name": "github-linked",
        "source_type": "github",
        "github_repo_id": github_repo.id,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["github_repo_id"] == github_repo.id


def test_create_project_invalid_github_repo(client):
    """Test creating project with invalid GitHub repo fails."""
    resp = client.post("/api/v1/unified-projects", json={
        "name": "invalid-link",
        "github_repo_id": "nonexistent-id",
    })
    assert resp.status_code == 404
    assert "GitHub repo not found" in resp.json()["detail"]


# ── GET /unified-projects/{id} Tests ──────────────────────────────────


def test_get_project(client, sample_project):
    """Test getting a project by ID."""
    resp = client.get(f"/api/v1/unified-projects/{sample_project.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sample_project.id
    assert data["name"] == "sample-project"


def test_get_project_not_found(client):
    """Test getting nonexistent project."""
    resp = client.get("/api/v1/unified-projects/nonexistent")
    assert resp.status_code == 404


# ── PATCH /unified-projects/{id} Tests ────────────────────────────────


def test_update_project(client, sample_project):
    """Test updating a project."""
    resp = client.patch(f"/api/v1/unified-projects/{sample_project.id}", json={
        "description": "Updated description",
        "language": "TypeScript",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["description"] == "Updated description"
    assert data["language"] == "TypeScript"
    assert data["name"] == "sample-project"  # Unchanged


def test_update_project_not_found(client):
    """Test updating nonexistent project."""
    resp = client.patch("/api/v1/unified-projects/nonexistent", json={
        "name": "updated",
    })
    assert resp.status_code == 404


def test_update_project_duplicate_path(client, db, sample_project):
    """Test updating project with duplicate local_path fails."""
    other = Project(
        id=uuid4().hex,
        name="other",
        local_path="/workspace/other",
        source_type="local",
    )
    db.add(other)
    db.commit()

    resp = client.patch(f"/api/v1/unified-projects/{sample_project.id}", json={
        "local_path": "/workspace/other",  # Already used by other
    })
    assert resp.status_code == 409


# ── DELETE /unified-projects/{id} Tests ───────────────────────────────


def test_delete_project(client, sample_project, db):
    """Test deleting a project."""
    resp = client.delete(f"/api/v1/unified-projects/{sample_project.id}")
    assert resp.status_code == 204

    # Verify deletion
    remaining = db.query(Project).filter(Project.id == sample_project.id).first()
    assert remaining is None


def test_delete_project_not_found(client):
    """Test deleting nonexistent project."""
    resp = client.delete("/api/v1/unified-projects/nonexistent")
    assert resp.status_code == 404


# ── POST /unified-projects/scan-local Tests ───────────────────────────


def test_scan_local(client):
    """Test scanning local workspace."""
    with patch("ora_automation_api.projects_router.sync_local_workspace") as mock_sync:
        mock_sync.return_value = {"created": 3, "updated": 1, "unchanged": 2}

        resp = client.post("/api/v1/unified-projects/scan-local")
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] == 3
        assert data["updated"] == 1
        assert data["unchanged"] == 2


# ── POST /unified-projects/{id}/prepare Tests ─────────────────────────


def test_prepare_project_local_exists(client, sample_project):
    """Test prepare returns existing local path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Update project to use temp path
        sample_project.local_path = tmpdir
        client.patch(f"/api/v1/unified-projects/{sample_project.id}", json={
            "local_path": tmpdir,
        })

        resp = client.post(f"/api/v1/unified-projects/{sample_project.id}/prepare")
        assert resp.status_code == 200
        data = resp.json()
        assert data["local_path"] == tmpdir
        assert data["cloned"] is False


def test_prepare_project_needs_clone(client, db, github_repo):
    """Test prepare clones github_only project."""
    project = Project(
        id=uuid4().hex,
        name="github-only-project",
        source_type="github_only",
        github_repo_id=github_repo.id,
    )
    db.add(project)
    db.commit()

    with patch("ora_automation_api.clone_service.is_cloned", return_value=False):
        with patch("ora_automation_api.clone_service.ensure_local_clone") as mock_clone:
            mock_clone.return_value = Path("/tmp/ora-clones/test-org/test-repo")

            resp = client.post(f"/api/v1/unified-projects/{project.id}/prepare")
            assert resp.status_code == 200
            data = resp.json()
            assert "test-repo" in data["local_path"]
            assert data["cloned"] is True


def test_prepare_project_no_github_link(client, db):
    """Test prepare fails for project without local path or GitHub link."""
    project = Project(
        id=uuid4().hex,
        name="orphan-project",
        source_type="local",
        # No local_path and no github_repo_id
    )
    db.add(project)
    db.commit()

    resp = client.post(f"/api/v1/unified-projects/{project.id}/prepare")
    assert resp.status_code == 400
    assert "no local path and no GitHub repo" in resp.json()["detail"]


def test_prepare_project_not_found(client):
    """Test prepare for nonexistent project."""
    resp = client.post("/api/v1/unified-projects/nonexistent/prepare")
    assert resp.status_code == 404
