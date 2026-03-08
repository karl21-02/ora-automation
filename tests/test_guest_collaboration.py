"""Tests for V2 Guest Collaboration feature.

Tests guest agent loading, merging, and pipeline integration.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from ora_automation_api.service import _load_guest_agents, _merge_guest_agents
from ora_automation_api.models import OrganizationAgent


class TestLoadGuestAgents:
    """Test _load_guest_agents function."""

    def test_load_single_guest_agent(self, client):
        """Load a single guest agent from another org."""
        # Create source org with an agent
        org_resp = client.post("/api/v1/orgs", json={"name": "SourceOrg"})
        org_id = org_resp.json()["id"]

        agent_resp = client.post(f"/api/v1/orgs/{org_id}/agents", json={
            "agent_id": "Expert",
            "display_name": "Domain Expert",
            "display_name_ko": "도메인 전문가",
            "tier": 3,
            "weight_score": 1.5,
        })
        assert agent_resp.status_code == 201

        # Use the DB session from the test
        from ora_automation_api.database import SessionLocal
        db = SessionLocal()
        try:
            guests = _load_guest_agents(db, [f"{org_id}:Expert"])
            assert len(guests) == 1
            guest = guests[0]
            assert guest["agent_id"] == "guest_Expert"
            assert guest["display_name"] == "[Guest] Domain Expert"
            assert guest["is_guest"] is True
            assert guest["is_clevel"] is True  # Guests participate in Level 3
            assert guest["source_org_id"] == org_id
            assert guest["weight_score"] == 1.5
        finally:
            db.close()

    def test_load_multiple_guest_agents(self, client):
        """Load multiple guest agents from different orgs."""
        # Create first org
        org1_resp = client.post("/api/v1/orgs", json={"name": "Org1"})
        org1_id = org1_resp.json()["id"]
        client.post(f"/api/v1/orgs/{org1_id}/agents", json={
            "agent_id": "Agent1",
            "display_name": "Agent One",
        })

        # Create second org
        org2_resp = client.post("/api/v1/orgs", json={"name": "Org2"})
        org2_id = org2_resp.json()["id"]
        client.post(f"/api/v1/orgs/{org2_id}/agents", json={
            "agent_id": "Agent2",
            "display_name": "Agent Two",
        })

        from ora_automation_api.database import SessionLocal
        db = SessionLocal()
        try:
            guests = _load_guest_agents(db, [f"{org1_id}:Agent1", f"{org2_id}:Agent2"])
            assert len(guests) == 2
            agent_ids = {g["agent_id"] for g in guests}
            assert agent_ids == {"guest_Agent1", "guest_Agent2"}
        finally:
            db.close()

    def test_load_guest_agent_invalid_format_skipped(self, client):
        """Invalid format (no colon) should be skipped."""
        from ora_automation_api.database import SessionLocal
        db = SessionLocal()
        try:
            guests = _load_guest_agents(db, ["invalid_format"])
            assert guests == []
        finally:
            db.close()

    def test_load_guest_agent_not_found_skipped(self, client):
        """Non-existent agent should be skipped."""
        from ora_automation_api.database import SessionLocal
        db = SessionLocal()
        try:
            guests = _load_guest_agents(db, ["nonexistent-org:NonExistent"])
            assert guests == []
        finally:
            db.close()

    def test_load_guest_agent_disabled_skipped(self, client):
        """Disabled agents should be skipped."""
        org_resp = client.post("/api/v1/orgs", json={"name": "DisabledAgentOrg"})
        org_id = org_resp.json()["id"]

        # Create and then disable agent
        agent_resp = client.post(f"/api/v1/orgs/{org_id}/agents", json={
            "agent_id": "DisabledAgent",
            "display_name": "Disabled",
            "enabled": False,
        })
        assert agent_resp.status_code == 201

        from ora_automation_api.database import SessionLocal
        db = SessionLocal()
        try:
            guests = _load_guest_agents(db, [f"{org_id}:DisabledAgent"])
            assert guests == []
        finally:
            db.close()


class TestMergeGuestAgents:
    """Test _merge_guest_agents function."""

    def test_merge_with_no_guests(self):
        """No guests means return original config unchanged."""
        org_config = {"org_id": "abc", "agents": [{"agent_id": "CEO"}]}
        result = _merge_guest_agents(org_config, [])
        assert result == org_config

    def test_merge_guests_into_none_config(self):
        """When no base config, create minimal config with guests."""
        guests = [
            {"agent_id": "guest_Expert", "display_name": "[Guest] Expert", "weight_score": 1.0},
        ]
        result = _merge_guest_agents(None, guests)
        assert result is not None
        assert result["org_id"] is None
        assert result["org_name"] == "Guest-only"
        assert len(result["agents"]) == 1
        assert result["agents"][0]["agent_id"] == "guest_Expert"
        assert "guest_Expert" in result["flat_mode_agents"]

    def test_merge_guests_into_existing_config(self):
        """Merge guests into existing org config."""
        org_config = {
            "org_id": "org123",
            "org_name": "MyOrg",
            "agents": [{"agent_id": "CEO", "weight_score": 2.0}],
            "flat_mode_agents": ["CEO"],
            "agent_final_weights": {"CEO": 2.0},
            "silos": [],
            "chapters": [],
        }
        guests = [
            {"agent_id": "guest_Expert", "display_name": "[Guest] Expert", "weight_score": 1.5},
        ]
        result = _merge_guest_agents(org_config, guests)

        # Original config preserved
        assert result["org_id"] == "org123"
        assert result["org_name"] == "MyOrg"

        # Guest added to agents
        assert len(result["agents"]) == 2
        agent_ids = {a["agent_id"] for a in result["agents"]}
        assert agent_ids == {"CEO", "guest_Expert"}

        # Guest added to flat_mode_agents
        assert "guest_Expert" in result["flat_mode_agents"]
        assert "CEO" in result["flat_mode_agents"]

        # Guest weight added
        assert result["agent_final_weights"]["guest_Expert"] == 1.5
        assert result["agent_final_weights"]["CEO"] == 2.0

    def test_merge_multiple_guests(self):
        """Merge multiple guests at once."""
        org_config = {
            "org_id": "org123",
            "agents": [],
            "flat_mode_agents": [],
            "agent_final_weights": {},
        }
        guests = [
            {"agent_id": "guest_A", "weight_score": 1.0},
            {"agent_id": "guest_B", "weight_score": 2.0},
        ]
        result = _merge_guest_agents(org_config, guests)

        assert len(result["agents"]) == 2
        assert set(result["flat_mode_agents"]) == {"guest_A", "guest_B"}
        assert result["agent_final_weights"]["guest_A"] == 1.0
        assert result["agent_final_weights"]["guest_B"] == 2.0


class TestGuestAgentE2E:
    """End-to-end test for guest collaboration via API."""

    def test_create_run_with_guest_agents(self, client):
        """Create orchestration run with guest_agent_ids field."""
        # Create source org with an agent
        org_resp = client.post("/api/v1/orgs", json={"name": "GuestSourceOrg"})
        org_id = org_resp.json()["id"]

        client.post(f"/api/v1/orgs/{org_id}/agents", json={
            "agent_id": "GuestWorker",
            "display_name": "Guest Worker",
        })

        # Create run with guest agent
        run_resp = client.post("/api/v1/orchestrations", json={
            "user_prompt": "Test with guest",
            "guest_agent_ids": [f"{org_id}:GuestWorker"],
            "dry_run": True,
        })
        assert run_resp.status_code == 202  # Accepted for async processing
        data = run_resp.json()
        assert data["guest_agent_ids"] == [f"{org_id}:GuestWorker"]

    def test_run_read_includes_guest_agents(self, client):
        """OrchestrationRunRead schema includes guest_agent_ids."""
        org_resp = client.post("/api/v1/orgs", json={"name": "ReadTestOrg"})
        org_id = org_resp.json()["id"]

        client.post(f"/api/v1/orgs/{org_id}/agents", json={
            "agent_id": "ReadTestAgent",
            "display_name": "Read Test Agent",
        })

        run_resp = client.post("/api/v1/orchestrations", json={
            "user_prompt": "Read test",
            "guest_agent_ids": [f"{org_id}:ReadTestAgent"],
            "dry_run": True,
        })
        run_id = run_resp.json()["id"]

        get_resp = client.get(f"/api/v1/orchestrations/{run_id}")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert f"{org_id}:ReadTestAgent" in data["guest_agent_ids"]

    def test_run_without_guests_has_empty_list(self, client):
        """Run without guest_agent_ids has empty list."""
        run_resp = client.post("/api/v1/orchestrations", json={
            "user_prompt": "No guests",
            "dry_run": True,
        })
        assert run_resp.status_code == 202
        data = run_resp.json()
        assert data["guest_agent_ids"] == []

    def test_run_with_invalid_guest_format(self, client):
        """Invalid guest format is stored but skipped during load."""
        run_resp = client.post("/api/v1/orchestrations", json={
            "user_prompt": "Invalid guest format",
            "guest_agent_ids": ["invalid_no_colon"],
            "dry_run": True,
        })
        assert run_resp.status_code == 202
        data = run_resp.json()
        # Invalid format is still stored
        assert data["guest_agent_ids"] == ["invalid_no_colon"]

    def test_run_with_nonexistent_guest(self, client):
        """Non-existent guest agent is stored but skipped during load."""
        run_resp = client.post("/api/v1/orchestrations", json={
            "user_prompt": "Nonexistent guest",
            "guest_agent_ids": ["nonexistent-org:NonExistent"],
            "dry_run": True,
        })
        assert run_resp.status_code == 202
        data = run_resp.json()
        assert data["guest_agent_ids"] == ["nonexistent-org:NonExistent"]


class TestGuestAgentFieldValidation:
    """Test guest_agent_ids field validation."""

    def test_guest_agent_ids_accepts_list(self, client):
        """guest_agent_ids accepts a list of strings."""
        run_resp = client.post("/api/v1/orchestrations", json={
            "user_prompt": "Test",
            "guest_agent_ids": ["org1:agent1", "org2:agent2"],
            "dry_run": True,
        })
        assert run_resp.status_code == 202
        assert run_resp.json()["guest_agent_ids"] == ["org1:agent1", "org2:agent2"]

    def test_guest_agent_ids_default_empty(self, client):
        """guest_agent_ids defaults to empty list if not provided."""
        run_resp = client.post("/api/v1/orchestrations", json={
            "user_prompt": "Test without guests",
            "dry_run": True,
        })
        assert run_resp.status_code == 202
        assert run_resp.json()["guest_agent_ids"] == []
