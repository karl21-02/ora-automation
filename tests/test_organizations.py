"""Tests for Organization / OrganizationAgent / Silo / Chapter CRUD, clone, preset seeding, org_id on run."""
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


class TestSiloCRUD:
    def test_create_silo(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization, OrganizationSilo

        org = Organization(id=uuid4().hex[:36], name="SiloOrg", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org)
        db.commit()

        silo = OrganizationSilo(
            id=uuid4().hex[:36],
            org_id=org.id,
            name="research_intelligence",
            description="Research silo",
            color="#3b82f6",
            sort_order=0,
        )
        db.add(silo)
        db.commit()
        db.refresh(silo)

        assert silo.name == "research_intelligence"
        assert silo.org_id == org.id
        assert silo.color == "#3b82f6"

    def test_silo_unique_per_org(self, db):
        from uuid import uuid4
        from sqlalchemy.exc import IntegrityError
        from ora_automation_api.models import Organization, OrganizationSilo

        org = Organization(id=uuid4().hex[:36], name="SiloUniqueOrg", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org)
        db.commit()

        s1 = OrganizationSilo(id=uuid4().hex[:36], org_id=org.id, name="DupSilo")
        db.add(s1)
        db.commit()

        s2 = OrganizationSilo(id=uuid4().hex[:36], org_id=org.id, name="DupSilo")
        db.add(s2)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_cascade_delete_silos(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization, OrganizationSilo

        org = Organization(id=uuid4().hex[:36], name="SiloCascadeOrg", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org)
        db.commit()

        silo = OrganizationSilo(id=uuid4().hex[:36], org_id=org.id, name="ToDelete")
        db.add(silo)
        db.commit()

        db.delete(org)
        db.commit()

        remaining = db.query(OrganizationSilo).filter(OrganizationSilo.org_id == org.id).all()
        assert len(remaining) == 0

    def test_delete_silo_nullifies_agent(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization, OrganizationSilo, OrganizationAgent

        org = Organization(id=uuid4().hex[:36], name="SiloNullOrg", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org)
        db.commit()

        silo = OrganizationSilo(id=uuid4().hex[:36], org_id=org.id, name="NullSilo")
        db.add(silo)
        db.commit()

        agent = OrganizationAgent(
            id=uuid4().hex[:36], org_id=org.id, agent_id="A1", display_name="A1",
            silo_id=silo.id, weights={}, trust_map={}, personality={},
            behavioral_directives=[], constraints=[], decision_focus=[],
        )
        db.add(agent)
        db.commit()

        assert agent.silo_id == silo.id

        db.delete(silo)
        db.commit()
        db.refresh(agent)

        assert agent.silo_id is None


class TestChapterCRUD:
    def test_create_chapter(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization, OrganizationChapter

        org = Organization(id=uuid4().hex[:36], name="ChapterOrg", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org)
        db.commit()

        chapter = OrganizationChapter(
            id=uuid4().hex[:36],
            org_id=org.id,
            name="scoring_chapter",
            description="Scoring chapter",
            shared_directives=["be fair"],
            shared_constraints=["no bias"],
            shared_decision_focus=["accuracy"],
            chapter_prompt="Score carefully.",
            color="#8b5cf6",
            icon="🎯",
        )
        db.add(chapter)
        db.commit()
        db.refresh(chapter)

        assert chapter.name == "scoring_chapter"
        assert chapter.shared_directives == ["be fair"]
        assert chapter.icon == "🎯"

    def test_chapter_unique_per_org(self, db):
        from uuid import uuid4
        from sqlalchemy.exc import IntegrityError
        from ora_automation_api.models import Organization, OrganizationChapter

        org = Organization(id=uuid4().hex[:36], name="ChUniqueOrg", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org)
        db.commit()

        c1 = OrganizationChapter(id=uuid4().hex[:36], org_id=org.id, name="DupChap")
        db.add(c1)
        db.commit()

        c2 = OrganizationChapter(id=uuid4().hex[:36], org_id=org.id, name="DupChap")
        db.add(c2)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_cascade_delete_chapters(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization, OrganizationChapter

        org = Organization(id=uuid4().hex[:36], name="ChCascadeOrg", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org)
        db.commit()

        chapter = OrganizationChapter(id=uuid4().hex[:36], org_id=org.id, name="ToDeleteCh")
        db.add(chapter)
        db.commit()

        db.delete(org)
        db.commit()

        remaining = db.query(OrganizationChapter).filter(OrganizationChapter.org_id == org.id).all()
        assert len(remaining) == 0

    def test_shared_directives_stored(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization, OrganizationChapter

        org = Organization(id=uuid4().hex[:36], name="ChDirectivesOrg", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org)
        db.commit()

        directives = ["analyze deeply", "cite sources", "be concise"]
        chapter = OrganizationChapter(
            id=uuid4().hex[:36], org_id=org.id, name="ResearchCh",
            shared_directives=directives,
        )
        db.add(chapter)
        db.commit()
        db.refresh(chapter)

        assert chapter.shared_directives == directives


class TestAgentSiloChapter:
    def test_agent_with_silo_and_chapter(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization, OrganizationSilo, OrganizationChapter, OrganizationAgent

        org = Organization(id=uuid4().hex[:36], name="AgentSCOrg", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org)
        db.commit()

        silo = OrganizationSilo(id=uuid4().hex[:36], org_id=org.id, name="TestSilo")
        chapter = OrganizationChapter(id=uuid4().hex[:36], org_id=org.id, name="TestChapter")
        db.add_all([silo, chapter])
        db.commit()

        agent = OrganizationAgent(
            id=uuid4().hex[:36], org_id=org.id, agent_id="Worker1", display_name="Worker 1",
            silo_id=silo.id, chapter_id=chapter.id, is_clevel=False, weight_score=1.5,
            weights={}, trust_map={}, personality={},
            behavioral_directives=[], constraints=[], decision_focus=[],
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        assert agent.silo_id == silo.id
        assert agent.chapter_id == chapter.id
        assert agent.is_clevel is False
        assert agent.weight_score == 1.5

    def test_clevel_agent_no_silo_chapter(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization, OrganizationAgent

        org = Organization(id=uuid4().hex[:36], name="CLevelOrg", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org)
        db.commit()

        agent = OrganizationAgent(
            id=uuid4().hex[:36], org_id=org.id, agent_id="CEO", display_name="CEO",
            silo_id=None, chapter_id=None, is_clevel=True, weight_score=2.0,
            weights={}, trust_map={}, personality={},
            behavioral_directives=[], constraints=[], decision_focus=[],
        )
        db.add(agent)
        db.commit()
        db.refresh(agent)

        assert agent.is_clevel is True
        assert agent.silo_id is None
        assert agent.chapter_id is None
        assert agent.weight_score == 2.0


class TestCloneWithSilosChapters:
    def test_clone_copies_silos_chapters_and_remaps(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization, OrganizationSilo, OrganizationChapter, OrganizationAgent

        # Source org
        org = Organization(id=uuid4().hex[:36], name="CloneSrcOrg", teams={}, flat_mode_agents=[], agent_final_weights={}, pipeline_params={"level1_max_rounds": 3})
        db.add(org)
        db.commit()

        silo = OrganizationSilo(id=uuid4().hex[:36], org_id=org.id, name="S1", color="#ff0000")
        chapter = OrganizationChapter(id=uuid4().hex[:36], org_id=org.id, name="C1", shared_directives=["d1"])
        db.add_all([silo, chapter])
        db.commit()

        agent = OrganizationAgent(
            id=uuid4().hex[:36], org_id=org.id, agent_id="Worker",
            display_name="Worker", silo_id=silo.id, chapter_id=chapter.id,
            is_clevel=False, weight_score=1.2,
            weights={}, trust_map={}, personality={},
            behavioral_directives=[], constraints=[], decision_focus=[],
        )
        db.add(agent)
        db.commit()

        # Clone
        new_org = Organization(
            id=uuid4().hex[:36], name="CloneDstOrg", teams={}, flat_mode_agents=[],
            agent_final_weights={}, pipeline_params=org.pipeline_params,
        )
        db.add(new_org)
        db.flush()

        silo_id_map = {}
        new_silo_id = uuid4().hex[:36]
        silo_id_map[silo.id] = new_silo_id
        new_silo = OrganizationSilo(id=new_silo_id, org_id=new_org.id, name=silo.name, color=silo.color)
        db.add(new_silo)

        chapter_id_map = {}
        new_chapter_id = uuid4().hex[:36]
        chapter_id_map[chapter.id] = new_chapter_id
        new_chapter = OrganizationChapter(
            id=new_chapter_id, org_id=new_org.id, name=chapter.name,
            shared_directives=chapter.shared_directives,
        )
        db.add(new_chapter)
        db.flush()

        new_agent = OrganizationAgent(
            id=uuid4().hex[:36], org_id=new_org.id, agent_id=agent.agent_id,
            display_name=agent.display_name,
            silo_id=silo_id_map.get(agent.silo_id),
            chapter_id=chapter_id_map.get(agent.chapter_id),
            is_clevel=agent.is_clevel, weight_score=agent.weight_score,
            weights={}, trust_map={}, personality={},
            behavioral_directives=[], constraints=[], decision_focus=[],
        )
        db.add(new_agent)
        db.commit()

        # Verify clone
        db.refresh(new_silo)
        db.refresh(new_chapter)
        db.refresh(new_agent)

        assert new_silo.org_id == new_org.id
        assert new_silo.name == "S1"
        assert new_silo.color == "#ff0000"
        assert new_silo.id != silo.id

        assert new_chapter.org_id == new_org.id
        assert new_chapter.shared_directives == ["d1"]
        assert new_chapter.id != chapter.id

        assert new_agent.silo_id == new_silo.id
        assert new_agent.chapter_id == new_chapter.id
        assert new_agent.silo_id != silo.id
        assert new_agent.chapter_id != chapter.id
        assert new_agent.weight_score == 1.2

        assert new_org.pipeline_params == {"level1_max_rounds": 3}


class TestOrganizationPipelineParams:
    def test_pipeline_params_default(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization

        org = Organization(id=uuid4().hex[:36], name="PipelineOrg", teams={}, flat_mode_agents=[], agent_final_weights={})
        db.add(org)
        db.commit()
        db.refresh(org)

        assert org.pipeline_params == {}

    def test_pipeline_params_set(self, db):
        from uuid import uuid4
        from ora_automation_api.models import Organization

        params = {"level1_max_rounds": 5, "level2_debate_rounds": 3}
        org = Organization(
            id=uuid4().hex[:36], name="PipelineOrg2", teams={}, flat_mode_agents=[],
            agent_final_weights={}, pipeline_params=params,
        )
        db.add(org)
        db.commit()
        db.refresh(org)

        assert org.pipeline_params == params
