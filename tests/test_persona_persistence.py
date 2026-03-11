"""Tests for persona adjustment persistence (Phase C DB layer).

All tests use in-memory SQLite, no real DB connections.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ora_automation_api.models import Base, Organization, OrganizationAgent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    """Create in-memory SQLite session with schema."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def org_with_agents(db_session: Session) -> tuple[str, dict[str, str]]:
    """Create organization with test agents."""
    org = Organization(
        id="test-org-1",
        name="Test Organization",
    )
    db_session.add(org)

    agents = {
        "Researcher": OrganizationAgent(
            id="agent-1",
            org_id="test-org-1",
            agent_id="Researcher",
            display_name="Researcher",
            display_name_ko="연구원",
            role="researcher",
            tier=2,
            enabled=True,
            weights={"novelty": 0.3, "impact": 0.3, "feasibility": 0.2},
            behavioral_directives=["Focus on innovation", "Cite sources"],
            constraints=["No speculation"],
        ),
        "PM": OrganizationAgent(
            id="agent-2",
            org_id="test-org-1",
            agent_id="PM",
            display_name="Product Manager",
            display_name_ko="프로덕트 매니저",
            role="pm",
            tier=2,
            enabled=True,
            weights={"feasibility": 0.4, "impact": 0.4},
            behavioral_directives=["Consider user needs"],
            constraints=["Stay within budget"],
        ),
        "DevLead": OrganizationAgent(
            id="agent-3",
            org_id="test-org-1",
            agent_id="DevLead",
            display_name="Dev Lead",
            display_name_ko="개발 리드",
            role="developer",
            tier=2,
            enabled=True,
            weights={"feasibility": 0.5},
            behavioral_directives=[],
            constraints=[],
        ),
    }
    for agent in agents.values():
        db_session.add(agent)
    db_session.commit()

    return "test-org-1", {name: a.id for name, a in agents.items()}


# ---------------------------------------------------------------------------
# persist_persona_adjustments tests
# ---------------------------------------------------------------------------

class TestPersistPersonaAdjustments:
    def test_no_adjustments_returns_early(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import persist_persona_adjustments

        org_id, _ = org_with_agents
        result = persist_persona_adjustments(
            org_id=org_id,
            persona_learning_result={"adjustments": []},
            db=db_session,
        )

        assert result["status"] == "no_adjustments"
        assert result["applied"] == 0

    def test_weight_adjustment_applied(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import persist_persona_adjustments

        org_id, _ = org_with_agents
        result = persist_persona_adjustments(
            org_id=org_id,
            persona_learning_result={
                "adjustments": [
                    {
                        "agent_id": "Researcher",
                        "weight_adjustments": [
                            {"weight_name": "novelty", "delta": 0.1, "confidence": 1.0, "reason": "test"},
                        ],
                    }
                ]
            },
            db=db_session,
            decay_factor=1.0,  # No decay for test
        )

        assert result["status"] == "ok"
        assert result["applied"] == 1
        assert result["details"]["weight_changes"] == 1

        # Verify in DB
        agent = db_session.query(OrganizationAgent).filter_by(agent_id="Researcher").first()
        assert agent.weights["novelty"] == 0.4  # 0.3 + 0.1

    def test_weight_adjustment_with_confidence_and_decay(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import persist_persona_adjustments

        org_id, _ = org_with_agents
        result = persist_persona_adjustments(
            org_id=org_id,
            persona_learning_result={
                "adjustments": [
                    {
                        "agent_id": "Researcher",
                        "weight_adjustments": [
                            {"weight_name": "novelty", "delta": 0.1, "confidence": 0.5, "reason": "test"},
                        ],
                    }
                ]
            },
            db=db_session,
            decay_factor=0.9,
        )

        # 0.3 + (0.1 * 0.5 * 0.9) = 0.3 + 0.045 = 0.345
        agent = db_session.query(OrganizationAgent).filter_by(agent_id="Researcher").first()
        assert agent.weights["novelty"] == 0.345

    def test_weight_clamped_to_bounds(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import persist_persona_adjustments

        org_id, _ = org_with_agents

        # Set high initial value
        agent = db_session.query(OrganizationAgent).filter_by(agent_id="Researcher").first()
        agent.weights = {"novelty": 0.95}
        db_session.commit()

        result = persist_persona_adjustments(
            org_id=org_id,
            persona_learning_result={
                "adjustments": [
                    {
                        "agent_id": "Researcher",
                        "weight_adjustments": [
                            {"weight_name": "novelty", "delta": 0.1, "confidence": 1.0, "reason": "test"},
                        ],
                    }
                ]
            },
            db=db_session,
            decay_factor=1.0,
        )

        agent = db_session.query(OrganizationAgent).filter_by(agent_id="Researcher").first()
        assert agent.weights["novelty"] == 1.0  # Clamped to max

    def test_adds_directives(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import persist_persona_adjustments

        org_id, _ = org_with_agents
        result = persist_persona_adjustments(
            org_id=org_id,
            persona_learning_result={
                "adjustments": [
                    {
                        "agent_id": "Researcher",
                        "add_directives": ["Consider market trends", "Review competitor analysis"],
                    }
                ]
            },
            db=db_session,
        )

        assert result["details"]["directive_adds"] == 2
        agent = db_session.query(OrganizationAgent).filter_by(agent_id="Researcher").first()
        assert "Consider market trends" in agent.behavioral_directives
        assert "Review competitor analysis" in agent.behavioral_directives
        # Original directives preserved
        assert "Focus on innovation" in agent.behavioral_directives

    def test_removes_directives(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import persist_persona_adjustments

        org_id, _ = org_with_agents
        result = persist_persona_adjustments(
            org_id=org_id,
            persona_learning_result={
                "adjustments": [
                    {
                        "agent_id": "Researcher",
                        "remove_directives": ["Cite sources"],
                    }
                ]
            },
            db=db_session,
        )

        assert result["details"]["directive_removes"] == 1
        agent = db_session.query(OrganizationAgent).filter_by(agent_id="Researcher").first()
        assert "Cite sources" not in agent.behavioral_directives
        assert "Focus on innovation" in agent.behavioral_directives  # Other directive preserved

    def test_adds_constraints(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import persist_persona_adjustments

        org_id, _ = org_with_agents
        result = persist_persona_adjustments(
            org_id=org_id,
            persona_learning_result={
                "adjustments": [
                    {
                        "agent_id": "Researcher",
                        "add_constraints": ["Must verify facts"],
                    }
                ]
            },
            db=db_session,
        )

        assert result["details"]["constraint_adds"] == 1
        agent = db_session.query(OrganizationAgent).filter_by(agent_id="Researcher").first()
        assert "Must verify facts" in agent.constraints
        assert "No speculation" in agent.constraints  # Original preserved

    def test_removes_constraints(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import persist_persona_adjustments

        org_id, _ = org_with_agents
        result = persist_persona_adjustments(
            org_id=org_id,
            persona_learning_result={
                "adjustments": [
                    {
                        "agent_id": "Researcher",
                        "remove_constraints": ["No speculation"],
                    }
                ]
            },
            db=db_session,
        )

        assert result["details"]["constraint_removes"] == 1
        agent = db_session.query(OrganizationAgent).filter_by(agent_id="Researcher").first()
        assert "No speculation" not in agent.constraints

    def test_avoids_duplicate_directives(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import persist_persona_adjustments

        org_id, _ = org_with_agents
        result = persist_persona_adjustments(
            org_id=org_id,
            persona_learning_result={
                "adjustments": [
                    {
                        "agent_id": "Researcher",
                        "add_directives": ["Focus on innovation"],  # Already exists
                    }
                ]
            },
            db=db_session,
        )

        # Should not add duplicate
        assert result["details"]["directive_adds"] == 0
        agent = db_session.query(OrganizationAgent).filter_by(agent_id="Researcher").first()
        assert agent.behavioral_directives.count("Focus on innovation") == 1

    def test_skips_unknown_agents(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import persist_persona_adjustments

        org_id, _ = org_with_agents
        result = persist_persona_adjustments(
            org_id=org_id,
            persona_learning_result={
                "adjustments": [
                    {
                        "agent_id": "UnknownAgent",
                        "weight_adjustments": [
                            {"weight_name": "novelty", "delta": 0.1, "confidence": 1.0, "reason": "test"},
                        ],
                    }
                ]
            },
            db=db_session,
        )

        assert result["status"] == "ok"
        assert result["applied"] == 0

    def test_multiple_agents_updated(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import persist_persona_adjustments

        org_id, _ = org_with_agents
        result = persist_persona_adjustments(
            org_id=org_id,
            persona_learning_result={
                "adjustments": [
                    {
                        "agent_id": "Researcher",
                        "add_directives": ["New directive 1"],
                    },
                    {
                        "agent_id": "PM",
                        "add_directives": ["New directive 2"],
                    },
                    {
                        "agent_id": "DevLead",
                        "add_directives": ["New directive 3"],
                    },
                ]
            },
            db=db_session,
        )

        assert result["applied"] == 3
        assert result["details"]["directive_adds"] == 3

    def test_combined_adjustments(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import persist_persona_adjustments

        org_id, _ = org_with_agents
        result = persist_persona_adjustments(
            org_id=org_id,
            persona_learning_result={
                "adjustments": [
                    {
                        "agent_id": "Researcher",
                        "weight_adjustments": [
                            {"weight_name": "novelty", "delta": 0.05, "confidence": 1.0, "reason": "test"},
                        ],
                        "add_directives": ["New directive"],
                        "remove_directives": ["Cite sources"],
                        "add_constraints": ["New constraint"],
                    }
                ]
            },
            db=db_session,
            decay_factor=1.0,
        )

        assert result["applied"] == 1
        assert result["details"]["weight_changes"] == 1
        assert result["details"]["directive_adds"] == 1
        assert result["details"]["directive_removes"] == 1
        assert result["details"]["constraint_adds"] == 1


# ---------------------------------------------------------------------------
# get_org_agent_personas tests
# ---------------------------------------------------------------------------

class TestGetOrgAgentPersonas:
    def test_returns_all_enabled_agents(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import get_org_agent_personas

        org_id, _ = org_with_agents
        personas = get_org_agent_personas(org_id, db=db_session)

        assert len(personas) == 3
        assert "Researcher" in personas
        assert "PM" in personas
        assert "DevLead" in personas

    def test_returns_correct_data_structure(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import get_org_agent_personas

        org_id, _ = org_with_agents
        personas = get_org_agent_personas(org_id, db=db_session)

        researcher = personas["Researcher"]
        assert "weights" in researcher
        assert "behavioral_directives" in researcher
        assert "constraints" in researcher
        assert "trust_map" in researcher
        assert "tier" in researcher
        assert "role" in researcher

        assert researcher["weights"]["novelty"] == 0.3
        assert "Focus on innovation" in researcher["behavioral_directives"]

    def test_excludes_disabled_agents(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import get_org_agent_personas

        org_id, _ = org_with_agents

        # Disable one agent
        agent = db_session.query(OrganizationAgent).filter_by(agent_id="DevLead").first()
        agent.enabled = False
        db_session.commit()

        personas = get_org_agent_personas(org_id, db=db_session)

        assert len(personas) == 2
        assert "DevLead" not in personas

    def test_returns_empty_for_unknown_org(self, db_session: Session):
        from ora_automation_api.service import get_org_agent_personas

        personas = get_org_agent_personas("nonexistent-org", db=db_session)
        assert personas == {}

    def test_handles_empty_weights_and_directives(self, db_session: Session, org_with_agents):
        from ora_automation_api.service import get_org_agent_personas

        org_id, _ = org_with_agents
        personas = get_org_agent_personas(org_id, db=db_session)

        devlead = personas["DevLead"]
        assert devlead["behavioral_directives"] == []
        assert devlead["constraints"] == []
