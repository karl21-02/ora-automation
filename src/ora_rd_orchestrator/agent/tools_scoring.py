"""Scoring, deliberation, and consensus tools for the ReAct agent.

Wraps existing scoring, deliberation, and consensus functions
with the AgentState interface.
"""
from __future__ import annotations

import logging
from typing import Any

from .state import AgentState
from .tool_registry import Tool, ToolParameter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _handle_score_all_topics(state: AgentState, **kwargs: Any) -> dict:
    """Score all topics across all agents via LLM."""
    from ..config import FLAT_MODE_AGENTS
    from ..report_builder import _agent_score_key, build_agent_rankings, build_final_score
    from ..scoring import compute_agent_score, score_all_agents

    if not state.personas:
        return {"error": "Personas not loaded. Call load_personas first."}
    if not state.topic_states:
        return {"error": "Topics not analyzed. Call analyze_workspace first."}

    all_agent_scores = score_all_agents(
        topic_states=state.topic_states,
        personas=state.personas,
        llm_command="",  # provider-first (no subprocess)
        llm_timeout=10.0,
        agent_definitions=state.agent_definitions,
        agent_filter=FLAT_MODE_AGENTS,
    )

    # Build per-topic score dict: {topic_id: {score_agentname: float}}
    scores: dict[str, dict[str, Any]] = {}
    for topic_id in state.topic_states:
        per_topic: dict[str, Any] = {}
        for agent_id, topic_scores in all_agent_scores.items():
            if topic_id in topic_scores:
                features = topic_scores[topic_id]
                persona = state.personas.get(agent_id)
                weights = persona.weights if persona else {}
                per_topic[_agent_score_key(agent_id)] = compute_agent_score(features, weights)
        scores[topic_id] = per_topic
    state.scores = scores

    # Build ranked list and agent rankings
    ranked = build_final_score(state.topic_states, scores)
    state.ranked = ranked

    agent_rankings = build_agent_rankings(scores, top_k=state.top_k, agent_filter=FLAT_MODE_AGENTS)
    state.agent_rankings = agent_rankings

    return {
        "topics_scored": len(scores),
        "agents_scored": len(all_agent_scores),
        "top_ranked": [
            {"topic_id": r["topic_id"], "topic_name": r["topic_name"], "total_score": r.get("total_score", 0)}
            for r in ranked[:5]
        ],
    }


def _handle_run_deliberation(
    state: AgentState, num_rounds: int = 2, **kwargs: Any
) -> dict:
    """Run multi-round LLM deliberation."""
    from ..config import ORCHESTRATION_STAGES_DEFAULT
    from ..deliberation import llm_deliberation_round
    from ..report_builder import _agent_score_key, _clamp_score, build_final_score

    if not state.scores:
        return {"error": "Scoring not done. Call score_all_topics first."}

    stages = list(ORCHESTRATION_STAGES_DEFAULT)
    service_scope_list = state.service_scope or []
    discussion: list[dict] = []
    all_decisions: list = []

    for round_no in range(1, num_rounds + 1):
        ranked_snapshot = build_final_score(state.topic_states, state.scores)

        score_updates, decisions, round_summaries, llm_actions, llm_state = llm_deliberation_round(
            round_no=round_no,
            stages=stages,
            service_scope=service_scope_list,
            states=state.topic_states,
            working_scores=state.scores,
            ranked=ranked_snapshot,
            previous_decisions=[d.to_dict() for d in all_decisions],
            previous_discussion=discussion,
            agent_definitions=state.agent_definitions,
        )

        # Apply score adjustments (supports both ScoreAdjustment v2 and float v1)
        from ..types import ScoreAdjustment
        for topic_id, per_agent in score_updates.items():
            if topic_id not in state.scores:
                continue
            for agent_name, adjustment in per_agent.items():
                agent_key = _agent_score_key(agent_name)
                if agent_key not in state.scores[topic_id]:
                    continue
                # Handle both ScoreAdjustment and legacy float
                if isinstance(adjustment, ScoreAdjustment):
                    delta = adjustment.delta
                else:
                    delta = float(adjustment)
                state.scores[topic_id][agent_key] = _clamp_score(
                    state.scores[topic_id][agent_key] + delta, 0.0, 10.0
                )

        all_decisions.extend(decisions)
        discussion.extend(round_summaries)

    state.pipeline_decisions = all_decisions

    # Refresh ranked after deliberation
    state.ranked = build_final_score(state.topic_states, state.scores)

    return {
        "rounds_executed": num_rounds,
        "decisions": len(all_decisions),
        "discussion_entries": len(discussion),
    }


def _handle_apply_consensus(state: AgentState, top_k: int = 0, **kwargs: Any) -> dict:
    """Apply final consensus to select top topics."""
    from ..consensus import apply_hybrid_consensus

    if not state.ranked:
        return {"error": "Ranking not available. Call score_all_topics first."}

    effective_top_k = top_k if top_k > 0 else state.top_k

    consensus = apply_hybrid_consensus(
        ranked=state.ranked,
        states=state.topic_states,
        scores=state.scores,
        agent_rankings=state.agent_rankings or {},
        discussion=None,
        top_k=effective_top_k,
        agent_definitions=state.agent_definitions,
    )
    state.consensus_summary = consensus

    final_ids = consensus.get("final_topic_ids", [])
    return {
        "status": consensus.get("status", "unknown"),
        "method": consensus.get("method", "unknown"),
        "final_topic_count": len(final_ids),
        "final_topic_ids": final_ids[:effective_top_k],
    }


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_scoring_tools() -> list[Tool]:
    """Return scoring/deliberation/consensus tools for registration."""
    return [
        Tool(
            name="score_all_topics",
            description="모든 에이전트가 모든 토픽에 대해 점수를 매깁니다. analyze_workspace 이후 실행합니다.",
            parameters=[],
            handler=_handle_score_all_topics,
            category="scoring",
        ),
        Tool(
            name="run_deliberation",
            description="에이전트 간 다중 라운드 토론을 실행합니다. 점수 조정과 의사결정이 포함됩니다.",
            parameters=[
                ToolParameter(
                    name="num_rounds",
                    type="integer",
                    description="토론 라운드 수 (기본값: 2)",
                ),
            ],
            handler=_handle_run_deliberation,
            category="scoring",
        ),
        Tool(
            name="apply_consensus",
            description="최종 합의를 적용하여 상위 토픽을 선정합니다. 스코어링 또는 토론 이후 실행합니다.",
            parameters=[
                ToolParameter(
                    name="top_k",
                    type="integer",
                    description="선정할 최종 토픽 수 (기본값: state의 top_k 사용)",
                ),
            ],
            handler=_handle_apply_consensus,
            category="scoring",
        ),
    ]
