"""Tests for Organization API endpoints (org_router.py).

Uses the shared `client` fixture from conftest.py which:
- Creates an in-memory SQLite database
- Overrides FastAPI dependencies
- Bypasses startup handlers (no real DB connection)
"""
from __future__ import annotations

import pytest


# ── Organization CRUD ─────────────────────────────────────────────


class TestListOrgs:
    def test_list_orgs_empty(self, client):
        resp = client.get("/api/v1/orgs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_orgs_returns_created(self, client):
        client.post("/api/v1/orgs", json={"name": "Org1"})
        client.post("/api/v1/orgs", json={"name": "Org2"})
        resp = client.get("/api/v1/orgs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        names = {item["name"] for item in data["items"]}
        assert names == {"Org1", "Org2"}


class TestCreateOrg:
    def test_create_org_minimal(self, client):
        resp = client.post("/api/v1/orgs", json={"name": "TestOrg"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "TestOrg"
        assert data["is_preset"] is False
        assert "id" in data

    def test_create_org_with_params(self, client):
        resp = client.post("/api/v1/orgs", json={
            "name": "CustomOrg",
            "description": "A test org",
            "pipeline_params": {"top_k": 8},
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["description"] == "A test org"
        assert data["pipeline_params"]["top_k"] == 8

    def test_create_org_duplicate_name_rejected(self, client):
        client.post("/api/v1/orgs", json={"name": "UniqueOrg"})
        resp = client.post("/api/v1/orgs", json={"name": "UniqueOrg"})
        assert resp.status_code == 409
        assert "already exists" in resp.json()["detail"]


class TestGetOrg:
    def test_get_org_by_id(self, client):
        create_resp = client.post("/api/v1/orgs", json={"name": "GetTest"})
        org_id = create_resp.json()["id"]

        resp = client.get(f"/api/v1/orgs/{org_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "GetTest"
        assert "agents" in data
        assert "silos" in data
        assert "chapters" in data

    def test_get_org_not_found(self, client):
        resp = client.get("/api/v1/orgs/nonexistent-id")
        assert resp.status_code == 404


class TestUpdateOrg:
    def test_update_org_name(self, client):
        create_resp = client.post("/api/v1/orgs", json={"name": "UpdateTest"})
        org_id = create_resp.json()["id"]

        resp = client.patch(f"/api/v1/orgs/{org_id}", json={"name": "UpdatedName"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "UpdatedName"

    def test_update_org_pipeline_params(self, client):
        create_resp = client.post("/api/v1/orgs", json={"name": "ParamsTest"})
        org_id = create_resp.json()["id"]

        resp = client.patch(f"/api/v1/orgs/{org_id}", json={
            "pipeline_params": {"level1_max_rounds": 10}
        })
        assert resp.status_code == 200
        assert resp.json()["pipeline_params"]["level1_max_rounds"] == 10

    def test_update_org_not_found(self, client):
        resp = client.patch("/api/v1/orgs/nonexistent", json={"name": "X"})
        assert resp.status_code == 404


class TestDeleteOrg:
    def test_delete_org(self, client):
        create_resp = client.post("/api/v1/orgs", json={"name": "ToDelete"})
        org_id = create_resp.json()["id"]

        resp = client.delete(f"/api/v1/orgs/{org_id}")
        assert resp.status_code == 204

        get_resp = client.get(f"/api/v1/orgs/{org_id}")
        assert get_resp.status_code == 404

    def test_delete_org_not_found(self, client):
        resp = client.delete("/api/v1/orgs/nonexistent")
        assert resp.status_code == 404


# ── Agent CRUD ────────────────────────────────────────────────────


class TestAgentCRUD:
    def test_create_agent(self, client):
        org_resp = client.post("/api/v1/orgs", json={"name": "AgentOrg"})
        org_id = org_resp.json()["id"]

        resp = client.post(f"/api/v1/orgs/{org_id}/agents", json={
            "agent_id": "TestAgent",
            "display_name": "Test Agent",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["agent_id"] == "TestAgent"
        assert data["org_id"] == org_id

    def test_create_agent_with_full_fields(self, client):
        org_resp = client.post("/api/v1/orgs", json={"name": "FullAgentOrg"})
        org_id = org_resp.json()["id"]

        resp = client.post(f"/api/v1/orgs/{org_id}/agents", json={
            "agent_id": "CEO",
            "display_name": "Chief Executive Officer",
            "display_name_ko": "대표이사",
            "role": "ceo",
            "tier": 4,
            "is_clevel": True,
            "weight_score": 2.0,
            "system_prompt_template": "You are the CEO.",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["is_clevel"] is True
        assert data["tier"] == 4
        assert data["weight_score"] == 2.0

    def test_create_agent_duplicate_rejected(self, client):
        org_resp = client.post("/api/v1/orgs", json={"name": "DupAgentOrg"})
        org_id = org_resp.json()["id"]

        client.post(f"/api/v1/orgs/{org_id}/agents", json={
            "agent_id": "DupAgent",
            "display_name": "Dup",
        })
        resp = client.post(f"/api/v1/orgs/{org_id}/agents", json={
            "agent_id": "DupAgent",
            "display_name": "Dup2",
        })
        assert resp.status_code == 409

    def test_create_agent_invalid_id_rejected(self, client):
        org_resp = client.post("/api/v1/orgs", json={"name": "InvalidAgentOrg"})
        org_id = org_resp.json()["id"]

        resp = client.post(f"/api/v1/orgs/{org_id}/agents", json={
            "agent_id": "123Invalid",
            "display_name": "Invalid",
        })
        assert resp.status_code == 422

    def test_update_agent(self, client):
        org_resp = client.post("/api/v1/orgs", json={"name": "UpdateAgentOrg"})
        org_id = org_resp.json()["id"]

        create_resp = client.post(f"/api/v1/orgs/{org_id}/agents", json={
            "agent_id": "ToUpdate",
            "display_name": "Original",
        })
        agent_id = create_resp.json()["id"]

        resp = client.patch(f"/api/v1/orgs/{org_id}/agents/{agent_id}", json={
            "display_name": "Updated Name",
            "weight_score": 1.5,
        })
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "Updated Name"
        assert resp.json()["weight_score"] == 1.5

    def test_delete_agent(self, client):
        org_resp = client.post("/api/v1/orgs", json={"name": "DeleteAgentOrg"})
        org_id = org_resp.json()["id"]

        create_resp = client.post(f"/api/v1/orgs/{org_id}/agents", json={
            "agent_id": "ToDelete",
            "display_name": "Delete Me",
        })
        agent_id = create_resp.json()["id"]

        resp = client.delete(f"/api/v1/orgs/{org_id}/agents/{agent_id}")
        assert resp.status_code == 204


# ── Silo CRUD ─────────────────────────────────────────────────────


class TestSiloCRUD:
    def test_create_silo(self, client):
        org_resp = client.post("/api/v1/orgs", json={"name": "SiloOrg"})
        org_id = org_resp.json()["id"]

        resp = client.post(f"/api/v1/orgs/{org_id}/silos", json={
            "name": "Research Silo",
            "description": "Research and analysis",
            "color": "#3b82f6",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Research Silo"
        assert data["color"] == "#3b82f6"

    def test_create_silo_duplicate_rejected(self, client):
        org_resp = client.post("/api/v1/orgs", json={"name": "DupSiloOrg"})
        org_id = org_resp.json()["id"]

        client.post(f"/api/v1/orgs/{org_id}/silos", json={"name": "DupSilo"})
        resp = client.post(f"/api/v1/orgs/{org_id}/silos", json={"name": "DupSilo"})
        assert resp.status_code == 409

    def test_update_silo(self, client):
        org_resp = client.post("/api/v1/orgs", json={"name": "UpdateSiloOrg"})
        org_id = org_resp.json()["id"]

        create_resp = client.post(f"/api/v1/orgs/{org_id}/silos", json={
            "name": "OldSilo",
        })
        silo_id = create_resp.json()["id"]

        resp = client.patch(f"/api/v1/orgs/{org_id}/silos/{silo_id}", json={
            "name": "NewSilo",
            "color": "#ef4444",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "NewSilo"
        assert resp.json()["color"] == "#ef4444"

    def test_delete_silo(self, client):
        org_resp = client.post("/api/v1/orgs", json={"name": "DeleteSiloOrg"})
        org_id = org_resp.json()["id"]

        create_resp = client.post(f"/api/v1/orgs/{org_id}/silos", json={
            "name": "ToDeleteSilo",
        })
        silo_id = create_resp.json()["id"]

        resp = client.delete(f"/api/v1/orgs/{org_id}/silos/{silo_id}")
        assert resp.status_code == 204


# ── Chapter CRUD ──────────────────────────────────────────────────


class TestChapterCRUD:
    def test_create_chapter(self, client):
        org_resp = client.post("/api/v1/orgs", json={"name": "ChapterOrg"})
        org_id = org_resp.json()["id"]

        resp = client.post(f"/api/v1/orgs/{org_id}/chapters", json={
            "name": "Engineering",
            "shared_directives": ["Consider tech debt"],
            "chapter_prompt": "You are part of Engineering chapter.",
            "icon": "📐",
            "color": "#3b82f6",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Engineering"
        assert data["shared_directives"] == ["Consider tech debt"]
        assert data["icon"] == "📐"

    def test_create_chapter_prompt_too_long_rejected(self, client):
        org_resp = client.post("/api/v1/orgs", json={"name": "LongPromptOrg"})
        org_id = org_resp.json()["id"]

        resp = client.post(f"/api/v1/orgs/{org_id}/chapters", json={
            "name": "TooLongChapter",
            "chapter_prompt": "X" * 2001,
        })
        assert resp.status_code == 422

    def test_update_chapter(self, client):
        org_resp = client.post("/api/v1/orgs", json={"name": "UpdateChapterOrg"})
        org_id = org_resp.json()["id"]

        create_resp = client.post(f"/api/v1/orgs/{org_id}/chapters", json={
            "name": "OldChapter",
        })
        chapter_id = create_resp.json()["id"]

        resp = client.patch(f"/api/v1/orgs/{org_id}/chapters/{chapter_id}", json={
            "name": "NewChapter",
            "shared_directives": ["New directive"],
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "NewChapter"
        assert resp.json()["shared_directives"] == ["New directive"]

    def test_delete_chapter(self, client):
        org_resp = client.post("/api/v1/orgs", json={"name": "DeleteChapterOrg"})
        org_id = org_resp.json()["id"]

        create_resp = client.post(f"/api/v1/orgs/{org_id}/chapters", json={
            "name": "ToDeleteChapter",
        })
        chapter_id = create_resp.json()["id"]

        resp = client.delete(f"/api/v1/orgs/{org_id}/chapters/{chapter_id}")
        assert resp.status_code == 204


# ── Clone ─────────────────────────────────────────────────────────


class TestCloneOrg:
    def test_clone_org_deep_copies_all(self, client):
        # Create source org with silo, chapter, agent
        org_resp = client.post("/api/v1/orgs", json={"name": "SourceOrg"})
        org_id = org_resp.json()["id"]

        silo_resp = client.post(f"/api/v1/orgs/{org_id}/silos", json={
            "name": "MySilo",
        })
        silo_id = silo_resp.json()["id"]

        chapter_resp = client.post(f"/api/v1/orgs/{org_id}/chapters", json={
            "name": "MyChapter",
            "shared_directives": ["directive1"],
        })
        chapter_id = chapter_resp.json()["id"]

        client.post(f"/api/v1/orgs/{org_id}/agents", json={
            "agent_id": "Worker",
            "display_name": "Worker",
            "silo_id": silo_id,
            "chapter_id": chapter_id,
        })

        # Clone
        clone_resp = client.post(f"/api/v1/orgs/{org_id}/clone", json={
            "name": "ClonedOrg",
        })
        assert clone_resp.status_code == 201
        data = clone_resp.json()

        assert data["name"] == "ClonedOrg"
        assert data["id"] != org_id
        assert len(data["silos"]) == 1
        assert len(data["chapters"]) == 1
        assert len(data["agents"]) == 1

        # Verify IDs are different
        assert data["silos"][0]["id"] != silo_id
        assert data["chapters"][0]["id"] != chapter_id

        # Verify agent's silo_id/chapter_id are remapped
        cloned_agent = data["agents"][0]
        assert cloned_agent["silo_id"] == data["silos"][0]["id"]
        assert cloned_agent["chapter_id"] == data["chapters"][0]["id"]

    def test_clone_org_duplicate_name_rejected(self, client):
        org_resp = client.post("/api/v1/orgs", json={"name": "CloneDupOrg"})
        org_id = org_resp.json()["id"]

        client.post("/api/v1/orgs", json={"name": "ExistingName"})
        resp = client.post(f"/api/v1/orgs/{org_id}/clone", json={
            "name": "ExistingName",
        })
        assert resp.status_code == 409
