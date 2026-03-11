"""Tests for structured debate module (Phase D).

Tests cover:
- Dataclass creation and serialization
- Role selection (LLM and fallback)
- Debate phases (advocate, challenger, mediation)
- Full debate round execution
- Integration with deliberation
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ora_rd_orchestrator.types import (
    AdvocatePhase,
    ChallengerPhase,
    DebateArgument,
    MediationPhase,
    ScoreAdjustment,
    StructuredDebateResult,
    StructuredDebateRound,
    TopicState,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_topic_state() -> TopicState:
    """Create a sample TopicState for testing."""
    return TopicState(
        topic_id="topic_1",
        topic_name="AI-driven automation",
        evidence=[
            {"source": "arxiv", "title": "Paper 1"},
            {"source": "crossref", "title": "Paper 2"},
        ],
        project_hits={"ora-automation": 5},
        keyword_hits=10,
        business_hits=3,
        novelty_hits=7,
    )


@pytest.fixture
def sample_agent_definitions() -> dict[str, dict]:
    """Sample agent definitions for testing."""
    return {
        "CEO": {
            "role": "ceo",
            "tier": 1,
            "domain": None,
            "team": "strategy",
            "objective": "Strategic alignment",
        },
        "PM": {
            "role": "pm",
            "tier": 2,
            "domain": "product",
            "team": "product",
            "objective": "Product-market fit",
        },
        "DevLead": {
            "role": "developer",
            "tier": 2,
            "domain": "engineering",
            "team": "engineering",
            "objective": "Technical feasibility",
        },
        "Researcher": {
            "role": "researcher",
            "tier": 3,
            "domain": "research",
            "team": "research",
            "objective": "Innovation potential",
        },
    }


@pytest.fixture
def sample_scores() -> dict[str, dict[str, float]]:
    """Sample scores for testing."""
    return {
        "topic_1": {
            "score_ceo": 7.5,
            "score_pm": 6.0,
            "score_devlead": 4.5,
            "score_researcher": 8.0,
        }
    }


# ---------------------------------------------------------------------------
# Dataclass Tests
# ---------------------------------------------------------------------------

class TestDebateArgument:
    def test_basic_creation(self):
        arg = DebateArgument(
            agent_id="PM",
            position="advocate",
            claim="This will increase user engagement",
            evidence=["DAU up 20% in similar features"],
            confidence=0.85,
        )
        assert arg.agent_id == "PM"
        assert arg.position == "advocate"
        assert arg.confidence == 0.85
        assert len(arg.evidence) == 1


class TestAdvocatePhase:
    def test_to_dict(self):
        phase = AdvocatePhase(
            topic_id="topic_1",
            advocates=["PM", "CEO"],
            arguments=[
                DebateArgument(
                    agent_id="PM",
                    position="advocate",
                    claim="Strong market fit",
                    evidence=["User research data"],
                    confidence=0.8,
                )
            ],
        )
        result = phase.to_dict()
        assert result["topic_id"] == "topic_1"
        assert result["advocates"] == ["PM", "CEO"]
        assert len(result["arguments"]) == 1
        assert result["arguments"][0]["claim"] == "Strong market fit"


class TestChallengerPhase:
    def test_to_dict(self):
        phase = ChallengerPhase(
            topic_id="topic_1",
            challengers=["DevLead"],
            rebuttals=[
                DebateArgument(
                    agent_id="DevLead",
                    position="challenger",
                    claim="Technical debt concerns",
                    evidence=["Legacy system limitations"],
                    confidence=0.7,
                )
            ],
        )
        result = phase.to_dict()
        assert result["challengers"] == ["DevLead"]
        assert result["rebuttals"][0]["position"] == "challenger"


class TestMediationPhase:
    def test_to_dict(self):
        phase = MediationPhase(
            topic_id="topic_1",
            mediator_id="CEO",
            proposed_score=6.5,
            score_range=(5.5, 7.5),
            resolved_points=["Market timing is good"],
            unresolved_points=["Tech stack decision"],
            synthesis="Proceed with phased approach",
            confidence=0.75,
        )
        result = phase.to_dict()
        assert result["mediator_id"] == "CEO"
        assert result["proposed_score"] == 6.5
        assert result["score_range"] == [5.5, 7.5]
        assert "Market timing" in result["resolved_points"][0]


class TestStructuredDebateRound:
    def test_to_dict_complete(self, sample_topic_state):
        advocate_phase = AdvocatePhase(
            topic_id="topic_1",
            advocates=["PM"],
            arguments=[],
        )
        challenger_phase = ChallengerPhase(
            topic_id="topic_1",
            challengers=["DevLead"],
            rebuttals=[],
        )
        mediation_phase = MediationPhase(
            topic_id="topic_1",
            mediator_id="CEO",
            proposed_score=7.0,
            confidence=0.8,
        )

        debate_round = StructuredDebateRound(
            round_num=1,
            topic_id="topic_1",
            topic_name="AI automation",
            advocate_phase=advocate_phase,
            challenger_phase=challenger_phase,
            mediation_phase=mediation_phase,
            converged=False,
        )

        result = debate_round.to_dict()
        assert result["round_num"] == 1
        assert result["converged"] is False
        assert "advocate_phase" in result
        assert "mediation_phase" in result


class TestStructuredDebateResult:
    def test_to_dict(self):
        result = StructuredDebateResult(
            topic_debates={},
            final_scores={"topic_1": 7.0},
            rounds_executed=2,
            all_converged=True,
        )
        output = result.to_dict()
        assert output["final_scores"]["topic_1"] == 7.0
        assert output["all_converged"] is True


# ---------------------------------------------------------------------------
# Role Selection Tests
# ---------------------------------------------------------------------------

class TestRoleSelection:
    def test_fallback_splits_agents_evenly(self, sample_agent_definitions):
        from ora_rd_orchestrator.structured_debate import _select_roles_fallback

        agent_ids = ["CEO", "PM", "DevLead", "Researcher"]
        advocates, challengers, mediator = _select_roles_fallback(
            agent_ids=agent_ids,
            agent_definitions=sample_agent_definitions,
        )

        assert len(advocates) >= 1
        assert len(challengers) >= 1
        # Mediator should be CEO (tier 1)
        assert mediator == "CEO"

    def test_fallback_single_agent(self, sample_agent_definitions):
        from ora_rd_orchestrator.structured_debate import _select_roles_fallback

        advocates, challengers, mediator = _select_roles_fallback(
            agent_ids=["PM"],
            agent_definitions=sample_agent_definitions,
        )

        assert advocates == ["PM"]
        assert challengers == []
        assert mediator == "PM"

    def test_llm_role_selection_with_mock(self, sample_agent_definitions, sample_scores):
        from ora_rd_orchestrator.structured_debate import _select_roles_via_llm
        from ora_rd_orchestrator.types import LLMResult

        mock_result = LLMResult(
            status="ok",
            parsed={
                "advocates": ["PM", "Researcher"],
                "challengers": ["DevLead"],
                "mediator": "CEO",
                "rationale": "Diverse perspectives",
            },
        )

        with patch("ora_rd_orchestrator.structured_debate.run_llm_command", return_value=mock_result):
            advocates, challengers, mediator = _select_roles_via_llm(
                topic_id="topic_1",
                topic_name="AI automation",
                current_scores=sample_scores,
                agent_ids=["CEO", "PM", "DevLead", "Researcher"],
                agent_definitions=sample_agent_definitions,
                round_num=1,
            )

        assert "PM" in advocates
        assert "Researcher" in advocates
        assert "DevLead" in challengers
        assert mediator == "CEO"

    def test_llm_role_selection_falls_back_on_failure(self, sample_agent_definitions, sample_scores):
        from ora_rd_orchestrator.structured_debate import _select_roles_via_llm
        from ora_rd_orchestrator.types import LLMResult

        mock_result = LLMResult(
            status="failed",
            parsed={"reason": "timeout"},
        )

        with patch("ora_rd_orchestrator.structured_debate.run_llm_command", return_value=mock_result):
            advocates, challengers, mediator = _select_roles_via_llm(
                topic_id="topic_1",
                topic_name="AI automation",
                current_scores=sample_scores,
                agent_ids=["CEO", "PM", "DevLead", "Researcher"],
                agent_definitions=sample_agent_definitions,
                round_num=1,
            )

        # Should use fallback (first half advocates, second half challengers)
        assert len(advocates) >= 1
        assert len(challengers) >= 1


# ---------------------------------------------------------------------------
# Phase Tests
# ---------------------------------------------------------------------------

class TestAdvocatePhaseExecution:
    def test_run_advocate_phase_parses_response(self, sample_topic_state, sample_agent_definitions, sample_scores):
        from ora_rd_orchestrator.structured_debate import run_advocate_phase
        from ora_rd_orchestrator.types import LLMResult

        mock_result = LLMResult(
            status="ok",
            parsed={
                "arguments": [
                    {
                        "agent_id": "PM",
                        "claim": "High market potential",
                        "evidence": ["Growing market", "User demand"],
                        "confidence": 0.85,
                    },
                    {
                        "agent_id": "Researcher",
                        "claim": "Novel approach",
                        "evidence": ["Recent research supports this"],
                        "confidence": 0.75,
                    },
                ]
            },
        )

        with patch("ora_rd_orchestrator.structured_debate.run_llm_command", return_value=mock_result):
            phase = run_advocate_phase(
                topic_id="topic_1",
                topic_name="AI automation",
                advocates=["PM", "Researcher"],
                current_scores=sample_scores,
                topic_state=sample_topic_state,
                agent_definitions=sample_agent_definitions,
            )

        assert len(phase.arguments) == 2
        assert phase.arguments[0].claim == "High market potential"
        assert phase.arguments[0].confidence == 0.85

    def test_run_advocate_phase_handles_llm_failure(self, sample_topic_state, sample_agent_definitions, sample_scores):
        from ora_rd_orchestrator.structured_debate import run_advocate_phase
        from ora_rd_orchestrator.types import LLMResult

        mock_result = LLMResult(status="failed", parsed={})

        with patch("ora_rd_orchestrator.structured_debate.run_llm_command", return_value=mock_result):
            phase = run_advocate_phase(
                topic_id="topic_1",
                topic_name="AI automation",
                advocates=["PM"],
                current_scores=sample_scores,
                topic_state=sample_topic_state,
                agent_definitions=sample_agent_definitions,
            )

        assert phase.arguments == []
        assert phase.meta["status"] == "failed"


class TestChallengerPhaseExecution:
    def test_run_challenger_phase_parses_rebuttals(self, sample_topic_state, sample_agent_definitions, sample_scores):
        from ora_rd_orchestrator.structured_debate import run_challenger_phase
        from ora_rd_orchestrator.types import LLMResult

        advocate_phase = AdvocatePhase(
            topic_id="topic_1",
            advocates=["PM"],
            arguments=[
                DebateArgument(
                    agent_id="PM",
                    position="advocate",
                    claim="High market potential",
                    evidence=["Data point"],
                    confidence=0.8,
                )
            ],
        )

        mock_result = LLMResult(
            status="ok",
            parsed={
                "rebuttals": [
                    {
                        "agent_id": "DevLead",
                        "target_claim": "High market potential",
                        "claim": "Technical complexity underestimated",
                        "evidence": ["Similar projects failed"],
                        "confidence": 0.7,
                    }
                ]
            },
        )

        with patch("ora_rd_orchestrator.structured_debate.run_llm_command", return_value=mock_result):
            phase = run_challenger_phase(
                topic_id="topic_1",
                topic_name="AI automation",
                challengers=["DevLead"],
                advocate_phase=advocate_phase,
                current_scores=sample_scores,
                topic_state=sample_topic_state,
                agent_definitions=sample_agent_definitions,
            )

        assert len(phase.rebuttals) == 1
        assert phase.rebuttals[0].claim == "Technical complexity underestimated"


class TestMediationPhaseExecution:
    def test_run_mediation_phase_parses_synthesis(self, sample_agent_definitions, sample_scores):
        from ora_rd_orchestrator.structured_debate import run_mediation_phase
        from ora_rd_orchestrator.types import LLMResult

        advocate_phase = AdvocatePhase(topic_id="topic_1", advocates=["PM"], arguments=[])
        challenger_phase = ChallengerPhase(topic_id="topic_1", challengers=["DevLead"], rebuttals=[])

        mock_result = LLMResult(
            status="ok",
            parsed={
                "proposed_score": 6.8,
                "score_range": {"min": 6.0, "max": 7.5},
                "resolved_points": ["Timeline is feasible"],
                "unresolved_points": ["Budget allocation"],
                "next_round_focus": ["Review cost estimates"],
                "synthesis": "Balanced approach recommended",
                "confidence": 0.72,
            },
        )

        with patch("ora_rd_orchestrator.structured_debate.run_llm_command", return_value=mock_result):
            phase = run_mediation_phase(
                topic_id="topic_1",
                topic_name="AI automation",
                mediator_id="CEO",
                advocate_phase=advocate_phase,
                challenger_phase=challenger_phase,
                current_scores=sample_scores,
                agent_definitions=sample_agent_definitions,
            )

        assert phase.proposed_score == 6.8
        assert phase.score_range == (6.0, 7.5)
        assert "Timeline is feasible" in phase.resolved_points
        assert phase.confidence == 0.72


# ---------------------------------------------------------------------------
# Full Round Tests
# ---------------------------------------------------------------------------

class TestStructuredDebateRoundExecution:
    def test_full_round_execution(self, sample_topic_state, sample_agent_definitions, sample_scores):
        from ora_rd_orchestrator.structured_debate import run_structured_debate_round
        from ora_rd_orchestrator.types import LLMResult

        # Mock all LLM calls
        role_result = LLMResult(
            status="ok",
            parsed={
                "advocates": ["PM", "Researcher"],
                "challengers": ["DevLead"],
                "mediator": "CEO",
            },
        )
        advocate_result = LLMResult(
            status="ok",
            parsed={
                "arguments": [
                    {"agent_id": "PM", "claim": "Good fit", "evidence": ["Data"], "confidence": 0.8}
                ]
            },
        )
        challenger_result = LLMResult(
            status="ok",
            parsed={
                "rebuttals": [
                    {"agent_id": "DevLead", "claim": "Risky", "evidence": ["Tech debt"], "confidence": 0.6}
                ]
            },
        )
        mediation_result = LLMResult(
            status="ok",
            parsed={
                "proposed_score": 7.0,
                "score_range": {"min": 6.8, "max": 7.2},  # width=0.4 <= 0.5 threshold
                "resolved_points": ["Go ahead"],
                "unresolved_points": [],
                "synthesis": "Proceed with caution",
                "confidence": 0.85,
            },
        )

        call_count = 0

        def mock_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return role_result
            elif call_count == 2:
                return advocate_result
            elif call_count == 3:
                return challenger_result
            else:
                return mediation_result

        with patch("ora_rd_orchestrator.structured_debate.run_llm_command", side_effect=mock_llm):
            result = run_structured_debate_round(
                round_num=1,
                topic_id="topic_1",
                topic_name="AI automation",
                current_scores=sample_scores,
                topic_state=sample_topic_state,
                agent_ids=["CEO", "PM", "DevLead", "Researcher"],
                agent_definitions=sample_agent_definitions,
            )

        assert result.round_num == 1
        assert result.topic_id == "topic_1"
        assert len(result.advocate_phase.arguments) == 1
        assert len(result.challenger_phase.rebuttals) == 1
        assert result.mediation_phase.proposed_score == 7.0
        # Should converge: score range <= 0.5, confidence >= 0.7, no unresolved
        assert result.converged is True


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestDeliberationIntegration:
    def test_run_structured_deliberation_returns_adjustments(self, sample_topic_state, sample_agent_definitions, sample_scores):
        from ora_rd_orchestrator.deliberation import run_structured_deliberation
        from ora_rd_orchestrator.types import LLMResult

        # Mock to return quick convergence
        mock_result = LLMResult(
            status="ok",
            parsed={
                "advocates": ["PM"],
                "challengers": ["DevLead"],
                "mediator": "CEO",
                "arguments": [],
                "rebuttals": [],
                "proposed_score": 7.0,
                "score_range": {"min": 6.8, "max": 7.2},
                "resolved_points": ["All agreed"],
                "unresolved_points": [],
                "synthesis": "Consensus reached",
                "confidence": 0.9,
            },
        )

        with patch("ora_rd_orchestrator.structured_debate.run_llm_command", return_value=mock_result):
            adjustments, metadata = run_structured_deliberation(
                topics={"topic_1": sample_topic_state},
                initial_scores=sample_scores,
                agent_ids=["CEO", "PM", "DevLead"],
                agent_definitions=sample_agent_definitions,
                max_rounds=2,
            )

        assert "topic_1" in adjustments
        assert isinstance(adjustments["topic_1"]["CEO"], ScoreAdjustment)
        assert "topic_debates" in metadata
        assert "final_scores" in metadata


class TestExtractScoreAdjustments:
    def test_extracts_from_mediation(self):
        from ora_rd_orchestrator.structured_debate import extract_score_adjustments_from_debate

        advocate_phase = AdvocatePhase(topic_id="topic_1", advocates=["PM"], arguments=[])
        challenger_phase = ChallengerPhase(topic_id="topic_1", challengers=["DevLead"], rebuttals=[])
        mediation_phase = MediationPhase(
            topic_id="topic_1",
            mediator_id="CEO",
            proposed_score=7.5,
            confidence=0.8,
        )
        debate_round = StructuredDebateRound(
            round_num=1,
            topic_id="topic_1",
            topic_name="Test",
            advocate_phase=advocate_phase,
            challenger_phase=challenger_phase,
            mediation_phase=mediation_phase,
        )

        result = StructuredDebateResult(
            topic_debates={"topic_1": [debate_round]},
            final_scores={"topic_1": 7.5},
            rounds_executed=1,
        )

        adjustments = extract_score_adjustments_from_debate(result)

        assert "topic_1" in adjustments
        assert "CEO" in adjustments["topic_1"]
        # Delta from neutral (5.0)
        assert adjustments["topic_1"]["CEO"].delta == 2.5
        assert adjustments["topic_1"]["CEO"].confidence == 0.8
