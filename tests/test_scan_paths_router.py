"""API tests for Scan Paths router."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ora_automation_api.database import Base, get_db


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
            yield c

    main_module.app.dependency_overrides.clear()
    main_module.app.router.on_startup = orig_on_startup
    db_module.engine = orig_db_engine
    db_module.SessionLocal = orig_db_session_local
    test_engine.dispose()


@pytest.fixture()
def temp_workspace():
    """Create a temporary workspace with git repos."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create two fake git repos
        repo1 = Path(tmpdir) / "project-one"
        repo1.mkdir()
        (repo1 / ".git").mkdir()
        (repo1 / "package.json").write_text("{}")

        repo2 = Path(tmpdir) / "project-two"
        repo2.mkdir()
        (repo2 / ".git").mkdir()
        (repo2 / "pyproject.toml").write_text("[project]")

        yield tmpdir


class TestScanPathsCRUD:
    """Test Scan Paths CRUD endpoints."""

    def test_list_scan_paths_empty(self, client: TestClient):
        """Should return empty list when no scan paths exist."""
        resp = client.get("/api/v1/scan-paths")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_create_scan_path(self, client: TestClient, temp_workspace: str):
        """Should create a new scan path."""
        resp = client.post(
            "/api/v1/scan-paths",
            json={"path": temp_workspace, "name": "테스트", "recursive": False},
        )
        assert resp.status_code == 201
        data = resp.json()
        # Compare resolved paths (macOS /var → /private/var symlink)
        assert Path(data["path"]).resolve() == Path(temp_workspace).resolve()
        assert data["name"] == "테스트"
        assert data["enabled"] is True
        assert data["recursive"] is False
        assert data["project_count"] == 0
        assert "id" in data

    def test_create_scan_path_invalid_path(self, client: TestClient):
        """Should reject non-existent path."""
        resp = client.post(
            "/api/v1/scan-paths",
            json={"path": "/nonexistent/path/12345"},
        )
        assert resp.status_code == 400
        assert "does not exist" in resp.json()["detail"]

    def test_create_scan_path_duplicate(self, client: TestClient, temp_workspace: str):
        """Should reject duplicate path."""
        client.post("/api/v1/scan-paths", json={"path": temp_workspace})
        resp = client.post("/api/v1/scan-paths", json={"path": temp_workspace})
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]

    def test_get_scan_path(self, client: TestClient, temp_workspace: str):
        """Should get a scan path by ID."""
        create_resp = client.post("/api/v1/scan-paths", json={"path": temp_workspace})
        scan_path_id = create_resp.json()["id"]

        resp = client.get(f"/api/v1/scan-paths/{scan_path_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == scan_path_id

    def test_get_scan_path_not_found(self, client: TestClient):
        """Should return 404 for non-existent scan path."""
        resp = client.get("/api/v1/scan-paths/nonexistent")
        assert resp.status_code == 404

    def test_update_scan_path(self, client: TestClient, temp_workspace: str):
        """Should update a scan path."""
        create_resp = client.post("/api/v1/scan-paths", json={"path": temp_workspace})
        scan_path_id = create_resp.json()["id"]

        resp = client.patch(
            f"/api/v1/scan-paths/{scan_path_id}",
            json={"name": "업데이트됨", "enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "업데이트됨"
        assert resp.json()["enabled"] is False

    def test_delete_scan_path(self, client: TestClient, temp_workspace: str):
        """Should delete a scan path."""
        create_resp = client.post("/api/v1/scan-paths", json={"path": temp_workspace})
        scan_path_id = create_resp.json()["id"]

        resp = client.delete(f"/api/v1/scan-paths/{scan_path_id}")
        assert resp.status_code == 204

        # Verify deleted
        resp = client.get(f"/api/v1/scan-paths/{scan_path_id}")
        assert resp.status_code == 404

    def test_list_scan_paths_with_filter(self, client: TestClient, temp_workspace: str):
        """Should filter scan paths by enabled status."""
        # Create two scan paths
        with tempfile.TemporaryDirectory() as tmpdir2:
            resp1 = client.post("/api/v1/scan-paths", json={"path": temp_workspace})
            resp2 = client.post("/api/v1/scan-paths", json={"path": tmpdir2})

            # Disable one
            client.patch(f"/api/v1/scan-paths/{resp2.json()['id']}", json={"enabled": False})

            # Filter enabled only
            resp = client.get("/api/v1/scan-paths?enabled=true")
            assert resp.status_code == 200
            assert len(resp.json()["items"]) == 1
            assert resp.json()["items"][0]["enabled"] is True


class TestScanExecution:
    """Test scan execution endpoints."""

    def test_scan_path_creates_projects(self, client: TestClient, temp_workspace: str):
        """Should scan path and create projects."""
        # Create scan path
        create_resp = client.post("/api/v1/scan-paths", json={"path": temp_workspace})
        scan_path_id = create_resp.json()["id"]

        # Execute scan
        resp = client.post(f"/api/v1/scan-paths/{scan_path_id}/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert data["scan_path_id"] == scan_path_id
        assert data["projects_found"] == 2
        assert data["projects_created"] == 2
        assert data["projects_updated"] == 0
        assert data["duration_ms"] >= 0

        # Verify projects were created
        projects_resp = client.get("/api/v1/unified-projects")
        assert projects_resp.status_code == 200
        assert projects_resp.json()["total"] == 2

    def test_scan_disabled_path_fails(self, client: TestClient, temp_workspace: str):
        """Should reject scan on disabled path."""
        create_resp = client.post("/api/v1/scan-paths", json={"path": temp_workspace})
        scan_path_id = create_resp.json()["id"]

        # Disable
        client.patch(f"/api/v1/scan-paths/{scan_path_id}", json={"enabled": False})

        # Try to scan
        resp = client.post(f"/api/v1/scan-paths/{scan_path_id}/scan")
        assert resp.status_code == 400
        assert "disabled" in resp.json()["detail"]

    def test_scan_all_paths(self, client: TestClient, temp_workspace: str):
        """Should scan all enabled paths."""
        with tempfile.TemporaryDirectory() as tmpdir2:
            # Create fake repo in second dir
            repo = Path(tmpdir2) / "another-project"
            repo.mkdir()
            (repo / ".git").mkdir()

            # Create two scan paths
            client.post("/api/v1/scan-paths", json={"path": temp_workspace})
            client.post("/api/v1/scan-paths", json={"path": tmpdir2})

            # Scan all
            resp = client.post("/api/v1/scan-paths/scan-all")
            assert resp.status_code == 200
            results = resp.json()
            assert len(results) == 2

            total_found = sum(r["projects_found"] for r in results)
            assert total_found == 3  # 2 + 1

    def test_scan_updates_project_count(self, client: TestClient, temp_workspace: str):
        """Should update project_count after scan."""
        create_resp = client.post("/api/v1/scan-paths", json={"path": temp_workspace})
        scan_path_id = create_resp.json()["id"]

        # Initial count is 0
        assert create_resp.json()["project_count"] == 0

        # Scan
        client.post(f"/api/v1/scan-paths/{scan_path_id}/scan")

        # Check updated count
        resp = client.get(f"/api/v1/scan-paths/{scan_path_id}")
        assert resp.json()["project_count"] == 2

    def test_rescan_is_idempotent(self, client: TestClient, temp_workspace: str):
        """Should not duplicate projects on rescan."""
        create_resp = client.post("/api/v1/scan-paths", json={"path": temp_workspace})
        scan_path_id = create_resp.json()["id"]

        # First scan
        resp1 = client.post(f"/api/v1/scan-paths/{scan_path_id}/scan")
        assert resp1.json()["projects_created"] == 2

        # Second scan
        resp2 = client.post(f"/api/v1/scan-paths/{scan_path_id}/scan")
        assert resp2.json()["projects_created"] == 0
        assert resp2.json()["projects_found"] == 2

        # Still only 2 projects
        projects_resp = client.get("/api/v1/unified-projects")
        assert projects_resp.json()["total"] == 2
