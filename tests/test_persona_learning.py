"""Tests for dynamic persona learning.

All LLM calls are mocked — no real LLM invocations.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from ora_rd_orchestrator.types import (
    OrchestrationDecision,
    PersonaAdjustment,
    PersonaLearningResult,
    WeightAdjustment,
)


# ---------------------------------------------------------------------------
# WeightAdjustment tests
# ---------------------------------------------------------------------------

class TestWeightAdjustment:
    def test_basic_creation(self):
        wa = WeightAdjustment(
            weight_name="impact",
            delta=0.05,
            confidence=0.8,
            reason="Agent showed strong impact analysis",
        )
        assert wa.weight_name == "impact"
        assert wa.delta == 0.05
        assert wa.confidence == 0.8

    def test_to_dict(self):
        wa = WeightAdjustment(
            weight_name="feasibility",
            delta=-0.03,
            confidence=0.6,
            reason="Too optimistic on feasibility",
        )
        d = wa.to_dict()
        assert d["weight_name"] == "feasibility"
        assert d["delta"] == -0.03
        assert d["confidence"] == 0.6


# ---------------------------------------------------------------------------
# PersonaAdjustment tests
# ---------------------------------------------------------------------------

class TestPersonaAdjustment:
    def test_basic_creation(self):
        adj = PersonaAdjustment(
            agent_id="Researcher",
            weight_adjustments=[
                WeightAdjustment("novelty", 0.05, 0.9, "good novelty focus"),
            ],
            add_directives=["Consider market trends"],
            overall_assessment="Solid performance",
            confidence=0.85,
        )
        assert adj.agent_id == "Researcher"
        assert len(adj.weight_adjustments) == 1
        assert len(adj.add_directives) == 1
        assert adj.confidence == 0.85

    def test_to_dict(self):
        adj = PersonaAdjustment(
            agent_id="PM",
            weight_adjustments=[],
            add_directives=["Focus on user needs"],
            remove_directives=["Old directive"],
            add_constraints=["Must consider budget"],
            remove_constraints=[],
            overall_assessment="Needs improvement",
            confidence=0.7,
        )
        d = adj.to_dict()
        assert d["agent_id"] == "PM"
        assert d["add_directives"] == ["Focus on user needs"]
        assert d["remove_directives"] == ["Old directive"]
        assert d["confidence"] == 0.7


# ---------------------------------------------------------------------------
# PersonaLearningResult tests
# ---------------------------------------------------------------------------

class TestPersonaLearningResult:
    def test_empty_result(self):
        result = PersonaLearningResult()
        assert result.adjustments == []
        assert result.meta == {}

    def test_to_dict(self):
        result = PersonaLearningResult(
            adjustments=[
                PersonaAdjustment("A", [], [], [], [], [], "good", 0.8),
            ],
            meta={"status": "ok"},
        )
        d = result.to_dict()
        assert len(d["adjustments"]) == 1
        assert d["meta"]["status"] == "ok"

    def test_apply_to_weights_basic(self):
        result = PersonaLearningResult(
            adjustments=[
                PersonaAdjustment(
                    agent_id="A",
                    weight_adjustments=[
                        WeightAdjustment("impact", 0.1, 1.0, "test"),
                    ],
                ),
            ]
        )
        weights = {"A": {"impact": 0.3}}
        updated = result.apply_to_weights(weights, decay_factor=1.0)

        # 0.3 + (0.1 * 1.0 * 1.0) = 0.4
        assert updated["A"]["impact"] == 0.4

    def test_apply_to_weights_with_confidence(self):
        result = PersonaLearningResult(
            adjustments=[
                PersonaAdjustment(
                    agent_id="A",
                    weight_adjustments=[
                        WeightAdjustment("impact", 0.1, 0.5, "test"),
                    ],
                ),
            ]
        )
        weights = {"A": {"impact": 0.3}}
        updated = result.apply_to_weights(weights, decay_factor=1.0)

        # 0.3 + (0.1 * 0.5 * 1.0) = 0.35
        assert updated["A"]["impact"] == 0.35

    def test_apply_to_weights_clamps_to_bounds(self):
        result = PersonaLearningResult(
            adjustments=[
                PersonaAdjustment(
                    agent_id="A",
                    weight_adjustments=[
                        WeightAdjustment("impact", 0.1, 1.0, "test"),
                    ],
                ),
            ]
        )
        weights = {"A": {"impact": 0.95}}
        updated = result.apply_to_weights(weights, max_weight=1.0, decay_factor=1.0)

        # 0.95 + 0.1 = 1.05 → clamped to 1.0
        assert updated["A"]["impact"] == 1.0

    def test_apply_to_weights_creates_new_agent(self):
        result = PersonaLearningResult(
            adjustments=[
                PersonaAdjustment(
                    agent_id="NewAgent",
                    weight_adjustments=[
                        WeightAdjustment("impact", 0.1, 1.0, "test"),
                    ],
                ),
            ]
        )
        weights = {}
        updated = result.apply_to_weights(weights, decay_factor=1.0)

        # Default weight 0.2 + 0.1 = 0.3
        assert updated["NewAgent"]["impact"] == 0.3


# ---------------------------------------------------------------------------
# compute_persona_adjustments tests (with mocked LLM)
# ---------------------------------------------------------------------------

class TestComputePersonaAdjustments:
    def _mock_llm_result(self, adjustments: list[dict], summary: str = ""):
        from ora_rd_orchestrator.types import LLMResult
        return LLMResult(
            status="ok",
            parsed={
                "persona_adjustments": adjustments,
                "summary": summary,
            },
        )

    @patch("ora_rd_orchestrator.persona_learning.run_llm_command")
    def test_basic_adjustment(self, mock_llm):
        from ora_rd_orchestrator.persona_learning import compute_persona_adjustments

        mock_llm.return_value = self._mock_llm_result([
            {
                "agent_id": "Researcher",
                "weight_adjustments": [
                    {
                        "weight_name": "novelty",
                        "delta": 0.05,
                        "confidence": 0.9,
                        "reason": "Good novelty focus",
                    }
                ],
                "add_directives": ["Consider market size"],
                "remove_directives": [],
                "add_constraints": [],
                "remove_constraints": [],
                "overall_assessment": "Strong performance",
                "confidence": 0.85,
            }
        ])

        result = compute_persona_adjustments(
            deliberation_history=[],
            final_scores={"t1": {"score_researcher": 5.0}},
            decisions=[],
            agent_definitions={"Researcher": {"role": "researcher"}},
            current_weights={"Researcher": {"novelty": 0.3}},
            current_directives={"Researcher": []},
            current_constraints={"Researcher": []},
        )

        assert len(result.adjustments) == 1
        adj = result.adjustments[0]
        assert adj.agent_id == "Researcher"
        assert len(adj.weight_adjustments) == 1
        assert adj.weight_adjustments[0].weight_name == "novelty"
        assert adj.weight_adjustments[0].delta == 0.05
        assert adj.add_directives == ["Consider market size"]

    @patch("ora_rd_orchestrator.persona_learning.run_llm_command")
    def test_filters_invalid_agents(self, mock_llm):
        from ora_rd_orchestrator.persona_learning import compute_persona_adjustments

        mock_llm.return_value = self._mock_llm_result([
            {
                "agent_id": "UnknownAgent",
                "weight_adjustments": [],
                "overall_assessment": "Should be filtered",
                "confidence": 0.8,
            }
        ])

        result = compute_persona_adjustments(
            deliberation_history=[],
            final_scores={},
            decisions=[],
            agent_definitions={"Researcher": {"role": "researcher"}},
            current_weights={},
            current_directives={},
            current_constraints={},
        )

        assert len(result.adjustments) == 0

    @patch("ora_rd_orchestrator.persona_learning.run_llm_command")
    def test_clamps_delta_values(self, mock_llm):
        from ora_rd_orchestrator.persona_learning import compute_persona_adjustments

        mock_llm.return_value = self._mock_llm_result([
            {
                "agent_id": "A",
                "weight_adjustments": [
                    {"weight_name": "impact", "delta": 0.5, "confidence": 1.0, "reason": "too high"},
                    {"weight_name": "risk", "delta": -0.5, "confidence": 1.0, "reason": "too low"},
                ],
                "overall_assessment": "test",
                "confidence": 0.8,
            }
        ])

        result = compute_persona_adjustments(
            deliberation_history=[],
            final_scores={},
            decisions=[],
            agent_definitions={"A": {"role": "a"}},
            current_weights={},
            current_directives={},
            current_constraints={},
        )

        assert len(result.adjustments) == 1
        wa = result.adjustments[0].weight_adjustments
        assert wa[0].delta == 0.1  # Clamped to max
        assert wa[1].delta == -0.1  # Clamped to min

    @patch("ora_rd_orchestrator.persona_learning.run_llm_command")
    def test_deduplicates_agents(self, mock_llm):
        from ora_rd_orchestrator.persona_learning import compute_persona_adjustments

        mock_llm.return_value = self._mock_llm_result([
            {"agent_id": "A", "weight_adjustments": [], "overall_assessment": "first", "confidence": 0.9},
            {"agent_id": "A", "weight_adjustments": [], "overall_assessment": "duplicate", "confidence": 0.8},
        ])

        result = compute_persona_adjustments(
            deliberation_history=[],
            final_scores={},
            decisions=[],
            agent_definitions={"A": {"role": "a"}},
            current_weights={},
            current_directives={},
            current_constraints={},
        )

        assert len(result.adjustments) == 1
        assert result.adjustments[0].overall_assessment == "first"

    @patch("ora_rd_orchestrator.persona_learning.run_llm_command")
    def test_handles_llm_failure(self, mock_llm):
        from ora_rd_orchestrator.persona_learning import compute_persona_adjustments
        from ora_rd_orchestrator.types import LLMResult

        mock_llm.return_value = LLMResult(
            status="failed",
            parsed={"reason": "timeout"},
        )

        result = compute_persona_adjustments(
            deliberation_history=[],
            final_scores={},
            decisions=[],
            agent_definitions={"A": {}},
            current_weights={},
            current_directives={},
            current_constraints={},
        )

        assert len(result.adjustments) == 0
        assert result.meta["status"] == "failed"


# ---------------------------------------------------------------------------
# merge_persona_adjustments tests
# ---------------------------------------------------------------------------

class TestMergePersonaAdjustments:
    def test_does_not_modify_originals(self):
        from ora_rd_orchestrator.persona_learning import merge_persona_adjustments

        base_weights = {"A": {"impact": 0.3}}
        base_directives = {"A": ["original"]}
        base_constraints = {"A": ["const1"]}

        result = PersonaLearningResult(
            adjustments=[
                PersonaAdjustment(
                    agent_id="A",
                    weight_adjustments=[WeightAdjustment("impact", 0.1, 1.0, "test")],
                    add_directives=["new directive"],
                ),
            ]
        )

        new_weights, new_dirs, new_cons = merge_persona_adjustments(
            base_weights, base_directives, base_constraints, result, decay_factor=1.0
        )

        # Originals unchanged
        assert base_weights["A"]["impact"] == 0.3
        assert base_directives["A"] == ["original"]

        # New values updated
        assert new_weights["A"]["impact"] == 0.4
        assert "new directive" in new_dirs["A"]
        assert "original" in new_dirs["A"]

    def test_removes_directives(self):
        from ora_rd_orchestrator.persona_learning import merge_persona_adjustments

        base_directives = {"A": ["keep this", "remove this"]}

        result = PersonaLearningResult(
            adjustments=[
                PersonaAdjustment(
                    agent_id="A",
                    remove_directives=["remove this"],
                ),
            ]
        )

        _, new_dirs, _ = merge_persona_adjustments(
            {}, base_directives, {}, result
        )

        assert new_dirs["A"] == ["keep this"]

    def test_adds_constraints(self):
        from ora_rd_orchestrator.persona_learning import merge_persona_adjustments

        base_constraints = {"A": ["existing"]}

        result = PersonaLearningResult(
            adjustments=[
                PersonaAdjustment(
                    agent_id="A",
                    add_constraints=["new constraint"],
                ),
            ]
        )

        _, _, new_cons = merge_persona_adjustments(
            {}, {}, base_constraints, result
        )

        assert "existing" in new_cons["A"]
        assert "new constraint" in new_cons["A"]

    def test_avoids_duplicate_directives(self):
        from ora_rd_orchestrator.persona_learning import merge_persona_adjustments

        base_directives = {"A": ["already exists"]}

        result = PersonaLearningResult(
            adjustments=[
                PersonaAdjustment(
                    agent_id="A",
                    add_directives=["already exists", "new one"],
                ),
            ]
        )

        _, new_dirs, _ = merge_persona_adjustments(
            {}, base_directives, {}, result
        )

        # Should not duplicate
        assert new_dirs["A"].count("already exists") == 1
        assert "new one" in new_dirs["A"]

    def test_creates_new_agent_entries(self):
        from ora_rd_orchestrator.persona_learning import merge_persona_adjustments

        result = PersonaLearningResult(
            adjustments=[
                PersonaAdjustment(
                    agent_id="NewAgent",
                    add_directives=["first directive"],
                    add_constraints=["first constraint"],
                ),
            ]
        )

        _, new_dirs, new_cons = merge_persona_adjustments(
            {}, {}, {}, result
        )

        assert new_dirs["NewAgent"] == ["first directive"]
        assert new_cons["NewAgent"] == ["first constraint"]
