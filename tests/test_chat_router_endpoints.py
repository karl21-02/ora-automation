"""Tests for chat_router.py endpoints: reports, projects, conversations.

Uses shared `client` fixture from conftest.py.
Note: The client fixture mocks _scan_projects to return MOCK_PROJECTS.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ora_automation_api.schemas import ProjectInfo


# ── Projects Endpoint ─────────────────────────────────────────────────


class TestListProjects:
    def test_list_projects_returns_mock_projects(self, client):
        """Returns the mocked project list from conftest."""
        # The client fixture patches _scan_projects with MOCK_PROJECTS
        resp = client.get("/api/v1/projects")
        assert resp.status_code == 200
        data = resp.json()
        # MOCK_PROJECTS has OraAiServer, OraFrontend, OraInfra
        names = {p["name"] for p in data}
        assert "OraAiServer" in names
        assert "OraFrontend" in names
        assert "OraInfra" in names

    def test_list_projects_has_correct_fields(self, client):
        """Each project has required fields."""
        resp = client.get("/api/v1/projects")
        assert resp.status_code == 200
        for proj in resp.json():
            assert "name" in proj
            assert "path" in proj
            assert "has_makefile" in proj
            assert "has_dockerfile" in proj


# ── Reports Endpoint ──────────────────────────────────────────────────


class TestListReports:
    def test_list_reports_empty(self, client):
        """When report dirs are empty, returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            output_dir.mkdir()

            with patch("ora_automation_api.chat_router.settings") as mock_settings:
                mock_settings.run_output_dir = output_dir
                mock_settings.automation_root = root

                resp = client.get("/api/v1/reports")
                assert resp.status_code == 200
                assert resp.json() == []

    def test_list_reports_with_files(self, client):
        """Returns report info for .md and .json files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            output_dir.mkdir()

            # Create some reports
            (output_dir / "report1.md").write_text("# Report 1")
            (output_dir / "report2.json").write_text('{"key": "value"}')
            (output_dir / "nested").mkdir()
            (output_dir / "nested" / "report3.md").write_text("# Nested")
            # Non-report files should be excluded
            (output_dir / "readme.txt").write_text("ignore me")

            with patch("ora_automation_api.chat_router.settings") as mock_settings:
                mock_settings.run_output_dir = output_dir
                mock_settings.automation_root = root

                resp = client.get("/api/v1/reports")
                assert resp.status_code == 200
                data = resp.json()
                filenames = {r["filename"] for r in data}
                assert "report1.md" in filenames
                assert "report2.json" in filenames
                assert "nested/report3.md" in filenames
                assert "readme.txt" not in filenames

                # Check report_type
                md_report = next(r for r in data if r["filename"] == "report1.md")
                assert md_report["report_type"] == "markdown"

                json_report = next(r for r in data if r["filename"] == "report2.json")
                assert json_report["report_type"] == "json"


class TestGetReport:
    def test_get_report_success(self, client):
        """Successfully retrieves a report file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            output_dir.mkdir()
            (output_dir / "test.md").write_text("# Test Report\n\nContent here.")

            with patch("ora_automation_api.chat_router.settings") as mock_settings:
                mock_settings.run_output_dir = output_dir
                mock_settings.automation_root = root

                resp = client.get("/api/v1/reports/test.md")
                assert resp.status_code == 200
                assert "Test Report" in resp.text

    def test_get_report_not_found(self, client):
        """Returns 404 for non-existent report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_dir = root / "output"
            output_dir.mkdir()

            with patch("ora_automation_api.chat_router.settings") as mock_settings:
                mock_settings.run_output_dir = output_dir
                mock_settings.automation_root = root

                resp = client.get("/api/v1/reports/nonexistent.md")
                assert resp.status_code == 404

    def test_get_report_path_traversal_rejected(self, client):
        """Path traversal attempts are rejected with 400."""
        # ".." in filename triggers 400 before file lookup
        resp = client.get("/api/v1/reports/..%2F..%2Fetc%2Fpasswd")
        # URL-encoded ".." should be caught
        assert resp.status_code in (400, 404)  # Either is acceptable

    def test_get_report_dotdot_raw_rejected(self, client):
        """Raw .. in path is rejected."""
        resp = client.get("/api/v1/reports/subdir/../secret.md")
        assert resp.status_code in (400, 404)

    def test_get_report_absolute_path_rejected(self, client):
        """Absolute paths starting with / are rejected."""
        # Note: The endpoint path is /reports/{filename:path}
        # So /api/v1/reports//etc/passwd has filename="etc/passwd"
        resp = client.get("/api/v1/reports/%2Fetc%2Fpasswd")
        assert resp.status_code in (400, 404)


# ── Conversations Endpoint ────────────────────────────────────────────


class TestConversationsCRUD:
    def test_create_conversation(self, client):
        """Create a new conversation."""
        resp = client.post("/api/v1/conversations", json={
            "title": "Test Conversation",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Test Conversation"
        assert "id" in data

    def test_create_conversation_with_org(self, client):
        """Create conversation bound to an org."""
        # Create org first
        org_resp = client.post("/api/v1/orgs", json={"name": "ConvTestOrg"})
        org_id = org_resp.json()["id"]

        resp = client.post("/api/v1/conversations", json={
            "title": "Org Bound Conv",
            "org_id": org_id,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["org_id"] == org_id

    def test_list_conversations(self, client):
        """List conversations."""
        # Create some conversations
        client.post("/api/v1/conversations", json={"title": "Conv1"})
        client.post("/api/v1/conversations", json={"title": "Conv2"})

        resp = client.get("/api/v1/conversations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        titles = {c["title"] for c in data["items"]}
        assert "Conv1" in titles
        assert "Conv2" in titles

    def test_list_conversations_filter_by_org(self, client):
        """Filter conversations by org_id."""
        # Create org and conversation
        org_resp = client.post("/api/v1/orgs", json={"name": "FilterTestOrg"})
        org_id = org_resp.json()["id"]

        client.post("/api/v1/conversations", json={"title": "WithOrg", "org_id": org_id})
        client.post("/api/v1/conversations", json={"title": "NoOrg"})

        resp = client.get(f"/api/v1/conversations?org_id={org_id}")
        assert resp.status_code == 200
        data = resp.json()
        titles = {c["title"] for c in data["items"]}
        assert "WithOrg" in titles
        assert "NoOrg" not in titles

    def test_get_conversation_detail(self, client):
        """Get conversation with messages."""
        # Create conversation
        create_resp = client.post("/api/v1/conversations", json={"title": "DetailTest"})
        conv_id = create_resp.json()["id"]

        resp = client.get(f"/api/v1/conversations/{conv_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "DetailTest"
        assert "messages" in data

    def test_get_conversation_not_found(self, client):
        """404 for non-existent conversation."""
        resp = client.get("/api/v1/conversations/nonexistent-id")
        assert resp.status_code == 404

    def test_update_conversation_title(self, client):
        """Update conversation title."""
        create_resp = client.post("/api/v1/conversations", json={"title": "OldTitle"})
        conv_id = create_resp.json()["id"]

        resp = client.patch(f"/api/v1/conversations/{conv_id}", json={
            "title": "NewTitle",
        })
        assert resp.status_code == 200
        assert resp.json()["title"] == "NewTitle"

    def test_update_conversation_org(self, client):
        """Bind/unbind conversation to org."""
        # Create org
        org_resp = client.post("/api/v1/orgs", json={"name": "BindTestOrg"})
        org_id = org_resp.json()["id"]

        # Create conversation without org
        create_resp = client.post("/api/v1/conversations", json={"title": "BindTest"})
        conv_id = create_resp.json()["id"]

        # Bind to org
        resp = client.patch(f"/api/v1/conversations/{conv_id}", json={
            "org_id": org_id,
        })
        assert resp.status_code == 200
        assert resp.json()["org_id"] == org_id

        # Unbind (empty string)
        resp = client.patch(f"/api/v1/conversations/{conv_id}", json={
            "org_id": "",
        })
        assert resp.status_code == 200
        assert resp.json()["org_id"] is None

    def test_delete_conversation(self, client):
        """Delete conversation."""
        create_resp = client.post("/api/v1/conversations", json={"title": "ToDelete"})
        conv_id = create_resp.json()["id"]

        resp = client.delete(f"/api/v1/conversations/{conv_id}")
        assert resp.status_code == 204

        # Verify deleted
        get_resp = client.get(f"/api/v1/conversations/{conv_id}")
        assert get_resp.status_code == 404

    def test_delete_conversation_not_found(self, client):
        """404 when deleting non-existent conversation."""
        resp = client.delete("/api/v1/conversations/nonexistent")
        assert resp.status_code == 404
