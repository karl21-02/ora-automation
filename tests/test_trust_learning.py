"""Tests for dynamic trust_map learning.

All LLM calls are mocked — no real LLM invocations.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from ora_rd_orchestrator.types import (
    OrchestrationDecision,
    ScoreAdjustment,
    TrustLearningResult,
    TrustUpdate,
)


# ---------------------------------------------------------------------------
# TrustUpdate dataclass tests
# ---------------------------------------------------------------------------

class TestTrustUpdate:
    def test_basic_creation(self):
        update = TrustUpdate(
            source_agent="Researcher",
            target_agent="DataAnalyst",
            delta=0.1,
            confidence=0.8,
            reason="DataAnalyst provided accurate predictions",
        )
        assert update.source_agent == "Researcher"
        assert update.target_agent == "DataAnalyst"
        assert update.delta == 0.1
        assert update.confidence == 0.8
        assert update.evidence_topic_ids == []

    def test_to_dict(self):
        update = TrustUpdate(
            source_agent="PM",
            target_agent="Developer",
            delta=-0.05,
            confidence=0.6,
            reason="Developer scores were inconsistent",
            evidence_topic_ids=["topic_1", "topic_2"],
        )
        d = update.to_dict()
        assert d["source_agent"] == "PM"
        assert d["target_agent"] == "Developer"
        assert d["delta"] == -0.05
        assert d["confidence"] == 0.6
        assert d["evidence_topic_ids"] == ["topic_1", "topic_2"]


# ---------------------------------------------------------------------------
# TrustLearningResult tests
# ---------------------------------------------------------------------------

class TestTrustLearningResult:
    def test_empty_result(self):
        result = TrustLearningResult()
        assert result.updates == []
        assert result.meta == {}

    def test_to_dict(self):
        result = TrustLearningResult(
            updates=[
                TrustUpdate("A", "B", 0.1, 0.9, "good"),
                TrustUpdate("C", "D", -0.1, 0.7, "bad"),
            ],
            meta={"status": "ok"},
        )
        d = result.to_dict()
        assert len(d["updates"]) == 2
        assert d["meta"]["status"] == "ok"

    def test_apply_to_trust_map_basic(self):
        result = TrustLearningResult(
            updates=[
                TrustUpdate("A", "B", 0.1, 1.0, "test"),
            ]
        )
        trust_map = {"A": {"B": 0.5}}
        updated = result.apply_to_trust_map(trust_map, decay_factor=1.0)

        # delta=0.1, confidence=1.0, decay=1.0 → +0.1
        assert updated["A"]["B"] == 0.6

    def test_apply_to_trust_map_with_confidence(self):
        result = TrustLearningResult(
            updates=[
                TrustUpdate("A", "B", 0.2, 0.5, "test"),
            ]
        )
        trust_map = {"A": {"B": 0.5}}
        updated = result.apply_to_trust_map(trust_map, decay_factor=1.0)

        # delta=0.2, confidence=0.5 → effective=0.1
        assert updated["A"]["B"] == 0.6

    def test_apply_to_trust_map_with_decay(self):
        result = TrustLearningResult(
            updates=[
                TrustUpdate("A", "B", 0.2, 1.0, "test"),
            ]
        )
        trust_map = {"A": {"B": 0.5}}
        updated = result.apply_to_trust_map(trust_map, decay_factor=0.5)

        # delta=0.2, confidence=1.0, decay=0.5 → effective=0.1
        assert updated["A"]["B"] == 0.6

    def test_apply_to_trust_map_clamps_to_max(self):
        result = TrustLearningResult(
            updates=[
                TrustUpdate("A", "B", 0.2, 1.0, "test"),
            ]
        )
        trust_map = {"A": {"B": 0.95}}
        updated = result.apply_to_trust_map(trust_map, max_trust=1.0, decay_factor=1.0)

        # 0.95 + 0.2 = 1.15 → clamped to 1.0
        assert updated["A"]["B"] == 1.0

    def test_apply_to_trust_map_clamps_to_min(self):
        result = TrustLearningResult(
            updates=[
                TrustUpdate("A", "B", -0.2, 1.0, "test"),
            ]
        )
        trust_map = {"A": {"B": 0.15}}
        updated = result.apply_to_trust_map(trust_map, min_trust=0.1, decay_factor=1.0)

        # 0.15 - 0.2 = -0.05 → clamped to 0.1
        assert updated["A"]["B"] == 0.1

    def test_apply_to_trust_map_creates_new_entry(self):
        result = TrustLearningResult(
            updates=[
                TrustUpdate("A", "B", 0.1, 1.0, "test"),
            ]
        )
        trust_map = {}  # Empty trust map
        updated = result.apply_to_trust_map(trust_map, decay_factor=1.0)

        # Default trust is 0.5, so 0.5 + 0.1 = 0.6
        assert updated["A"]["B"] == 0.6

    def test_apply_to_trust_map_multiple_updates(self):
        result = TrustLearningResult(
            updates=[
                TrustUpdate("A", "B", 0.1, 1.0, "test1"),
                TrustUpdate("A", "C", -0.1, 1.0, "test2"),
                TrustUpdate("B", "A", 0.05, 1.0, "test3"),
            ]
        )
        trust_map = {
            "A": {"B": 0.5, "C": 0.7},
            "B": {"A": 0.6},
        }
        updated = result.apply_to_trust_map(trust_map, decay_factor=1.0)

        assert updated["A"]["B"] == 0.6
        assert updated["A"]["C"] == 0.6
        assert updated["B"]["A"] == 0.65


# ---------------------------------------------------------------------------
# compute_trust_updates tests (with mocked LLM)
# ---------------------------------------------------------------------------

class TestComputeTrustUpdates:
    def _mock_llm_result(self, trust_updates: list[dict], summary: str = ""):
        from ora_rd_orchestrator.types import LLMResult
        return LLMResult(
            status="ok",
            parsed={
                "trust_updates": trust_updates,
                "summary": summary,
            },
        )

    @patch("ora_rd_orchestrator.trust_learning.run_llm_command")
    def test_basic_trust_update(self, mock_llm):
        from ora_rd_orchestrator.trust_learning import compute_trust_updates

        mock_llm.return_value = self._mock_llm_result([
            {
                "source_agent": "Researcher",
                "target_agent": "DataAnalyst",
                "delta": 0.1,
                "confidence": 0.8,
                "reason": "Accurate predictions",
                "evidence_topic_ids": ["t1"],
            }
        ])

        result = compute_trust_updates(
            deliberation_history=[],
            score_adjustments={},
            final_scores={"t1": {"score_researcher": 5.0}},
            decisions=[],
            agent_definitions={
                "Researcher": {"role": "researcher", "tier": 2},
                "DataAnalyst": {"role": "analyst", "tier": 2},
            },
            current_trust_map={},
        )

        assert len(result.updates) == 1
        assert result.updates[0].source_agent == "Researcher"
        assert result.updates[0].target_agent == "DataAnalyst"
        assert result.updates[0].delta == 0.1
        assert result.updates[0].confidence == 0.8

    @patch("ora_rd_orchestrator.trust_learning.run_llm_command")
    def test_filters_invalid_agents(self, mock_llm):
        from ora_rd_orchestrator.trust_learning import compute_trust_updates

        mock_llm.return_value = self._mock_llm_result([
            {
                "source_agent": "UnknownAgent",
                "target_agent": "DataAnalyst",
                "delta": 0.1,
                "confidence": 0.8,
                "reason": "Should be filtered",
            },
            {
                "source_agent": "Researcher",
                "target_agent": "UnknownTarget",
                "delta": 0.1,
                "confidence": 0.8,
                "reason": "Should also be filtered",
            },
        ])

        result = compute_trust_updates(
            deliberation_history=[],
            score_adjustments={},
            final_scores={},
            decisions=[],
            agent_definitions={
                "Researcher": {"role": "researcher"},
                "DataAnalyst": {"role": "analyst"},
            },
            current_trust_map={},
        )

        assert len(result.updates) == 0

    @patch("ora_rd_orchestrator.trust_learning.run_llm_command")
    def test_prevents_self_rating(self, mock_llm):
        from ora_rd_orchestrator.trust_learning import compute_trust_updates

        mock_llm.return_value = self._mock_llm_result([
            {
                "source_agent": "Researcher",
                "target_agent": "Researcher",  # Self-rating
                "delta": 0.2,
                "confidence": 1.0,
                "reason": "I trust myself",
            },
        ])

        result = compute_trust_updates(
            deliberation_history=[],
            score_adjustments={},
            final_scores={},
            decisions=[],
            agent_definitions={"Researcher": {"role": "researcher"}},
            current_trust_map={},
        )

        assert len(result.updates) == 0

    @patch("ora_rd_orchestrator.trust_learning.run_llm_command")
    def test_clamps_delta_values(self, mock_llm):
        from ora_rd_orchestrator.trust_learning import compute_trust_updates

        mock_llm.return_value = self._mock_llm_result([
            {
                "source_agent": "A",
                "target_agent": "B",
                "delta": 0.5,  # Exceeds max of 0.2
                "confidence": 1.0,
                "reason": "Too high",
            },
            {
                "source_agent": "B",
                "target_agent": "A",
                "delta": -0.5,  # Below min of -0.2
                "confidence": 1.0,
                "reason": "Too low",
            },
        ])

        result = compute_trust_updates(
            deliberation_history=[],
            score_adjustments={},
            final_scores={},
            decisions=[],
            agent_definitions={
                "A": {"role": "a"},
                "B": {"role": "b"},
            },
            current_trust_map={},
        )

        assert len(result.updates) == 2
        assert result.updates[0].delta == 0.2  # Clamped to max
        assert result.updates[1].delta == -0.2  # Clamped to min

    @patch("ora_rd_orchestrator.trust_learning.run_llm_command")
    def test_deduplicates_pairs(self, mock_llm):
        from ora_rd_orchestrator.trust_learning import compute_trust_updates

        mock_llm.return_value = self._mock_llm_result([
            {
                "source_agent": "A",
                "target_agent": "B",
                "delta": 0.1,
                "confidence": 0.8,
                "reason": "First",
            },
            {
                "source_agent": "A",
                "target_agent": "B",
                "delta": 0.15,
                "confidence": 0.9,
                "reason": "Duplicate - should be ignored",
            },
        ])

        result = compute_trust_updates(
            deliberation_history=[],
            score_adjustments={},
            final_scores={},
            decisions=[],
            agent_definitions={
                "A": {"role": "a"},
                "B": {"role": "b"},
            },
            current_trust_map={},
        )

        assert len(result.updates) == 1
        assert result.updates[0].delta == 0.1  # First one wins

    @patch("ora_rd_orchestrator.trust_learning.run_llm_command")
    def test_handles_llm_failure(self, mock_llm):
        from ora_rd_orchestrator.trust_learning import compute_trust_updates
        from ora_rd_orchestrator.types import LLMResult

        mock_llm.return_value = LLMResult(
            status="failed",
            parsed={"reason": "timeout"},
        )

        result = compute_trust_updates(
            deliberation_history=[],
            score_adjustments={},
            final_scores={},
            decisions=[],
            agent_definitions={"A": {}},
            current_trust_map={},
        )

        assert len(result.updates) == 0
        assert result.meta["status"] == "failed"


# ---------------------------------------------------------------------------
# merge_trust_maps tests
# ---------------------------------------------------------------------------

class TestMergeTrustMaps:
    def test_does_not_modify_original(self):
        from ora_rd_orchestrator.trust_learning import merge_trust_maps

        base = {"A": {"B": 0.5}}
        result = TrustLearningResult(
            updates=[TrustUpdate("A", "B", 0.1, 1.0, "test")]
        )

        merged = merge_trust_maps(base, result, decay_factor=1.0)

        # Original unchanged
        assert base["A"]["B"] == 0.5
        # Merged has update
        assert merged["A"]["B"] == 0.6

    def test_preserves_existing_entries(self):
        from ora_rd_orchestrator.trust_learning import merge_trust_maps

        base = {
            "A": {"B": 0.5, "C": 0.8},
            "D": {"E": 0.6},
        }
        result = TrustLearningResult(
            updates=[TrustUpdate("A", "B", 0.1, 1.0, "test")]
        )

        merged = merge_trust_maps(base, result, decay_factor=1.0)

        # Updated
        assert merged["A"]["B"] == 0.6
        # Preserved
        assert merged["A"]["C"] == 0.8
        assert merged["D"]["E"] == 0.6

    def test_empty_updates_returns_copy(self):
        from ora_rd_orchestrator.trust_learning import merge_trust_maps

        base = {"A": {"B": 0.5}}
        result = TrustLearningResult(updates=[])

        merged = merge_trust_maps(base, result)

        assert merged == base
        assert merged is not base  # Should be a copy
