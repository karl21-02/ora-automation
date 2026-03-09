"""LLM-based final consensus for R&D topic selection.

All consensus decisions are made by LLM. No hardcoded gates or rules.
"""
from __future__ import annotations

import datetime as dt
import logging
from difflib import SequenceMatcher
from typing import Any

from .config import (
    CONSENSUS_FUZZY_MATCH_THRESHOLD,
    LLM_CONSENSUS_CMD_ENV,
    LLM_CONSENSUS_TIMEOUT_SECONDS,
)
from .llm_client import run_llm_command
from .types import TopicState

logger = logging.getLogger(__name__)


def _build_llm_consensus_payload(
    ranked: list[dict],
    states: dict[str, TopicState],
    agent_rankings: dict[str, list[str]],
    discussion: list[dict] | None,
    top_k: int,
    agent_definitions: dict[str, dict[str, Any]] | None = None,
    deliberation_risk_summary: list[dict] | None = None,
) -> dict:
    _defs = agent_definitions or {}
    # Pre-build rank index: O(A*R) once instead of O(top_k*A*R) with list.index()
    _rank_index: dict[str, dict[str, int]] = {
        agent: {tid: idx + 1 for idx, tid in enumerate(ranks)}
        for agent, ranks in agent_rankings.items()
    }
    return {
        "version": "llm-consensus-v2",
        "top_k": top_k,
        "output_contract": {
            "final_consensus": "ordered topic_id list length<=top_k",
            "rationale": "string",
            "concerns": [{"topic_id": "id", "reason": "string"}],
        },
        "agent_rules": {
            agent: {
                "objective": _defs.get(agent, {}).get("objective", ""),
                "decision_focus": _defs.get(agent, {}).get("decision_focus", []),
            }
            for agent in _defs
        },
        "discussion": discussion or [],
        "topics": [
            {
                "topic_id": item["topic_id"],
                "topic_name": item["topic_name"],
                "scores": item,
                "evidence_count": len(states[item["topic_id"]].evidence),
                "project_count": states[item["topic_id"]].project_count,
                "risk_penalty": item.get("features", {}).get("risk_penalty", 0),
                "feature": item.get("features", {}),
                "agent_signals": {
                    "agent_rankings": {
                        agent: _rank_index[agent].get(item["topic_id"])
                        for agent in agent_rankings
                    }
                },
            }
            for item in ranked[:top_k]
            if item["topic_id"] in states
        ],
        "deliberation_risk_summary": deliberation_risk_summary or [],
        "meta": {
            "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "topic_count": len(ranked),
        },
    }


def apply_hybrid_consensus(
    ranked: list[dict],
    states: dict[str, TopicState],
    scores: dict[str, dict[str, float]],
    agent_rankings: dict[str, list[str]],
    discussion: list[dict] | None,
    top_k: int,
    command: str | None = None,
    timeout: float = LLM_CONSENSUS_TIMEOUT_SECONDS,
    agent_definitions: dict[str, dict[str, Any]] | None = None,
    deliberation_risk_summary: list[dict] | None = None,
) -> dict:
    """Apply LLM-based consensus. No hardcoded gates."""
    target_size = min(top_k, len(ranked))
    payload = _build_llm_consensus_payload(
        ranked, states, agent_rankings, discussion, target_size,
        agent_definitions=agent_definitions,
        deliberation_risk_summary=deliberation_risk_summary,
    )

    result = run_llm_command(
        payload=payload,
        command=command,
        timeout=timeout,
        env_var=LLM_CONSENSUS_CMD_ENV,
    )

    if result.status != "ok":
        return {
            "method": "llm-only",
            "status": "failed",
            "reason": result.parsed.get("reason", "llm consensus failed"),
            "final_consensus_ids": [],
            "final_rationale": "",
            "llm": {"status": result.status, **result.parsed},
            "llm_raw_output": result.raw_output[:1200] if result.raw_output else "",
            "concerns": [],
            "vetoed": [],
            "gating": [],
            "payload": payload,
            "target_size": target_size,
            "requested_top_k": top_k,
        }

    llm_result = result.parsed
    candidate = llm_result.get("final_consensus", llm_result.get("consensus", []))

    # Build fuzzy matching index for topic IDs
    _valid_ids = set(states.keys())
    _norm_to_id: dict[str, str] = {}
    for tid in _valid_ids:
        _norm_to_id[tid.lower().replace("-", "_").replace(" ", "_")] = tid

    def _resolve_topic_id(raw_id: str) -> str | None:
        """Resolve a topic ID with exact match first, then normalized, then fuzzy."""
        if raw_id in _valid_ids:
            return raw_id
        normed = raw_id.lower().replace("-", "_").replace(" ", "_")
        if normed in _norm_to_id:
            return _norm_to_id[normed]
        # Fuzzy match as last resort
        best_match, best_score = "", 0.0
        for norm_key, real_id in _norm_to_id.items():
            score = SequenceMatcher(None, normed, norm_key).ratio()
            if score > best_score:
                best_score = score
                best_match = real_id
        if best_score >= CONSENSUS_FUZZY_MATCH_THRESHOLD:
            logger.info("Fuzzy-matched consensus topic ID '%s' → '%s' (%.2f)", raw_id, best_match, best_score)
            return best_match
        return None

    final_consensus: list[str] = []
    if isinstance(candidate, list):
        for topic_id in candidate:
            if not isinstance(topic_id, str):
                continue
            resolved = _resolve_topic_id(topic_id)
            if resolved is None:
                logger.warning("Consensus topic ID '%s' not found (no fuzzy match)", topic_id)
                continue
            if resolved in final_consensus:
                continue
            final_consensus.append(resolved)
            if len(final_consensus) >= target_size:
                break

    concerns: list[dict[str, str]] = []
    concerns_raw = llm_result.get("concerns", [])
    if isinstance(concerns_raw, list):
        for item in concerns_raw:
            if isinstance(item, str):
                concerns.append({"topic_id": item, "reason": "llm concern"})
            elif isinstance(item, dict) and isinstance(item.get("topic_id"), str):
                concerns.append(
                    {
                        "topic_id": item["topic_id"],
                        "reason": str(item.get("reason", "")).strip() or "llm concern",
                    }
                )

    return {
        "method": "llm-only",
        "status": "ok",
        "final_consensus_ids": final_consensus,
        "final_rationale": str(llm_result.get("rationale", "")).strip() or "llm consensus",
        "llm": llm_result,
        "llm_raw_output": result.raw_output[:1200] if result.raw_output else "",
        "concerns": concerns,
        "vetoed": [],
        "gating": [],
        "payload": payload,
        "target_size": target_size,
        "requested_top_k": top_k,
    }
