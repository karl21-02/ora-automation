"""LangGraph-based 3-level convergence pipeline.

When org_config contains chapters/silos, this module builds a StateGraph
that runs deliberation in three converging levels:

    Level 1: chapter-internal deliberation (parallel fan-out per chapter)
    Level 2: silo-internal deliberation (parallel fan-out per silo)
    Level 3: C-Level + silo representatives full deliberation

Each level loops until scores converge (max delta < threshold) or max_rounds.
"""
from __future__ import annotations

import logging
import operator
import threading
from typing import Annotated, Any

from typing_extensions import TypedDict

from .config import (
    CONVERGENCE_LEVEL1_MAX_ROUNDS,
    CONVERGENCE_LEVEL2_MAX_ROUNDS,
    CONVERGENCE_LEVEL3_MAX_ROUNDS,
    CONVERGENCE_THRESHOLD_DEFAULT,
    LLM_DELIBERATION_TIMEOUT_SECONDS,
)
from .types import (
    AgentPersona,
    ChapterDeliberationResult,
    ConvergencePipelineState,
    OrchestrationDecision,
    ProgressCallback,
    SiloDeliberationResult,
    TopicState,
)
from .report_builder import _agent_score_key

logger = logging.getLogger(__name__)

# Score bounds and defaults
SCORE_MIN = 0.0
SCORE_MAX = 10.0
SCORE_DEFAULT = 5.0


def _compute_average(values: list[float], decimals: int = 4) -> float:
    """Compute average with rounding, returns 0.0 for empty list."""
    if not values:
        return 0.0
    return round(sum(values) / len(values), decimals)


# ---------------------------------------------------------------------------
# LangGraph state schema
# ---------------------------------------------------------------------------

class ConvergenceGraphState(TypedDict):
    # Input (immutable after initialization)
    org_config: dict
    topic_ids: list[str]
    initial_scores: dict                    # {topic_id: {score_key: float}}
    agent_definitions: dict
    pipeline_params: dict
    llm_command: str
    llm_timeout: float
    service_scope: list[str]
    stages: list[str]

    # Level 1 (fan-in via operator.add)
    chapter_results: Annotated[list[dict], operator.add]
    clevel_scores: dict
    level1_round: int
    level1_prev_flat: dict
    level1_complete: bool

    # Level 2 (fan-in via operator.add)
    silo_results: Annotated[list[dict], operator.add]
    level2_round: int
    level2_prev_flat: dict
    level2_complete: bool

    # Level 3
    level3_scores: dict
    level3_round: int
    level3_prev_flat: dict
    level3_complete: bool

    # Output
    final_scores: dict
    decisions: list[dict]
    execution_log: Annotated[list[dict], operator.add]


# ---------------------------------------------------------------------------
# Convergence check
# ---------------------------------------------------------------------------

def is_converged(
    prev: dict[str, float],
    curr: dict[str, float],
    threshold: float,
) -> bool:
    """Check whether max score delta between two rounds is below threshold."""
    if not prev:
        return False
    all_keys = set(prev) | set(curr)
    if not all_keys:
        return True
    deltas = [abs(curr.get(k, 0.0) - prev.get(k, 0.0)) for k in all_keys]
    return max(deltas) <= threshold


# ---------------------------------------------------------------------------
# Grouping helpers
# ---------------------------------------------------------------------------

def _group_agents_by_chapter(
    org_config: dict,
) -> dict[str, tuple[str, list[str]]]:
    """chapter_id -> (chapter_name, [agent_ids]).

    C-Level agents (is_clevel=True or chapter_id=None) are grouped under
    the special key ``'__clevel__'``.
    """
    # Build chapter name lookup
    chapter_names: dict[str, str] = {}
    for ch in org_config.get("chapters", []):
        chapter_names[ch["id"]] = ch.get("name", ch["id"])

    groups: dict[str, tuple[str, list[str]]] = {}
    clevel_agents: list[str] = []

    for agent in org_config.get("agents", []):
        if not agent.get("enabled", True):
            continue
        if agent.get("is_clevel") or not agent.get("chapter_id"):
            clevel_agents.append(agent["agent_id"])
            continue
        ch_id = agent["chapter_id"]
        ch_name = chapter_names.get(ch_id, ch_id)
        if ch_id not in groups:
            groups[ch_id] = (ch_name, [])
        groups[ch_id][1].append(agent["agent_id"])

    if clevel_agents:
        groups["__clevel__"] = ("C-Level", clevel_agents)
    return groups


def _group_chapters_by_silo(
    org_config: dict,
) -> dict[str, tuple[str, list[str]]]:
    """silo_id -> (silo_name, [chapter_ids])."""
    silo_names: dict[str, str] = {}
    for silo in org_config.get("silos", []):
        silo_names[silo["id"]] = silo.get("name", silo["id"])

    # Build agent→chapter mapping, then chapter→silo from agents
    chapter_to_silo: dict[str, str] = {}
    for agent in org_config.get("agents", []):
        if not agent.get("enabled", True):
            continue
        ch_id = agent.get("chapter_id")
        silo_id = agent.get("silo_id")
        if ch_id and silo_id:
            chapter_to_silo[ch_id] = silo_id

    groups: dict[str, tuple[str, list[str]]] = {}
    for ch_id, silo_id in chapter_to_silo.items():
        silo_name = silo_names.get(silo_id, silo_id)
        if silo_id not in groups:
            groups[silo_id] = (silo_name, [])
        if ch_id not in groups[silo_id][1]:
            groups[silo_id][1].append(ch_id)
    return groups


# ---------------------------------------------------------------------------
# Score flattening helpers (for convergence comparison)
# ---------------------------------------------------------------------------

def _flatten_scores(scores: dict[str, dict[str, float]]) -> dict[str, float]:
    """Flatten nested {topic_id: {key: val}} to {topic_id:key: val}."""
    flat: dict[str, float] = {}
    for tid, inner in scores.items():
        if isinstance(inner, dict):
            for k, v in inner.items():
                flat[f"{tid}:{k}"] = float(v)
        else:
            flat[tid] = float(inner)
    return flat


def _aggregate_chapter_scores(
    chapter_results: list[dict],
) -> dict[str, dict[str, float]]:
    """Merge chapter results into {topic_id: {score_key: avg_val}}."""
    accum: dict[str, dict[str, list[float]]] = {}
    for cr in chapter_results:
        for tid, score_dict in cr.get("topic_scores", {}).items():
            if tid not in accum:
                accum[tid] = {}
            for k, v in score_dict.items():
                accum[tid].setdefault(k, []).append(float(v))
    result: dict[str, dict[str, float]] = {}
    for tid, keys in accum.items():
        result[tid] = {k: _compute_average(vs) for k, vs in keys.items()}
    return result


# ---------------------------------------------------------------------------
# Common deliberation loop helper
# ---------------------------------------------------------------------------

def _build_mock_topic_catalog(topic_ids: list[str]) -> dict[str, Any]:
    """Build minimal TopicState-like objects for decision parsing."""
    catalog: dict[str, Any] = {}
    for tid in topic_ids:
        catalog[tid] = type("_TS", (), {
            "topic_name": tid,
            "evidence": [],
            "project_hits": {},
            "compute_features": lambda self=None: {},
            "keyword_hits": 0,
            "business_hits": 0,
            "novelty_hits": 0,
            "code_hits": 0,
            "doc_hits": 0,
            "history_hits": 0,
        })()
    return catalog


def _apply_score_updates(
    working_scores: dict[str, dict[str, float]],
    score_updates: dict,
) -> None:
    """Apply score deltas with 0-10 clamping (in-place).

    Args:
        working_scores: Current scores dict {topic_id: {agent_key: score}}
        score_updates: Updates from LLM {topic_id: {agent_name: delta}}
    """
    for tid, per_agent in score_updates.items():
        if tid not in working_scores:
            continue
        for agent_name, delta in per_agent.items():
            key = _agent_score_key(agent_name)
            if key in working_scores[tid]:
                new_val = working_scores[tid][key] + delta
                working_scores[tid][key] = max(SCORE_MIN, min(SCORE_MAX, new_val))


def _filter_scores_by_agents(
    topic_ids: list[str],
    agent_ids: list[str],
    source_scores: dict[str, dict[str, float]],
    default: float | None = None,
) -> dict[str, dict[str, float]]:
    """Filter source scores to only include specified agents.

    Args:
        topic_ids: List of topic IDs to process
        agent_ids: List of agent IDs to include
        source_scores: Source scores {topic_id: {agent_key: score}}
        default: Default score if agent key not in source. If None, skip missing keys.

    Returns:
        Filtered scores dict {topic_id: {agent_key: score}}
    """
    result: dict[str, dict[str, float]] = {}
    for tid in topic_ids:
        per_topic: dict[str, float] = {}
        topic_scores = source_scores.get(tid, {})
        for aid in agent_ids:
            key = _agent_score_key(aid)
            if default is not None:
                per_topic[key] = topic_scores.get(key, default)
            elif key in topic_scores:
                per_topic[key] = topic_scores[key]
        result[tid] = per_topic
    return result


def _run_deliberation_loop(
    working_scores: dict[str, dict[str, float]],
    agent_ids: list[str],
    topic_ids: list[str],
    agent_definitions: dict,
    llm_command: str,
    llm_timeout: float,
    service_scope: list[str],
    stages: list[str],
    max_rounds: int,
    threshold: float,
) -> tuple[dict[str, dict[str, float]], int, bool, list[dict]]:
    """Run deliberation rounds until convergence.

    Returns:
        (final_scores, rounds_executed, converged, discussion)
    """
    from .deliberation import llm_deliberation_round
    topic_catalog = _build_mock_topic_catalog(topic_ids)
    filtered_defs = {k: v for k, v in agent_definitions.items() if k in agent_ids}

    prev_flat: dict[str, float] = {}
    discussion: list[dict] = []
    rounds_executed = 0
    converged = False

    for round_no in range(1, max_rounds + 1):
        ranked = _build_ranked_from_scores(topic_ids, working_scores)

        score_updates, decisions, summaries, actions, meta = llm_deliberation_round(
            round_no=round_no,
            stages=stages,
            service_scope=service_scope,
            states=topic_catalog,
            working_scores=working_scores,
            ranked=ranked,
            previous_decisions=[],
            previous_discussion=discussion,
            command=llm_command,
            timeout=llm_timeout,
            agent_definitions=filtered_defs,
            known_agent_ids=set(agent_ids),
        )

        _apply_score_updates(working_scores, score_updates)

        if summaries:
            discussion.extend(summaries)
        rounds_executed = round_no

        curr_flat = _flatten_scores(working_scores)
        if is_converged(prev_flat, curr_flat, threshold):
            converged = True
            break
        prev_flat = curr_flat

    return working_scores, rounds_executed, converged, discussion


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

def _run_chapter_deliberation(
    chapter_id: str,
    chapter_name: str,
    agent_ids: list[str],
    topic_ids: list[str],
    initial_scores: dict,
    agent_definitions: dict,
    llm_command: str,
    llm_timeout: float,
    service_scope: list[str],
    stages: list[str],
    max_rounds: int,
    threshold: float,
) -> dict:
    """Run deliberation within a single chapter until convergence."""
    working_scores = _filter_scores_by_agents(topic_ids, agent_ids, initial_scores)

    # Run deliberation loop
    final_scores, rounds_executed, converged, discussion = _run_deliberation_loop(
        working_scores=working_scores,
        agent_ids=agent_ids,
        topic_ids=topic_ids,
        agent_definitions=agent_definitions,
        llm_command=llm_command,
        llm_timeout=llm_timeout,
        service_scope=service_scope,
        stages=stages,
        max_rounds=max_rounds,
        threshold=threshold,
    )

    return {
        "chapter_id": chapter_id,
        "chapter_name": chapter_name,
        "agent_ids": agent_ids,
        "topic_scores": final_scores,
        "rounds_executed": rounds_executed,
        "converged": converged,
        "discussion": discussion,
    }


def _run_clevel_scoring(
    clevel_agent_ids: list[str],
    topic_ids: list[str],
    initial_scores: dict,
    agent_definitions: dict,
) -> dict[str, dict[str, float]]:
    """Extract C-Level agent scores from initial_scores."""
    return _filter_scores_by_agents(topic_ids, clevel_agent_ids, initial_scores)


def _run_silo_deliberation(
    silo_id: str,
    silo_name: str,
    chapter_ids: list[str],
    chapter_results: list[dict],
    topic_ids: list[str],
    agent_definitions: dict,
    llm_command: str,
    llm_timeout: float,
    service_scope: list[str],
    stages: list[str],
    max_rounds: int,
    threshold: float,
) -> dict:
    """Run deliberation among chapter representatives within a silo."""
    # Collect representative agent IDs (first agent from each chapter)
    rep_agents: list[str] = []
    silo_chapter_results = [cr for cr in chapter_results if cr["chapter_id"] in chapter_ids]

    for cr in silo_chapter_results:
        if cr.get("agent_ids"):
            rep_agents.append(cr["agent_ids"][0])

    if not rep_agents:
        return {
            "silo_id": silo_id,
            "silo_name": silo_name,
            "chapter_ids": chapter_ids,
            "topic_scores": {tid: 0.0 for tid in topic_ids},
            "rounds_executed": 0,
            "converged": True,
            "discussion": [],
        }

    # Build working scores from chapter results
    merged_chapter_scores = _aggregate_chapter_scores(silo_chapter_results)
    working_scores = _filter_scores_by_agents(
        topic_ids, rep_agents, merged_chapter_scores, default=SCORE_DEFAULT
    )

    # Run deliberation loop
    final_scores, rounds_executed, converged, discussion = _run_deliberation_loop(
        working_scores=working_scores,
        agent_ids=rep_agents,
        topic_ids=topic_ids,
        agent_definitions=agent_definitions,
        llm_command=llm_command,
        llm_timeout=llm_timeout,
        service_scope=service_scope,
        stages=stages,
        max_rounds=max_rounds,
        threshold=threshold,
    )

    # Aggregate to per-topic float for silo result
    topic_scores_flat: dict[str, float] = {}
    for tid, per_agent in final_scores.items():
        vals = [v for v in per_agent.values() if isinstance(v, (int, float))]
        topic_scores_flat[tid] = _compute_average(vals)

    return {
        "silo_id": silo_id,
        "silo_name": silo_name,
        "chapter_ids": chapter_ids,
        "topic_scores": topic_scores_flat,
        "rounds_executed": rounds_executed,
        "converged": converged,
        "discussion": discussion,
    }


def _build_ranked_from_scores(
    topic_ids: list[str],
    working_scores: dict[str, dict[str, float]],
) -> list[dict]:
    """Build a minimal ranked list for deliberation input."""
    ranked: list[dict] = []
    for tid in topic_ids:
        per_topic = working_scores.get(tid, {})
        vals = [v for v in per_topic.values() if isinstance(v, (int, float))]
        total = _compute_average(vals)
        ranked.append({
            "topic_id": tid,
            "topic_name": tid,
            "total_score": total,
            "features": {},
        })
    ranked.sort(key=lambda x: x["total_score"], reverse=True)
    return ranked


# ---------------------------------------------------------------------------
# LangGraph node functions
# ---------------------------------------------------------------------------

def level1_chapter_node(state: dict) -> dict:
    """Single chapter internal deliberation."""
    chapter_id = state["_chapter_id"]
    chapter_name = state["_chapter_name"]
    agent_ids = state["_agent_ids"]
    params = state.get("pipeline_params", {})
    threshold = params.get("convergence_threshold", CONVERGENCE_THRESHOLD_DEFAULT)
    max_rounds = params.get("level1_max_rounds", CONVERGENCE_LEVEL1_MAX_ROUNDS)

    result = _run_chapter_deliberation(
        chapter_id=chapter_id,
        chapter_name=chapter_name,
        agent_ids=agent_ids,
        topic_ids=state["topic_ids"],
        initial_scores=state["initial_scores"],
        agent_definitions=state["agent_definitions"],
        llm_command=state.get("llm_command", ""),
        llm_timeout=state.get("llm_timeout", LLM_DELIBERATION_TIMEOUT_SECONDS),
        service_scope=state.get("service_scope", []),
        stages=state.get("stages", []),
        max_rounds=max_rounds,
        threshold=threshold,
    )
    return {
        "chapter_results": [result],
        "execution_log": [{
            "level": 1,
            "type": "chapter",
            "chapter_id": chapter_id,
            "chapter_name": chapter_name,
            "rounds": result["rounds_executed"],
            "converged": result["converged"],
        }],
    }


def level1_clevel_node(state: dict) -> dict:
    """C-Level agents individual scoring (no deliberation at Level 1)."""
    groups = _group_agents_by_chapter(state["org_config"])
    clevel_info = groups.get("__clevel__")
    if not clevel_info:
        return {"clevel_scores": {}, "execution_log": []}

    clevel_ids = clevel_info[1]
    scores = _run_clevel_scoring(
        clevel_agent_ids=clevel_ids,
        topic_ids=state["topic_ids"],
        initial_scores=state["initial_scores"],
        agent_definitions=state["agent_definitions"],
    )
    return {
        "clevel_scores": scores,
        "execution_log": [{
            "level": 1,
            "type": "clevel",
            "agent_ids": clevel_ids,
        }],
    }


def level1_check_node(state: dict) -> dict:
    """Aggregate chapter results and check Level 1 convergence."""
    chapter_results = state.get("chapter_results", [])
    round_num = state.get("level1_round", 0) + 1
    params = state.get("pipeline_params", {})
    threshold = params.get("convergence_threshold", CONVERGENCE_THRESHOLD_DEFAULT)
    max_rounds = params.get("level1_max_rounds", CONVERGENCE_LEVEL1_MAX_ROUNDS)

    # Build aggregated scores
    merged = _aggregate_chapter_scores(chapter_results)
    curr_flat = _flatten_scores(merged)
    prev_flat = state.get("level1_prev_flat", {})

    converged = is_converged(prev_flat, curr_flat, threshold)
    complete = converged or round_num >= max_rounds

    return {
        "level1_round": round_num,
        "level1_prev_flat": curr_flat,
        "level1_complete": complete,
        "execution_log": [{
            "level": 1,
            "type": "check",
            "round": round_num,
            "converged": converged,
            "complete": complete,
        }],
    }


def level2_silo_node(state: dict) -> dict:
    """Single silo deliberation among chapter representatives."""
    silo_id = state["_silo_id"]
    silo_name = state["_silo_name"]
    chapter_ids = state["_chapter_ids"]
    params = state.get("pipeline_params", {})
    threshold = params.get("convergence_threshold", CONVERGENCE_THRESHOLD_DEFAULT)
    max_rounds = params.get("level2_max_rounds", CONVERGENCE_LEVEL2_MAX_ROUNDS)

    result = _run_silo_deliberation(
        silo_id=silo_id,
        silo_name=silo_name,
        chapter_ids=chapter_ids,
        chapter_results=state.get("chapter_results", []),
        topic_ids=state["topic_ids"],
        agent_definitions=state["agent_definitions"],
        llm_command=state.get("llm_command", ""),
        llm_timeout=state.get("llm_timeout", LLM_DELIBERATION_TIMEOUT_SECONDS),
        service_scope=state.get("service_scope", []),
        stages=state.get("stages", []),
        max_rounds=max_rounds,
        threshold=threshold,
    )
    return {
        "silo_results": [result],
        "execution_log": [{
            "level": 2,
            "type": "silo",
            "silo_id": silo_id,
            "silo_name": silo_name,
            "rounds": result["rounds_executed"],
            "converged": result["converged"],
        }],
    }


def level2_check_node(state: dict) -> dict:
    """Aggregate silo results and check Level 2 convergence."""
    silo_results = state.get("silo_results", [])
    round_num = state.get("level2_round", 0) + 1
    params = state.get("pipeline_params", {})
    threshold = params.get("convergence_threshold", CONVERGENCE_THRESHOLD_DEFAULT)
    max_rounds = params.get("level2_max_rounds", CONVERGENCE_LEVEL2_MAX_ROUNDS)

    # Build flattened scores from silo results
    curr_flat: dict[str, float] = {}
    for sr in silo_results:
        for tid, score in sr.get("topic_scores", {}).items():
            key = f"{sr['silo_id']}:{tid}"
            curr_flat[key] = float(score) if isinstance(score, (int, float)) else 0.0

    prev_flat = state.get("level2_prev_flat", {})
    converged = is_converged(prev_flat, curr_flat, threshold)
    complete = converged or round_num >= max_rounds

    return {
        "level2_round": round_num,
        "level2_prev_flat": curr_flat,
        "level2_complete": complete,
        "execution_log": [{
            "level": 2,
            "type": "check",
            "round": round_num,
            "converged": converged,
            "complete": complete,
        }],
    }


def level3_node(state: dict) -> dict:
    """C-Level + silo representatives full deliberation."""
    from .deliberation import llm_deliberation_round
    org_config = state["org_config"]
    groups = _group_agents_by_chapter(org_config)
    silo_groups = _group_chapters_by_silo(org_config)

    # Participants: C-Level agents + one representative per silo
    participants: list[str] = []
    clevel_info = groups.get("__clevel__")
    if clevel_info:
        participants.extend(clevel_info[1])

    chapter_results = state.get("chapter_results", [])
    cr_by_chapter: dict[str, dict] = {cr["chapter_id"]: cr for cr in chapter_results}

    for silo_id, (silo_name, ch_ids) in silo_groups.items():
        for ch_id in ch_ids:
            cr = cr_by_chapter.get(ch_id)
            if cr and cr.get("agent_ids"):
                participants.append(cr["agent_ids"][0])
                break

    topic_ids = state["topic_ids"]
    params = state.get("pipeline_params", {})

    # Build working scores: merge clevel_scores + silo averages
    clevel_scores = state.get("clevel_scores", {})
    silo_results = state.get("silo_results", [])

    working_scores: dict[str, dict[str, float]] = {}
    for tid in topic_ids:
        per_topic: dict[str, float] = {}
        # C-Level scores
        clevel_tid = clevel_scores.get(tid, {})
        per_topic.update(clevel_tid)
        # Silo representative scores
        for sr in silo_results:
            silo_score = sr.get("topic_scores", {}).get(tid, SCORE_DEFAULT)
            if isinstance(silo_score, (int, float)):
                # Use silo_id as pseudo-agent key
                per_topic[_agent_score_key(f"silo_{sr['silo_id']}")] = float(silo_score)
        working_scores[tid] = per_topic

    topic_catalog = _build_mock_topic_catalog(topic_ids)

    participant_defs = {k: v for k, v in state["agent_definitions"].items() if k in participants}
    ranked = _build_ranked_from_scores(topic_ids, working_scores)

    prev_decisions = state.get("decisions", [])
    score_updates, decisions, summaries, actions, meta = llm_deliberation_round(
        round_no=state.get("level3_round", 0) + 1,
        stages=state.get("stages", []),
        service_scope=state.get("service_scope", []),
        states=topic_catalog,
        working_scores=working_scores,
        ranked=ranked,
        previous_decisions=prev_decisions,
        previous_discussion=[],
        command=state.get("llm_command", ""),
        timeout=state.get("llm_timeout", LLM_DELIBERATION_TIMEOUT_SECONDS),
        agent_definitions=participant_defs,
        known_agent_ids=set(participants),
    )

    _apply_score_updates(working_scores, score_updates)

    decision_dicts = [d.to_dict() for d in decisions] if decisions else []

    return {
        "level3_scores": working_scores,
        "decisions": (prev_decisions or []) + decision_dicts,
        "execution_log": [{
            "level": 3,
            "type": "deliberation",
            "round": state.get("level3_round", 0) + 1,
            "participants": participants,
            "decisions_count": len(decisions),
        }],
    }


def level3_check_node(state: dict) -> dict:
    """Check Level 3 convergence and compute final scores."""
    round_num = state.get("level3_round", 0) + 1
    params = state.get("pipeline_params", {})
    threshold = params.get("convergence_threshold", CONVERGENCE_THRESHOLD_DEFAULT)
    max_rounds = params.get("level3_max_rounds", CONVERGENCE_LEVEL3_MAX_ROUNDS)

    level3_scores = state.get("level3_scores", {})
    curr_flat = _flatten_scores(level3_scores)
    prev_flat = state.get("level3_prev_flat", {})

    converged = is_converged(prev_flat, curr_flat, threshold)
    complete = converged or round_num >= max_rounds

    result: dict = {
        "level3_round": round_num,
        "level3_prev_flat": curr_flat,
        "level3_complete": complete,
        "execution_log": [{
            "level": 3,
            "type": "check",
            "round": round_num,
            "converged": converged,
            "complete": complete,
        }],
    }

    if complete:
        result["final_scores"] = level3_scores

    return result


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def _level1_fanout(state: dict) -> list:
    """Fan-out to chapter nodes + clevel node."""
    from langgraph.types import Send

    org_config = state["org_config"]
    groups = _group_agents_by_chapter(org_config)
    sends: list = []

    for ch_id, (ch_name, agent_ids) in groups.items():
        if ch_id == "__clevel__":
            sends.append(Send("level1_clevel", state))
        else:
            sends.append(Send("level1_chapter", {
                **state,
                "_chapter_id": ch_id,
                "_chapter_name": ch_name,
                "_agent_ids": agent_ids,
            }))
    return sends


def _route_after_level1(state: dict) -> list | str:
    """After level1_check: fan-out to level2 or re-run level1."""
    from langgraph.types import Send

    if state.get("level1_complete"):
        # Fan-out to silo nodes
        silo_groups = _group_chapters_by_silo(state["org_config"])
        sends: list = []
        for silo_id, (silo_name, ch_ids) in silo_groups.items():
            sends.append(Send("level2_silo", {
                **state,
                "_silo_id": silo_id,
                "_silo_name": silo_name,
                "_chapter_ids": ch_ids,
            }))
        if not sends:
            return "level3_node"
        return sends
    # Re-run level1 fan-out
    return _level1_fanout(state)


def _route_after_level2(state: dict) -> list | str:
    """After level2_check: go to level3 or re-run level2."""
    from langgraph.types import Send

    if state.get("level2_complete"):
        return "level3_node"

    silo_groups = _group_chapters_by_silo(state["org_config"])
    sends: list = []
    for silo_id, (silo_name, ch_ids) in silo_groups.items():
        sends.append(Send("level2_silo", {
            **state,
            "_silo_id": silo_id,
            "_silo_name": silo_name,
            "_chapter_ids": ch_ids,
        }))
    return sends if sends else "level3_node"


def _route_after_level3(state: dict) -> str:
    """After level3_check: end or re-run level3."""
    from langgraph.graph import END
    if state.get("level3_complete"):
        return END
    return "level3_node"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_convergence_graph():
    """Build and compile the 3-level convergence StateGraph."""
    from langgraph.graph import END, START, StateGraph

    builder = StateGraph(ConvergenceGraphState)

    builder.add_node("level1_chapter", level1_chapter_node)
    builder.add_node("level1_clevel", level1_clevel_node)
    builder.add_node("level1_check", level1_check_node)
    builder.add_node("level2_silo", level2_silo_node)
    builder.add_node("level2_check", level2_check_node)
    builder.add_node("level3_node", level3_node)
    builder.add_node("level3_check", level3_check_node)

    # Level 1: START → fan-out → fan-in at level1_check
    builder.add_conditional_edges(START, _level1_fanout)
    builder.add_edge("level1_chapter", "level1_check")
    builder.add_edge("level1_clevel", "level1_check")

    # Level 1 → Level 2 or re-run
    builder.add_conditional_edges("level1_check", _route_after_level1)

    # Level 2: silo nodes → level2_check
    builder.add_edge("level2_silo", "level2_check")

    # Level 2 → Level 3 or re-run
    builder.add_conditional_edges("level2_check", _route_after_level2)

    # Level 3: deliberation → check → loop or END
    builder.add_edge("level3_node", "level3_check")
    builder.add_conditional_edges("level3_check", _route_after_level3)

    return builder.compile()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_convergence_pipeline(
    org_config: dict,
    topic_states: dict[str, TopicState],
    initial_scores: dict[str, dict[str, float]],
    personas: dict[str, AgentPersona],
    agent_definitions: dict[str, dict],
    llm_command: str | None,
    llm_timeout: float,
    service_scope: list[str],
    stages: list[str],
    cancel_event: threading.Event | None = None,
    progress_callback: ProgressCallback = None,
) -> ConvergencePipelineState:
    """Run the 3-level convergence pipeline.

    Returns a ConvergencePipelineState with final_scores, decisions, and logs.
    """
    graph = build_convergence_graph()

    pipeline_params = org_config.get("pipeline_params", {})

    initial_state: dict[str, Any] = {
        "org_config": org_config,
        "topic_ids": list(topic_states.keys()),
        "initial_scores": initial_scores,
        "agent_definitions": agent_definitions or {},
        "pipeline_params": pipeline_params,
        "llm_command": llm_command or "",
        "llm_timeout": llm_timeout,
        "service_scope": service_scope,
        "stages": stages,
        # Level 1
        "chapter_results": [],
        "clevel_scores": {},
        "level1_round": 0,
        "level1_prev_flat": {},
        "level1_complete": False,
        # Level 2
        "silo_results": [],
        "level2_round": 0,
        "level2_prev_flat": {},
        "level2_complete": False,
        # Level 3
        "level3_scores": {},
        "level3_round": 0,
        "level3_prev_flat": {},
        "level3_complete": False,
        # Output
        "final_scores": {},
        "decisions": [],
        "execution_log": [],
    }

    if progress_callback:
        try:
            progress_callback("convergence", "Starting 3-level convergence pipeline")
        except Exception:
            pass

    result = graph.invoke(initial_state)

    return _to_convergence_state(result, topic_states)


def _to_convergence_state(
    result: dict,
    topic_states: dict[str, TopicState],
) -> ConvergencePipelineState:
    """Convert graph output to ConvergencePipelineState."""
    # Parse chapter results
    level1_results: list[ChapterDeliberationResult] = []
    for cr in result.get("chapter_results", []):
        level1_results.append(ChapterDeliberationResult(
            chapter_id=cr.get("chapter_id", ""),
            chapter_name=cr.get("chapter_name", ""),
            agent_ids=cr.get("agent_ids", []),
            topic_scores=cr.get("topic_scores", {}),
            rounds_executed=cr.get("rounds_executed", 0),
            converged=cr.get("converged", False),
            discussion=cr.get("discussion", []),
        ))

    # Parse silo results
    level2_results: list[SiloDeliberationResult] = []
    for sr in result.get("silo_results", []):
        level2_results.append(SiloDeliberationResult(
            silo_id=sr.get("silo_id", ""),
            silo_name=sr.get("silo_name", ""),
            chapter_ids=sr.get("chapter_ids", []),
            topic_scores=sr.get("topic_scores", {}),
            rounds_executed=sr.get("rounds_executed", 0),
            converged=sr.get("converged", False),
            discussion=sr.get("discussion", []),
        ))

    # Parse decisions with validation
    decisions: list[OrchestrationDecision] = []
    for d in result.get("decisions", []):
        if not isinstance(d, dict):
            logger.warning("Skipping non-dict decision: %s", type(d).__name__)
            continue
        # Require at least decision_id and owner
        if not d.get("decision_id") or not d.get("owner"):
            logger.warning("Skipping decision missing required fields: %s", d)
            continue
        decisions.append(OrchestrationDecision(
            decision_id=d.get("decision_id", ""),
            owner=d.get("owner", ""),
            rationale=d.get("rationale", ""),
            risk=d.get("risk", ""),
            next_action=d.get("next_action", ""),
            due=d.get("due", ""),
            topic_id=d.get("topic_id", ""),
            topic_name=d.get("topic_name", ""),
            service=d.get("service", []),
            score_delta=float(d.get("score_delta", 0.0)),
            confidence=float(d.get("confidence", 0.0)),
            fail_label=d.get("fail_label", ""),
        ))

    return ConvergencePipelineState(
        level1_results=level1_results,
        clevel_scores=result.get("clevel_scores", {}),
        level2_results=level2_results,
        level3_scores=result.get("level3_scores", {}),
        level3_rounds=result.get("level3_round", 0),
        level3_converged=result.get("level3_complete", False),
        final_scores=result.get("final_scores", {}),
        decisions=decisions,
        execution_log=result.get("execution_log", []),
    )
