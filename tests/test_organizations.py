"""Tests for Organization / OrganizationAgent CRUD, clone, preset seeding, org_id on run."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ora_automation_api.database import Base


@pytest.fixture()
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    # Enable FK constraints for SQLite (required for ON DELETE CASCADE)
    from sqlalchemy import event as sa_event

    @sa_event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


class TestOrganizationCRUD:
    def test_create_org(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization

        org = Organization(
            id=uuid4().hex[:36],
            name="Test Org",
            is_preset=False,
            teams={},
            flat_mode_agents=[],
            agent_final_weights={},
        )
        db.add(org)
        db.commit()
        db.refresh(org)

        assert org.id
        assert org.name == "Test Org"
        assert org.is_preset is False

    def test_org_name_unique(self, db):
        from uuid import uuid4
        from sqlalchemy.exc import IntegrityError
        from ora_automation_api.models import Organization

        org1 = Organization(id=uuid4().hex[:36], name="Unique", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org1)
        db.commit()

        org2 = Organization(id=uuid4().hex[:36], name="Unique", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org2)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


class TestOrganizationAgentCRUD:
    def test_create_agent(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization, OrganizationAgent

        org = Organization(id=uuid4().hex[:36], name="Org1", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org)
        db.commit()

        agent = OrganizationAgent(
            id=uuid4().hex[:36],
            org_id=org.id,
            agent_id="CEO",
            display_name="CEO",
            display_name_ko="CEO (대표)",
            role="ceo",
            tier=4,
            team="strategy",
            personality={"archetype": "leader"},
            behavioral_directives=["be bold"],
            constraints=["no risk"],
            decision_focus=["impact"],
            weights={"impact": 0.5},
            trust_map={"PM": 0.8},
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        assert agent.agent_id == "CEO"
        assert agent.tier == 4
        assert agent.personality["archetype"] == "leader"

    def test_agent_unique_per_org(self, db):
        from uuid import uuid4
        from sqlalchemy.exc import IntegrityError
        from ora_automation_api.models import Organization, OrganizationAgent

        org = Organization(id=uuid4().hex[:36], name="Org2", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org)
        db.commit()

        a1 = OrganizationAgent(id=uuid4().hex[:36], org_id=org.id, agent_id="PM", display_name="PM", weights={}, trust_map={}, personality={}, behavioral_directives=[], constraints=[], decision_focus=[])
        db.add(a1)
        db.commit()

        a2 = OrganizationAgent(id=uuid4().hex[:36], org_id=org.id, agent_id="PM", display_name="PM2", weights={}, trust_map={}, personality={}, behavioral_directives=[], constraints=[], decision_focus=[])
        db.add(a2)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_cascade_delete(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization, OrganizationAgent

        org = Organization(id=uuid4().hex[:36], name="Org3", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org)
        db.commit()

        agent = OrganizationAgent(id=uuid4().hex[:36], org_id=org.id, agent_id="QA", display_name="QA", weights={}, trust_map={}, personality={}, behavioral_directives=[], constraints=[], decision_focus=[])
        db.add(agent)
        db.commit()

        db.delete(org)
        db.commit()

        remaining = db.query(OrganizationAgent).filter(OrganizationAgent.org_id == org.id).all()
        assert len(remaining) == 0


class TestOrgIdOnRun:
    def test_run_with_org_id(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization, OrchestrationRun

        org = Organization(id=uuid4().hex[:36], name="RunOrg", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org)
        db.commit()

        run = OrchestrationRun(
            id=str(uuid4()),
            user_prompt="test",
            target="run-cycle",
            agent_role="engineer",
            org_id=org.id,
            command="in-process:run-cycle",
            env={},
            pipeline_stages=["analysis"],
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        assert run.org_id == org.id

    def test_run_without_org_id(self, db):
        from uuid import uuid4
        from ora_automation_api.models import OrchestrationRun

        run = OrchestrationRun(
            id=str(uuid4()),
            user_prompt="test",
            target="run-cycle",
            agent_role="engineer",
            command="in-process:run-cycle",
            env={},
            pipeline_stages=["analysis"],
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        assert run.org_id is None


class TestPersonaRegistryFromDicts:
    def test_from_agent_dicts(self):
        from ora_rd_orchestrator.personas import PersonaRegistry

        agents = [
            {
                "agent_id": "TestAgent",
                "display_name": "Test Agent",
                "display_name_ko": "테스트 에이전트",
                "role": "tester",
                "tier": 2,
                "team": "qa",
                "weights": {"impact": 0.5, "novelty": 0.3},
                "trust_map": {"PM": 0.8},
                "behavioral_directives": ["be thorough"],
                "constraints": ["no shortcuts"],
                "decision_focus": ["quality"],
            },
        ]
        reg = PersonaRegistry.from_agent_dicts(agents)
        assert len(reg) == 1
        assert "TestAgent" in reg
        persona = reg.get_persona("TestAgent")
        assert persona is not None
        assert persona.display_name == "Test Agent"
        assert persona.tier == 2
        assert persona.weights["impact"] == 0.5

    def test_disabled_agents_skipped(self):
        from ora_rd_orchestrator.personas import PersonaRegistry

        agents = [
            {"agent_id": "A", "display_name": "A", "role": "", "tier": 1, "enabled": True, "weights": {}, "trust_map": {}, "behavioral_directives": [], "constraints": [], "decision_focus": []},
            {"agent_id": "B", "display_name": "B", "role": "", "tier": 1, "enabled": False, "weights": {}, "trust_map": {}, "behavioral_directives": [], "constraints": [], "decision_focus": []},
        ]
        reg = PersonaRegistry.from_agent_dicts(agents)
        assert len(reg) == 1
        assert "A" in reg
        assert "B" not in reg

    def test_empty_agent_id_skipped(self):
        from ora_rd_orchestrator.personas import PersonaRegistry

        agents = [
            {"agent_id": "", "display_name": "NoId", "role": "", "tier": 1, "weights": {}, "trust_map": {}, "behavioral_directives": [], "constraints": [], "decision_focus": []},
        ]
        reg = PersonaRegistry.from_agent_dicts(agents)
        assert len(reg) == 0

    def test_to_agent_definitions_compat(self):
        from ora_rd_orchestrator.personas import PersonaRegistry

        agents = [
            {
                "agent_id": "X",
                "display_name": "X",
                "display_name_ko": "엑스",
                "role": "x",
                "tier": 3,
                "domain": "infra",
                "weights": {"impact": 0.4},
                "trust_map": {"Y": 0.9},
                "behavioral_directives": [],
                "constraints": [],
                "decision_focus": ["reliability"],
            },
        ]
        reg = PersonaRegistry.from_agent_dicts(agents)
        defs = reg.to_agent_definitions()
        assert "X" in defs
        assert defs["X"]["tier"] == 3
        assert defs["X"]["domain"] == "infra"
        assert defs["X"]["weights"] == {"impact": 0.4}
