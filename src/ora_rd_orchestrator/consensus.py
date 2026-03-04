"""LLM-based final consensus for R&D topic selection.

All consensus decisions are made by LLM. No hardcoded gates or rules.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from .config import (
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
) -> dict:
    _defs = agent_definitions or {}
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
                        agent: ranks.index(item["topic_id"]) + 1
                        if item["topic_id"] in ranks
                        else None
                        for agent, ranks in agent_rankings.items()
                    }
                },
            }
            for item in ranked[:top_k]
            if item["topic_id"] in states
        ],
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
) -> dict:
    """Apply LLM-based consensus. No hardcoded gates."""
    target_size = min(top_k, len(ranked))
    payload = _build_llm_consensus_payload(
        ranked, states, agent_rankings, discussion, target_size,
        agent_definitions=agent_definitions,
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
    final_consensus: list[str] = []
    if isinstance(candidate, list):
        for topic_id in candidate:
            if not isinstance(topic_id, str):
                continue
            if topic_id in final_consensus:
                continue
            if topic_id not in states:
                continue
            final_consensus.append(topic_id)
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
