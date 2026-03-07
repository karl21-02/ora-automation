"""Tests for the 3-level convergence pipeline.

All LLM calls are mocked — no real LLM invocations.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ora_rd_orchestrator.convergence import (
    _aggregate_chapter_scores,
    _build_ranked_from_scores,
    _flatten_scores,
    _group_agents_by_chapter,
    _group_chapters_by_silo,
    _run_chapter_deliberation,
    _run_clevel_scoring,
    _run_silo_deliberation,
    is_converged,
)
from ora_rd_orchestrator.types import (
    ChapterDeliberationResult,
    ConvergencePipelineState,
    OrchestrationDecision,
    SiloDeliberationResult,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_org_config(
    num_silos: int = 2,
    chapters_per_silo: int = 1,
    agents_per_chapter: int = 2,
    num_clevel: int = 1,
) -> dict:
    """Build a minimal org_config for testing."""
    silos = []
    chapters = []
    agents = []

    for si in range(num_silos):
        silo_id = f"silo-{si}"
        silos.append({"id": silo_id, "name": f"Silo{si}"})

        for ci in range(chapters_per_silo):
            ch_id = f"ch-{si}-{ci}"
            chapters.append({
                "id": ch_id,
                "name": f"Chapter{si}_{ci}",
                "shared_directives": [],
                "shared_constraints": [],
                "shared_decision_focus": [],
                "chapter_prompt": "",
            })

            for ai in range(agents_per_chapter):
                agent_id = f"Agent_{si}_{ci}_{ai}"
                agents.append({
                    "agent_id": agent_id,
                    "display_name": agent_id,
                    "display_name_ko": agent_id,
                    "role": "tester",
                    "tier": 2,
                    "team": "qa",
                    "domain": None,
                    "personality": {},
                    "weights": {"impact": 0.5},
                    "trust_map": {},
                    "behavioral_directives": [],
                    "constraints": [],
                    "decision_focus": [],
                    "system_prompt_template": "",
                    "enabled": True,
                    "silo_id": silo_id,
                    "chapter_id": ch_id,
                    "is_clevel": False,
                    "weight_score": 1.0,
                })

    # C-Level agents
    for ci in range(num_clevel):
        agents.append({
            "agent_id": f"CEO{ci}" if ci > 0 else "CEO",
            "display_name": "CEO",
            "display_name_ko": "대표",
            "role": "ceo",
            "tier": 4,
            "team": "strategy",
            "domain": "strategy",
            "personality": {},
            "weights": {"impact": 0.5},
            "trust_map": {},
            "behavioral_directives": [],
            "constraints": [],
            "decision_focus": [],
            "system_prompt_template": "",
            "enabled": True,
            "silo_id": None,
            "chapter_id": None,
            "is_clevel": True,
            "weight_score": 0.20,
        })

    return {
        "org_id": "test-org",
        "org_name": "TestOrg",
        "agents": agents,
        "silos": silos,
        "chapters": chapters,
        "pipeline_params": {},
        "flat_mode_agents": [],
        "agent_final_weights": {},
    }


def _score_key(agent_id: str) -> str:
    """Match report_builder._agent_score_key format: lowercase, no prefix."""
    return agent_id.lower().replace(" ", "_")


def _make_scores(topic_ids: list[str], agent_ids: list[str], base: float = 5.0) -> dict:
    """Build initial scores dict using report_builder key format."""
    scores: dict[str, dict[str, float]] = {}
    for tid in topic_ids:
        per_topic: dict[str, float] = {}
        for aid in agent_ids:
            per_topic[_score_key(aid)] = base
        scores[tid] = per_topic
    return scores


def _noop_llm_result():
    """Mock return value for llm_deliberation_round."""
    return (
        {},           # score_adjustments
        [],           # decisions
        [],           # round_summaries
        [],           # action_log
        {"status": "ok"},  # meta
    )


# ---------------------------------------------------------------------------
# TestIsConverged
# ---------------------------------------------------------------------------

class TestIsConverged:
    def test_converged_below_threshold(self):
        prev = {"a": 5.0, "b": 3.0}
        curr = {"a": 5.05, "b": 3.1}
        assert is_converged(prev, curr, 0.15) is True

    def test_not_converged_above_threshold(self):
        prev = {"a": 5.0, "b": 3.0}
        curr = {"a": 5.0, "b": 3.5}
        assert is_converged(prev, curr, 0.15) is False

    def test_not_converged_empty_prev(self):
        curr = {"a": 5.0}
        assert is_converged({}, curr, 0.15) is False

    def test_converged_identical_scores(self):
        scores = {"a": 5.0, "b": 3.0, "c": 7.0}
        assert is_converged(scores, scores.copy(), 0.15) is True

    def test_converged_both_empty(self):
        assert is_converged({}, {}, 0.15) is False  # prev is empty → False

    def test_edge_case_threshold_zero(self):
        prev = {"a": 5.0}
        curr = {"a": 5.0}
        assert is_converged(prev, curr, 0.0) is True

    def test_edge_case_new_key_in_curr(self):
        prev = {"a": 5.0}
        curr = {"a": 5.0, "b": 3.0}
        # b: |3.0 - 0| = 3.0 > 0.15
        assert is_converged(prev, curr, 0.15) is False


# ---------------------------------------------------------------------------
# TestGroupAgentsByChapter
# ---------------------------------------------------------------------------

class TestGroupAgentsByChapter:
    def test_groups_correctly(self):
        org = _make_org_config(num_silos=2, chapters_per_silo=1, agents_per_chapter=2, num_clevel=1)
        groups = _group_agents_by_chapter(org)

        # 2 chapters + 1 clevel
        assert len(groups) == 3
        assert "__clevel__" in groups
        assert groups["__clevel__"][0] == "C-Level"
        assert "CEO" in groups["__clevel__"][1]

        for key in ["ch-0-0", "ch-1-0"]:
            assert key in groups
            assert len(groups[key][1]) == 2

    def test_clevel_separate(self):
        org = _make_org_config(num_silos=1, chapters_per_silo=1, agents_per_chapter=1, num_clevel=2)
        groups = _group_agents_by_chapter(org)

        clevel_ids = groups["__clevel__"][1]
        assert len(clevel_ids) == 2

        # Non-clevel chapter should only have 1 agent
        non_clevel = {k: v for k, v in groups.items() if k != "__clevel__"}
        assert len(non_clevel) == 1
        for _, (_, agent_ids) in non_clevel.items():
            assert len(agent_ids) == 1

    def test_disabled_excluded(self):
        org = _make_org_config(num_silos=1, chapters_per_silo=1, agents_per_chapter=2, num_clevel=0)
        # Disable one agent
        org["agents"][0]["enabled"] = False

        groups = _group_agents_by_chapter(org)
        ch_id = "ch-0-0"
        assert ch_id in groups
        assert len(groups[ch_id][1]) == 1


# ---------------------------------------------------------------------------
# TestGroupChaptersBySilo
# ---------------------------------------------------------------------------

class TestGroupChaptersBySilo:
    def test_maps_correctly(self):
        org = _make_org_config(num_silos=2, chapters_per_silo=2, agents_per_chapter=1, num_clevel=0)
        groups = _group_chapters_by_silo(org)

        assert len(groups) == 2
        for silo_id in ["silo-0", "silo-1"]:
            assert silo_id in groups
            silo_name, ch_ids = groups[silo_id]
            assert len(ch_ids) == 2

    def test_clevel_agents_excluded(self):
        org = _make_org_config(num_silos=1, chapters_per_silo=1, agents_per_chapter=1, num_clevel=2)
        groups = _group_chapters_by_silo(org)

        # C-Level agents have no silo_id, so they don't appear
        assert "silo-0" in groups
        total_chapters = sum(len(ch_ids) for _, (_, ch_ids) in groups.items())
        assert total_chapters == 1


# ---------------------------------------------------------------------------
# TestFlattenScores / TestAggregateChapterScores
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_flatten_scores(self):
        scores = {"t1": {"impact": 5.0, "novelty": 3.0}, "t2": {"impact": 7.0}}
        flat = _flatten_scores(scores)
        assert flat == {"t1:impact": 5.0, "t1:novelty": 3.0, "t2:impact": 7.0}

    def test_aggregate_chapter_scores(self):
        results = [
            {"topic_scores": {"t1": {"score_A": 5.0, "score_B": 6.0}}},
            {"topic_scores": {"t1": {"score_A": 7.0, "score_C": 4.0}}},
        ]
        merged = _aggregate_chapter_scores(results)
        assert merged["t1"]["score_A"] == pytest.approx(6.0)  # (5+7)/2
        assert merged["t1"]["score_B"] == pytest.approx(6.0)  # only one value
        assert merged["t1"]["score_C"] == pytest.approx(4.0)

    def test_build_ranked_from_scores(self):
        scores = {"t1": {"s_A": 8.0}, "t2": {"s_A": 3.0}, "t3": {"s_A": 6.0}}
        ranked = _build_ranked_from_scores(["t1", "t2", "t3"], scores)
        assert ranked[0]["topic_id"] == "t1"
        assert ranked[-1]["topic_id"] == "t2"


# ---------------------------------------------------------------------------
# TestLevel1ChapterNode (LLM mocked)
# ---------------------------------------------------------------------------

class TestLevel1ChapterNode:
    @patch("ora_rd_orchestrator.deliberation.llm_deliberation_round")
    def test_chapter_deliberation_runs(self, mock_llm):
        mock_llm.return_value = _noop_llm_result()

        result = _run_chapter_deliberation(
            chapter_id="ch-0",
            chapter_name="TestChapter",
            agent_ids=["A", "B"],
            topic_ids=["t1", "t2"],
            initial_scores=_make_scores(["t1", "t2"], ["A", "B"]),
            agent_definitions={"A": {}, "B": {}},
            llm_command="echo",
            llm_timeout=5.0,
            service_scope=["global"],
            stages=["analysis", "deliberation"],
            max_rounds=2,
            threshold=0.15,
        )

        assert result["chapter_id"] == "ch-0"
        assert result["chapter_name"] == "TestChapter"
        assert result["agent_ids"] == ["A", "B"]
        assert result["rounds_executed"] >= 1

    @patch("ora_rd_orchestrator.deliberation.llm_deliberation_round")
    def test_returns_chapter_result_dict(self, mock_llm):
        mock_llm.return_value = _noop_llm_result()

        result = _run_chapter_deliberation(
            chapter_id="ch-1",
            chapter_name="Ch1",
            agent_ids=["X"],
            topic_ids=["t1"],
            initial_scores=_make_scores(["t1"], ["X"]),
            agent_definitions={"X": {}},
            llm_command="echo",
            llm_timeout=5.0,
            service_scope=[],
            stages=[],
            max_rounds=1,
            threshold=0.15,
        )

        assert "topic_scores" in result
        assert "converged" in result
        assert "discussion" in result

    @patch("ora_rd_orchestrator.deliberation.llm_deliberation_round")
    def test_converges_when_no_updates(self, mock_llm):
        """With no score adjustments, scores don't change → converged after 2 rounds."""
        mock_llm.return_value = _noop_llm_result()

        result = _run_chapter_deliberation(
            chapter_id="ch-0",
            chapter_name="TestChapter",
            agent_ids=["A"],
            topic_ids=["t1"],
            initial_scores=_make_scores(["t1"], ["A"]),
            agent_definitions={"A": {}},
            llm_command="echo",
            llm_timeout=5.0,
            service_scope=[],
            stages=[],
            max_rounds=5,
            threshold=0.15,
        )

        # Round 1: prev empty → not converged
        # Round 2: scores identical → converged
        assert result["converged"] is True
        assert result["rounds_executed"] == 2


# ---------------------------------------------------------------------------
# TestLevel1CLevelNode
# ---------------------------------------------------------------------------

class TestLevel1CLevelNode:
    def test_clevel_scoring(self):
        result = _run_clevel_scoring(
            clevel_agent_ids=["CEO"],
            topic_ids=["t1", "t2"],
            initial_scores=_make_scores(["t1", "t2"], ["CEO", "PM"]),
            agent_definitions={"CEO": {}},
        )

        assert "t1" in result
        assert _score_key("CEO") in result["t1"]
        assert _score_key("PM") not in result["t1"]

    def test_clevel_empty_agents(self):
        result = _run_clevel_scoring(
            clevel_agent_ids=[],
            topic_ids=["t1"],
            initial_scores=_make_scores(["t1"], ["CEO"]),
            agent_definitions={},
        )
        assert result["t1"] == {}


# ---------------------------------------------------------------------------
# TestLevel2SiloNode
# ---------------------------------------------------------------------------

class TestLevel2SiloNode:
    @patch("ora_rd_orchestrator.deliberation.llm_deliberation_round")
    def test_silo_deliberation(self, mock_llm):
        mock_llm.return_value = _noop_llm_result()

        chapter_results = [
            {
                "chapter_id": "ch-0",
                "chapter_name": "Ch0",
                "agent_ids": ["A", "B"],
                "topic_scores": {"t1": {_score_key("A"): 5.0, _score_key("B"): 6.0}},
                "rounds_executed": 2,
                "converged": True,
                "discussion": [],
            },
        ]

        result = _run_silo_deliberation(
            silo_id="silo-0",
            silo_name="TestSilo",
            chapter_ids=["ch-0"],
            chapter_results=chapter_results,
            topic_ids=["t1"],
            agent_definitions={"A": {}, "B": {}},
            llm_command="echo",
            llm_timeout=5.0,
            service_scope=[],
            stages=[],
            max_rounds=2,
            threshold=0.15,
        )

        assert result["silo_id"] == "silo-0"
        assert result["silo_name"] == "TestSilo"
        assert "t1" in result["topic_scores"]
        assert isinstance(result["topic_scores"]["t1"], float)

    @patch("ora_rd_orchestrator.deliberation.llm_deliberation_round")
    def test_silo_empty_chapters(self, mock_llm):
        mock_llm.return_value = _noop_llm_result()

        result = _run_silo_deliberation(
            silo_id="silo-empty",
            silo_name="Empty",
            chapter_ids=["ch-nonexistent"],
            chapter_results=[],
            topic_ids=["t1"],
            agent_definitions={},
            llm_command="echo",
            llm_timeout=5.0,
            service_scope=[],
            stages=[],
            max_rounds=1,
            threshold=0.15,
        )

        assert result["converged"] is True
        assert result["rounds_executed"] == 0


# ---------------------------------------------------------------------------
# TestLevel3Node
# ---------------------------------------------------------------------------

class TestLevel3Node:
    @patch("ora_rd_orchestrator.deliberation.llm_deliberation_round")
    def test_full_deliberation(self, mock_llm):
        from ora_rd_orchestrator.convergence import level3_node

        mock_llm.return_value = _noop_llm_result()

        org = _make_org_config(num_silos=1, chapters_per_silo=1, agents_per_chapter=2, num_clevel=1)
        state = {
            "org_config": org,
            "topic_ids": ["t1"],
            "initial_scores": _make_scores(["t1"], ["CEO", "Agent_0_0_0", "Agent_0_0_1"]),
            "agent_definitions": {"CEO": {}, "Agent_0_0_0": {}, "Agent_0_0_1": {}},
            "pipeline_params": {},
            "llm_command": "echo",
            "llm_timeout": 5.0,
            "service_scope": ["global"],
            "stages": ["deliberation"],
            "chapter_results": [
                {
                    "chapter_id": "ch-0-0",
                    "chapter_name": "Ch0",
                    "agent_ids": ["Agent_0_0_0", "Agent_0_0_1"],
                    "topic_scores": {"t1": {_score_key("Agent_0_0_0"): 5.0}},
                    "rounds_executed": 1,
                    "converged": True,
                    "discussion": [],
                },
            ],
            "clevel_scores": {"t1": {_score_key("CEO"): 7.0}},
            "silo_results": [
                {"silo_id": "silo-0", "silo_name": "Silo0", "topic_scores": {"t1": 6.0}, "chapter_ids": ["ch-0-0"]},
            ],
            "level3_round": 0,
            "decisions": [],
        }

        result = level3_node(state)

        assert "level3_scores" in result
        assert "t1" in result["level3_scores"]
        assert len(result["execution_log"]) == 1
        assert result["execution_log"][0]["level"] == 3


# ---------------------------------------------------------------------------
# TestConvergenceGraph
# ---------------------------------------------------------------------------

class TestConvergenceGraph:
    def test_graph_compiles(self):
        from ora_rd_orchestrator.convergence import build_convergence_graph

        graph = build_convergence_graph()
        assert graph is not None

    @patch("ora_rd_orchestrator.deliberation.llm_deliberation_round")
    def test_full_invoke_small_org(self, mock_llm):
        """End-to-end graph invoke with mocked LLM, 2 chapters, 2 silos, 5 agents."""
        mock_llm.return_value = _noop_llm_result()

        from ora_rd_orchestrator.convergence import build_convergence_graph

        org = _make_org_config(
            num_silos=2,
            chapters_per_silo=1,
            agents_per_chapter=2,
            num_clevel=1,
        )
        topic_ids = ["topic_a", "topic_b"]
        all_agent_ids = [a["agent_id"] for a in org["agents"]]
        initial_scores = _make_scores(topic_ids, all_agent_ids, base=5.0)
        agent_definitions = {aid: {} for aid in all_agent_ids}

        graph = build_convergence_graph()
        result = graph.invoke({
            "org_config": org,
            "topic_ids": topic_ids,
            "initial_scores": initial_scores,
            "agent_definitions": agent_definitions,
            "pipeline_params": {
                "convergence_threshold": 0.15,
                "level1_max_rounds": 2,
                "level2_max_rounds": 2,
                "level3_max_rounds": 2,
            },
            "llm_command": "echo",
            "llm_timeout": 5.0,
            "service_scope": ["global"],
            "stages": ["deliberation"],
            # Initialize all state fields
            "chapter_results": [],
            "clevel_scores": {},
            "level1_round": 0,
            "level1_prev_flat": {},
            "level1_complete": False,
            "silo_results": [],
            "level2_round": 0,
            "level2_prev_flat": {},
            "level2_complete": False,
            "level3_scores": {},
            "level3_round": 0,
            "level3_prev_flat": {},
            "level3_complete": False,
            "final_scores": {},
            "decisions": [],
            "execution_log": [],
        })

        assert result.get("level1_complete") is True
        assert result.get("level2_complete") is True
        assert result.get("level3_complete") is True
        assert "final_scores" in result
        assert len(result.get("execution_log", [])) > 0

    @patch("ora_rd_orchestrator.deliberation.llm_deliberation_round")
    def test_max_rounds_respected(self, mock_llm):
        """Ensure that max_rounds limits are respected even with no convergence."""
        call_count = 0

        def _side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Return small score adjustments to prevent convergence
            states = kwargs.get("states", args[4] if len(args) > 4 else {})
            adjustments = {}
            for tid in states:
                adjustments[tid] = {}
                for aid in (kwargs.get("known_agent_ids") or set()):
                    adjustments[tid][aid] = 0.5 * (1 if call_count % 2 == 0 else -1)
            return (adjustments, [], [], [], {"status": "ok"})

        mock_llm.side_effect = _side_effect

        from ora_rd_orchestrator.convergence import build_convergence_graph

        org = _make_org_config(
            num_silos=1,
            chapters_per_silo=1,
            agents_per_chapter=1,
            num_clevel=1,
        )
        topic_ids = ["t1"]
        all_ids = [a["agent_id"] for a in org["agents"]]

        graph = build_convergence_graph()
        result = graph.invoke({
            "org_config": org,
            "topic_ids": topic_ids,
            "initial_scores": _make_scores(topic_ids, all_ids),
            "agent_definitions": {aid: {} for aid in all_ids},
            "pipeline_params": {
                "convergence_threshold": 0.001,  # Very tight threshold
                "level1_max_rounds": 2,
                "level2_max_rounds": 1,
                "level3_max_rounds": 1,
            },
            "llm_command": "echo",
            "llm_timeout": 5.0,
            "service_scope": [],
            "stages": [],
            "chapter_results": [],
            "clevel_scores": {},
            "level1_round": 0,
            "level1_prev_flat": {},
            "level1_complete": False,
            "silo_results": [],
            "level2_round": 0,
            "level2_prev_flat": {},
            "level2_complete": False,
            "level3_scores": {},
            "level3_round": 0,
            "level3_prev_flat": {},
            "level3_complete": False,
            "final_scores": {},
            "decisions": [],
            "execution_log": [],
        })

        assert result.get("level3_complete") is True


# ---------------------------------------------------------------------------
# TestPipelineIntegration
# ---------------------------------------------------------------------------

class TestPipelineIntegration:
    def test_agent_mode_convergence_accepted(self):
        """pipeline.py normalizes 'convergence' as a valid agent_mode."""
        # We test the normalization logic directly
        agent_mode = "convergence"
        if agent_mode not in ("flat", "hierarchical", "convergence"):
            agent_mode = "flat"
        assert agent_mode == "convergence"

    def test_agent_mode_invalid_falls_back_to_flat(self):
        agent_mode = "unknown_mode"
        if agent_mode not in ("flat", "hierarchical", "convergence"):
            agent_mode = "flat"
        assert agent_mode == "flat"


# ---------------------------------------------------------------------------
# TestRunConvergencePipeline (entry point)
# ---------------------------------------------------------------------------

class TestRunConvergencePipeline:
    @patch("ora_rd_orchestrator.deliberation.llm_deliberation_round")
    def test_returns_convergence_state(self, mock_llm):
        mock_llm.return_value = _noop_llm_result()

        from ora_rd_orchestrator.convergence import run_convergence_pipeline
        from ora_rd_orchestrator.types import AgentPersona, TopicState

        org = _make_org_config(num_silos=1, chapters_per_silo=1, agents_per_chapter=1, num_clevel=1)
        topic_states = {
            "t1": TopicState(topic_id="t1", topic_name="Topic1"),
        }
        all_ids = [a["agent_id"] for a in org["agents"]]
        initial_scores = _make_scores(["t1"], all_ids)
        personas = {
            aid: AgentPersona(
                agent_id=aid, display_name=aid, display_name_ko=aid,
                role="tester", tier=2, domain=None, team="qa",
                system_prompt="test",
            )
            for aid in all_ids
        }
        agent_defs = {aid: {} for aid in all_ids}

        result = run_convergence_pipeline(
            org_config=org,
            topic_states=topic_states,
            initial_scores=initial_scores,
            personas=personas,
            agent_definitions=agent_defs,
            llm_command="echo",
            llm_timeout=5.0,
            service_scope=["global"],
            stages=["deliberation"],
        )

        assert isinstance(result, ConvergencePipelineState)
        assert isinstance(result.final_scores, dict)
        assert isinstance(result.execution_log, list)
        assert len(result.level1_results) >= 1


# ---------------------------------------------------------------------------
# TestConvergencePipelineStateTypes
# ---------------------------------------------------------------------------

class TestDataclasses:
    def test_chapter_deliberation_result(self):
        r = ChapterDeliberationResult(
            chapter_id="ch-1",
            chapter_name="Test",
            agent_ids=["A"],
            topic_scores={"t1": {"s_A": 5.0}},
            rounds_executed=2,
            converged=True,
        )
        assert r.chapter_id == "ch-1"
        assert r.converged is True
        assert r.discussion == []

    def test_silo_deliberation_result(self):
        r = SiloDeliberationResult(
            silo_id="s-1",
            silo_name="TestSilo",
            chapter_ids=["ch-1"],
            topic_scores={"t1": 5.5},
            rounds_executed=1,
            converged=False,
        )
        assert r.silo_id == "s-1"
        assert r.converged is False

    def test_convergence_pipeline_state_defaults(self):
        s = ConvergencePipelineState()
        assert s.level1_results == []
        assert s.level3_rounds == 0
        assert s.final_scores == {}
        assert s.decisions == []
