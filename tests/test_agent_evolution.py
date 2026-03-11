"""Tests for agent evolution module (Phase E) - Toss Style.

Tests cover:
- Dataclass creation and serialization
- Signal collection from orchestration
- Evolution proposal generation
- Auto-apply vs flagged changes
- Rollback capability
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from ora_rd_orchestrator.types import (
    AgentPersona,
    AgentSnapshot,
    ChapterDeliberationResult,
    ConvergencePipelineState,
    EvolutionProposal,
    EvolutionResult,
    EvolutionSignal,
    OrchestrationDecision,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_convergence_state() -> ConvergencePipelineState:
    """Create a sample convergence state for testing."""
    return ConvergencePipelineState(
        level1_results=[
            ChapterDeliberationResult(
                chapter_id="ch_product",
                chapter_name="Product",
                agent_ids=["PM", "Designer"],
                topic_scores={
                    "topic_1": {"score_pm": 7.5, "score_designer": 6.0},
                },
                rounds_executed=2,
                converged=True,
            ),
            ChapterDeliberationResult(
                chapter_id="ch_engineering",
                chapter_name="Engineering",
                agent_ids=["DevLead", "QA"],
                topic_scores={
                    "topic_1": {"score_devlead": 5.0, "score_qa": 4.5},
                },
                rounds_executed=3,
                converged=False,
            ),
        ],
        final_scores={
            "topic_1": {"score_pm": 7.0, "score_designer": 6.5, "score_devlead": 5.5, "score_qa": 5.0},
        },
        decisions=[
            OrchestrationDecision(
                decision_id="d1",
                owner="PM",
                rationale="Strong market fit",
                risk="low",
                next_action="Proceed",
                due="2024-12-31",
                topic_id="topic_1",
                topic_name="AI Automation",
                service=["b2b"],
                score_delta=0.5,
                confidence=0.8,
                fail_label="SKIP",
            ),
            OrchestrationDecision(
                decision_id="d2",
                owner="PM",
                rationale="User research supports",
                risk="low",
                next_action="Continue",
                due="2024-12-31",
                topic_id="topic_1",
                topic_name="AI Automation",
                service=["b2b"],
                score_delta=0.3,
                confidence=0.7,
                fail_label="SKIP",
            ),
        ],
        execution_log=[
            {"type": "chapter", "chapter_id": "ch_product", "rounds": 2, "converged": True},
            {"type": "chapter", "chapter_id": "ch_engineering", "rounds": 3, "converged": False},
        ],
    )


@pytest.fixture
def sample_agent_definitions() -> dict[str, dict]:
    """Sample agent definitions."""
    return {
        "PM": {"role": "pm", "tier": 2, "team": "product", "weights": {"impact": 0.3}},
        "Designer": {"role": "designer", "tier": 3, "team": "product", "weights": {}},
        "DevLead": {"role": "developer", "tier": 2, "team": "engineering", "weights": {}},
        "QA": {"role": "qa", "tier": 3, "team": "engineering", "weights": {}},
    }


@pytest.fixture
def sample_personas() -> dict[str, AgentPersona]:
    """Sample agent personas."""
    return {
        "PM": AgentPersona(
            agent_id="PM",
            display_name="Product Manager",
            display_name_ko="프로덕트 매니저",
            role="pm",
            tier=2,
            domain="product",
            team="product",
            system_prompt="You are a PM...",
            weights={"impact": 0.3, "feasibility": 0.2},
            behavioral_directives=["Focus on user needs"],
            trust_map={"DevLead": 0.7},
        ),
        "DevLead": AgentPersona(
            agent_id="DevLead",
            display_name="Dev Lead",
            display_name_ko="개발 리드",
            role="developer",
            tier=2,
            domain="engineering",
            team="engineering",
            system_prompt="You are a dev lead...",
            weights={"feasibility": 0.4},
        ),
    }


# ---------------------------------------------------------------------------
# Dataclass Tests
# ---------------------------------------------------------------------------

class TestEvolutionSignal:
    def test_basic_creation(self):
        signal = EvolutionSignal(
            agent_id="PM",
            signal_type="score_accuracy",
            measured_value=0.5,
            baseline_value=0.3,
            delta=0.2,
            confidence=0.8,
        )
        assert signal.agent_id == "PM"
        assert signal.delta == 0.2

    def test_to_dict(self):
        signal = EvolutionSignal(
            agent_id="PM",
            signal_type="consensus_contribution",
            measured_value=3,
            baseline_value=2,
            delta=1,
            confidence=0.6,
            context={"total_decisions": 5},
        )
        result = signal.to_dict()
        assert result["signal_type"] == "consensus_contribution"
        assert result["context"]["total_decisions"] == 5


class TestEvolutionProposal:
    def test_basic_creation(self):
        proposal = EvolutionProposal(
            agent_id="PM",
            proposal_type="weight_adjust",
            change_magnitude="small",
            auto_apply=True,
            details={"weight_adjustments": [{"weight_name": "impact", "delta": 0.05}]},
            rationale="PM consistently overestimates impact",
            confidence=0.7,
        )
        assert proposal.auto_apply is True
        assert proposal.change_magnitude == "small"

    def test_to_dict(self):
        proposal = EvolutionProposal(
            agent_id="DevLead",
            proposal_type="directive_add",
            change_magnitude="micro",
            auto_apply=True,
            details={"add_directives": ["Consider scalability"]},
        )
        result = proposal.to_dict()
        assert "add_directives" in result["details"]


class TestAgentSnapshot:
    def test_to_dict(self):
        snapshot = AgentSnapshot(
            agent_id="PM",
            version=1,
            weights={"impact": 0.3},
            behavioral_directives=["Focus on users"],
            created_at="2024-01-01T00:00:00",
            reason="Pre-evolution",
        )
        result = snapshot.to_dict()
        assert result["version"] == 1
        assert result["weights"]["impact"] == 0.3


class TestEvolutionResult:
    def test_to_dict(self):
        result = EvolutionResult(
            signals_collected=[
                EvolutionSignal("PM", "score_accuracy", 0.5, 0.3, 0.2, 0.8),
            ],
            proposals=[
                EvolutionProposal("PM", "weight_adjust", "micro", True, {}, "test", 0.7),
            ],
            auto_applied=["PM"],
            flagged_for_review=[],
        )
        output = result.to_dict()
        assert len(output["signals_collected"]) == 1
        assert output["auto_applied"] == ["PM"]


# ---------------------------------------------------------------------------
# Signal Collection Tests
# ---------------------------------------------------------------------------

class TestComputeEvolutionSignals:
    def test_collects_score_accuracy_signals(self, sample_convergence_state, sample_agent_definitions, sample_personas):
        from ora_rd_orchestrator.agent_evolution import compute_evolution_signals

        signals = compute_evolution_signals(
            convergence_state=sample_convergence_state,
            agent_definitions=sample_agent_definitions,
            personas=sample_personas,
        )

        # Should have signals for each agent
        score_signals = [s for s in signals if s.signal_type == "score_accuracy"]
        assert len(score_signals) > 0

    def test_collects_consensus_contribution_signals(self, sample_convergence_state, sample_agent_definitions, sample_personas):
        from ora_rd_orchestrator.agent_evolution import compute_evolution_signals

        signals = compute_evolution_signals(
            convergence_state=sample_convergence_state,
            agent_definitions=sample_agent_definitions,
            personas=sample_personas,
        )

        contrib_signals = [s for s in signals if s.signal_type == "consensus_contribution"]
        # Should have one per agent
        assert len(contrib_signals) == len(sample_agent_definitions)

        # PM has 2 decisions, others have 0
        pm_signal = next(s for s in contrib_signals if s.agent_id == "PM")
        assert pm_signal.measured_value == 2

    def test_collects_convergence_speed_signals(self, sample_convergence_state, sample_agent_definitions, sample_personas):
        from ora_rd_orchestrator.agent_evolution import compute_evolution_signals

        signals = compute_evolution_signals(
            convergence_state=sample_convergence_state,
            agent_definitions=sample_agent_definitions,
            personas=sample_personas,
        )

        speed_signals = [s for s in signals if s.signal_type == "convergence_speed"]
        assert len(speed_signals) > 0


# ---------------------------------------------------------------------------
# Magnitude Classification Tests
# ---------------------------------------------------------------------------

class TestMagnitudeClassification:
    def test_micro_magnitude_auto_applies(self):
        from ora_rd_orchestrator.agent_evolution import _classify_magnitude

        magnitude, auto_apply = _classify_magnitude(0.03)
        assert magnitude == "micro"
        assert auto_apply is True

    def test_small_magnitude_auto_applies(self):
        from ora_rd_orchestrator.agent_evolution import _classify_magnitude

        magnitude, auto_apply = _classify_magnitude(0.10)
        assert magnitude == "small"
        assert auto_apply is True

    def test_large_magnitude_flags_for_review(self):
        from ora_rd_orchestrator.agent_evolution import _classify_magnitude

        magnitude, auto_apply = _classify_magnitude(0.20)
        assert magnitude == "large"
        assert auto_apply is False

    def test_negative_delta_same_classification(self):
        from ora_rd_orchestrator.agent_evolution import _classify_magnitude

        magnitude, auto_apply = _classify_magnitude(-0.08)
        assert magnitude == "small"
        assert auto_apply is True


# ---------------------------------------------------------------------------
# Evolution Analysis Tests
# ---------------------------------------------------------------------------

class TestAnalyzeAgentEvolution:
    def test_generates_proposals_from_signals(self, sample_agent_definitions, sample_personas):
        from ora_rd_orchestrator.agent_evolution import analyze_agent_evolution
        from ora_rd_orchestrator.types import LLMResult

        signals = [
            EvolutionSignal("PM", "score_accuracy", 1.5, 0.5, 1.0, 0.8),
        ]

        mock_result = LLMResult(
            status="ok",
            parsed={
                "proposals": [
                    {
                        "agent_id": "PM",
                        "proposal_type": "weight_adjust",
                        "changes": {
                            "weight_adjustments": [{"weight_name": "impact", "delta": -0.03}],
                        },
                        "rationale": "PM tends to overestimate",
                        "confidence": 0.75,
                        "signals_used": ["score_accuracy"],
                    }
                ]
            },
        )

        with patch("ora_rd_orchestrator.agent_evolution.run_llm_command", return_value=mock_result):
            proposals = analyze_agent_evolution(
                signals=signals,
                agent_definitions=sample_agent_definitions,
                personas=sample_personas,
            )

        assert len(proposals) == 1
        assert proposals[0].agent_id == "PM"
        assert proposals[0].proposal_type == "weight_adjust"
        # Micro change (<0.05) should auto-apply
        assert proposals[0].change_magnitude == "micro"
        assert proposals[0].auto_apply is True

    def test_handles_llm_failure(self, sample_agent_definitions, sample_personas):
        from ora_rd_orchestrator.agent_evolution import analyze_agent_evolution
        from ora_rd_orchestrator.types import LLMResult

        signals = [EvolutionSignal("PM", "score_accuracy", 0.5, 0.3, 0.2, 0.8)]
        mock_result = LLMResult(status="failed", parsed={})

        with patch("ora_rd_orchestrator.agent_evolution.run_llm_command", return_value=mock_result):
            proposals = analyze_agent_evolution(
                signals=signals,
                agent_definitions=sample_agent_definitions,
                personas=sample_personas,
            )

        assert proposals == []

    def test_filters_invalid_agents(self, sample_agent_definitions, sample_personas):
        from ora_rd_orchestrator.agent_evolution import analyze_agent_evolution
        from ora_rd_orchestrator.types import LLMResult

        mock_result = LLMResult(
            status="ok",
            parsed={
                "proposals": [
                    {"agent_id": "UnknownAgent", "proposal_type": "weight_adjust", "changes": {}},
                ]
            },
        )

        with patch("ora_rd_orchestrator.agent_evolution.run_llm_command", return_value=mock_result):
            proposals = analyze_agent_evolution(
                signals=[],
                agent_definitions=sample_agent_definitions,
                personas=sample_personas,
            )

        assert len(proposals) == 0


# ---------------------------------------------------------------------------
# Apply Evolution Tests
# ---------------------------------------------------------------------------

class TestApplyEvolutionProposal:
    def test_applies_weight_adjustment(self, sample_personas):
        from ora_rd_orchestrator.agent_evolution import apply_evolution_proposal

        proposal = EvolutionProposal(
            agent_id="PM",
            proposal_type="weight_adjust",
            change_magnitude="small",
            auto_apply=True,
            details={
                "weight_adjustments": [{"weight_name": "impact", "delta": 0.1}],
            },
        )

        persona = sample_personas["PM"]
        original_impact = persona.weights.get("impact", 0)

        updated, changes = apply_evolution_proposal(proposal, persona)

        assert updated.weights["impact"] == original_impact + 0.1
        assert len(changes["changes"]) == 1

    def test_applies_directive_addition(self, sample_personas):
        from ora_rd_orchestrator.agent_evolution import apply_evolution_proposal

        proposal = EvolutionProposal(
            agent_id="PM",
            proposal_type="directive_add",
            change_magnitude="small",
            auto_apply=True,
            details={
                "add_directives": ["Consider competitive analysis"],
            },
        )

        persona = sample_personas["PM"]
        updated, changes = apply_evolution_proposal(proposal, persona)

        assert "Consider competitive analysis" in updated.behavioral_directives
        assert any(c["type"] == "directive_add" for c in changes["changes"])

    def test_applies_trust_adjustment(self):
        from ora_rd_orchestrator.agent_evolution import apply_evolution_proposal
        import copy

        # Create fresh persona for this test
        persona = AgentPersona(
            agent_id="PM",
            display_name="PM",
            display_name_ko="PM",
            role="pm",
            tier=2,
            domain="product",
            team="product",
            system_prompt="...",
            trust_map={"DevLead": 0.6},
        )

        proposal = EvolutionProposal(
            agent_id="PM",
            proposal_type="trust_adjust",
            change_magnitude="small",
            auto_apply=True,
            details={
                "trust_adjustments": [{"target_agent": "DevLead", "delta": 0.1}],
            },
        )

        updated, changes = apply_evolution_proposal(proposal, persona)

        assert updated.trust_map["DevLead"] == 0.7  # 0.6 + 0.1

    def test_clamps_weights_to_bounds(self, sample_personas):
        from ora_rd_orchestrator.agent_evolution import apply_evolution_proposal

        # Set weight near max
        sample_personas["PM"].weights["impact"] = 0.95

        proposal = EvolutionProposal(
            agent_id="PM",
            proposal_type="weight_adjust",
            change_magnitude="small",
            auto_apply=True,
            details={
                "weight_adjustments": [{"weight_name": "impact", "delta": 0.2}],
            },
        )

        updated, _ = apply_evolution_proposal(proposal, sample_personas["PM"])

        assert updated.weights["impact"] == 1.0  # Clamped to max


# ---------------------------------------------------------------------------
# Snapshot and Rollback Tests
# ---------------------------------------------------------------------------

class TestSnapshotAndRollback:
    def test_creates_snapshot(self, sample_personas):
        from ora_rd_orchestrator.agent_evolution import create_agent_snapshot

        persona = sample_personas["PM"]
        snapshot = create_agent_snapshot(
            agent_id="PM",
            persona=persona,
            reason="Pre-evolution test",
            version=1,
        )

        assert snapshot.agent_id == "PM"
        assert snapshot.weights == persona.weights
        assert snapshot.behavioral_directives == persona.behavioral_directives
        assert snapshot.reason == "Pre-evolution test"

    def test_rollback_restores_state(self, sample_personas):
        from ora_rd_orchestrator.agent_evolution import create_agent_snapshot, rollback_agent

        persona = sample_personas["PM"]
        original_weights = dict(persona.weights)

        # Create snapshot
        snapshot = create_agent_snapshot("PM", persona, "backup", 1)

        # Modify persona
        persona.weights["impact"] = 0.99
        persona.behavioral_directives.append("New directive")

        # Rollback
        rolled_back = rollback_agent("PM", snapshot, persona)

        assert rolled_back.weights == original_weights
        assert "New directive" not in rolled_back.behavioral_directives


# ---------------------------------------------------------------------------
# Full Evolution Cycle Tests
# ---------------------------------------------------------------------------

class TestRunEvolutionCycle:
    def test_full_cycle_auto_applies_small_changes(
        self, sample_convergence_state, sample_agent_definitions, sample_personas
    ):
        from ora_rd_orchestrator.agent_evolution import run_evolution_cycle
        from ora_rd_orchestrator.types import LLMResult

        mock_result = LLMResult(
            status="ok",
            parsed={
                "proposals": [
                    {
                        "agent_id": "PM",
                        "proposal_type": "weight_adjust",
                        "changes": {"weight_adjustments": [{"weight_name": "impact", "delta": 0.03}]},
                        "rationale": "Minor adjustment",
                        "confidence": 0.8,
                    }
                ]
            },
        )

        with patch("ora_rd_orchestrator.agent_evolution.run_llm_command", return_value=mock_result):
            result, updated_personas = run_evolution_cycle(
                convergence_state=sample_convergence_state,
                agent_definitions=sample_agent_definitions,
                personas=sample_personas,
            )

        assert "PM" in result.auto_applied
        assert len(result.flagged_for_review) == 0
        assert len(result.signals_collected) > 0

    def test_full_cycle_flags_large_changes(
        self, sample_convergence_state, sample_agent_definitions, sample_personas
    ):
        from ora_rd_orchestrator.agent_evolution import run_evolution_cycle
        from ora_rd_orchestrator.types import LLMResult

        mock_result = LLMResult(
            status="ok",
            parsed={
                "proposals": [
                    {
                        "agent_id": "PM",
                        "proposal_type": "weight_adjust",
                        "changes": {"weight_adjustments": [{"weight_name": "impact", "delta": 0.25}]},
                        "rationale": "Major rebalancing needed",
                        "confidence": 0.9,
                    }
                ]
            },
        )

        with patch("ora_rd_orchestrator.agent_evolution.run_llm_command", return_value=mock_result):
            result, _ = run_evolution_cycle(
                convergence_state=sample_convergence_state,
                agent_definitions=sample_agent_definitions,
                personas=sample_personas,
            )

        assert "PM" in result.flagged_for_review
        assert "PM" not in result.auto_applied
