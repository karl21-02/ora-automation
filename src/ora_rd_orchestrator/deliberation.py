"""Multi-round deliberation between agents.

All deliberation is performed via LLM calls. No hardcoded rules.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from .config import (
    LLM_DELIBERATION_CMD_ENV,
    LLM_DELIBERATION_FAIL_LABEL_HIGH_RISK,
    LLM_DELIBERATION_FAIL_LABEL_LOW_RISK,
    LLM_DELIBERATION_FAIL_LABEL_MEDIUM_RISK,
    LLM_DELIBERATION_TIMEOUT_SECONDS,
    PIPELINE_FAIL_LABEL_RETRY,
    PIPELINE_FAIL_LABEL_SKIP,
    PIPELINE_FAIL_LABEL_STOP,
    RISK_THRESHOLD_HIGH,
    RISK_THRESHOLD_MEDIUM,
    _normalize_services,
)
from .llm_client import run_llm_command
from .types import OrchestrationDecision, ScoreAdjustment, TopicState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from .utils import clamp_score


def _clamp_score(value: float, lo: float = 0.0, hi: float = 10.0) -> float:
    """Clamp score with 4 decimal precision for deliberation."""
    return clamp_score(value, lo, hi, decimals=4)


# ---------------------------------------------------------------------------
# LLM deliberation round helpers
# ---------------------------------------------------------------------------

def _to_risk_label(value: float) -> str:
    if value >= RISK_THRESHOLD_HIGH:
        return "high"
    if value >= RISK_THRESHOLD_MEDIUM:
        return "medium"
    return "low"


def _normalize_fail_label(value: object) -> str:
    label = str(value).strip().upper().replace(" ", "_")
    if label in {PIPELINE_FAIL_LABEL_SKIP, PIPELINE_FAIL_LABEL_RETRY, PIPELINE_FAIL_LABEL_STOP}:
        return label
    return ""


def _coerce_fail_label(risk_label: str, risk_score: float, confidence: float) -> str:
    """Map risk label to fail label. Uses label string from LLM, not thresholds."""
    label_map = {
        "high": LLM_DELIBERATION_FAIL_LABEL_HIGH_RISK,
        "medium": LLM_DELIBERATION_FAIL_LABEL_MEDIUM_RISK,
        "low": LLM_DELIBERATION_FAIL_LABEL_LOW_RISK,
    }
    return label_map.get(risk_label, LLM_DELIBERATION_FAIL_LABEL_LOW_RISK)


def _coerce_confidence(value: object, default: float = 0.5) -> float:
    try:
        return _clamp_score(float(value), 0.0, 1.0)
    except (TypeError, ValueError):
        return default


def _to_decision_due() -> str:
    import datetime as dt
    from .config import DECISION_DUE_DEFAULT_DAYS
    return (dt.date.today() + dt.timedelta(days=DECISION_DUE_DEFAULT_DAYS)).isoformat()


def parse_llm_decision_record(
    item: dict,
    topic_catalog: dict[str, TopicState],
    service_scope: list[str],
    known_agent_ids: set[str] | None = None,
) -> OrchestrationDecision:
    """Parse a single LLM decision record into an OrchestrationDecision."""
    topic_id = str(item.get("topic_id", "")).strip()
    if topic_id not in topic_catalog:
        topic_id = next(iter(topic_catalog), "")
    state = topic_catalog.get(topic_id)
    topic_name = state.topic_name if state else topic_id
    score_delta = float(item.get("score_delta", item.get("delta", 0.0) or 0.0))
    risk_score = float(item.get("risk_score", item.get("risk", 0.0) or 0.0))
    risk_label = item.get("risk", "")
    if isinstance(risk_label, (int, float)):
        risk_label = _to_risk_label(float(risk_label))
    elif isinstance(risk_label, str):
        risk_label = risk_label.strip().lower() or _to_risk_label(risk_score)
    else:
        risk_label = _to_risk_label(risk_score)

    owner = str(item.get("owner", "")).strip() or "Researcher"
    if known_agent_ids and owner not in known_agent_ids:
        owner = "Researcher"

    target_services_raw = item.get("service", [])
    if isinstance(target_services_raw, str):
        target_services = _normalize_services(target_services_raw.split(","))
    elif isinstance(target_services_raw, (list, tuple, set)):
        target_services = _normalize_services(target_services_raw)
    else:
        target_services = list(service_scope) if service_scope else []
    if not target_services:
        target_services = list(service_scope) if service_scope else ["global"]

    rationale = str(item.get("rationale", "")).strip()
    if not rationale:
        rationale = "LLM 근거 메시지가 누락되어 보수적으로 처리"
    next_action = str(item.get("next_action", "")).strip() or "추가 근거 정리 후 1차 PoC 범위 확정"
    due = str(item.get("due", "")).strip()
    if not due:
        due = _to_decision_due()

    fail_label = _normalize_fail_label(item.get("fail_label", ""))
    if not fail_label:
        fail_label = _coerce_fail_label(
            risk_label=risk_label,
            risk_score=risk_score,
            confidence=_coerce_confidence(item.get("confidence", 0.5), 0.5),
        )

    return OrchestrationDecision(
        decision_id=str(item.get("decision_id", f"decision-{uuid.uuid4()}")),
        owner=owner,
        rationale=rationale,
        risk=risk_label,
        next_action=next_action,
        due=due,
        topic_id=topic_id,
        topic_name=topic_name,
        service=target_services,
        score_delta=_clamp_score(score_delta, -5.0, 5.0),
        confidence=_coerce_confidence(item.get("confidence", 0.5), 0.5),
        fail_label=fail_label,
    )


def llm_deliberation_round(
    round_no: int,
    stages: list[str],
    service_scope: list[str],
    states: dict[str, TopicState],
    working_scores: dict[str, dict[str, float]],
    ranked: list[dict],
    previous_decisions: list[dict],
    previous_discussion: list[dict],
    command: str | None = None,
    timeout: float = LLM_DELIBERATION_TIMEOUT_SECONDS,
    agent_definitions: dict[str, dict[str, Any]] | None = None,
    known_agent_ids: set[str] | None = None,
) -> tuple[dict[str, dict[str, ScoreAdjustment]], list[OrchestrationDecision], list[dict], list[dict], dict]:
    """Execute a single LLM deliberation round.

    Returns (score_adjustments, decisions, round_summaries, action_log, meta).
    """
    resolved_cmd = command
    if not resolved_cmd:
        resolved_cmd = os.getenv(LLM_DELIBERATION_CMD_ENV, "").strip() or None

    _defs = agent_definitions or {}
    payload = {
        "version": "llm-deliberation-v2",
        "instructions": {
            "confidence_guide": (
                "Each score adjustment MUST include a confidence value (0.0~1.0). "
                "confidence reflects how certain the agent is about the adjustment: "
                "0.9+ = very high certainty (strong evidence, clear rationale), "
                "0.7~0.9 = high certainty (good evidence, solid reasoning), "
                "0.5~0.7 = moderate certainty (some evidence, reasonable inference), "
                "0.3~0.5 = low certainty (limited evidence, speculative), "
                "0.0~0.3 = very low certainty (no evidence, pure guess). "
                "Higher confidence adjustments will have more weight in final scoring."
            ),
            "scoring_rules": (
                "Adjustments are weighted by confidence when aggregating across agents. "
                "A +2.0 adjustment with 0.9 confidence has more impact than +2.0 with 0.3 confidence. "
                "Be honest about uncertainty - overconfident scores reduce overall system reliability."
            ),
        },
        "output_contract": {
            "score_adjustments": "topic_id -> {agent_name_or_key: {delta: -3.0~3.0, confidence: 0.0~1.0}}",
            "decisions": [
                {
                    "decision_id": "string",
                    "owner": "agent name",
                    "topic_id": "topic id",
                    "rationale": "why",
                    "risk": "low|medium|high",
                    "next_action": "action",
                    "due": "YYYY-MM-DD",
                    "service": ["b2b", "b2c"],
                    "score_delta": "float",
                    "confidence": "0~1",
                    "fail_label": "SKIP|RETRY|STOP",
                }
            ],
            "action_log": "optional list",
        },
        "round": round_no,
        "stages": stages,
        "service_scope": service_scope,
        "agent_rules": {
            agent: {
                "objective": _defs.get(agent, {}).get("objective", ""),
                "decision_focus": _defs.get(agent, {}).get("decision_focus", []),
                "weights": _defs.get(agent, {}).get("weights", {}),
            }
            for agent in _defs
        },
        "topics": [
            {
                "topic_id": item["topic_id"],
                "topic_name": item["topic_name"],
                "scores": item,
                "feature": item["features"],
                "evidence_count": len(states[item["topic_id"]].evidence),
                "project_hits": states[item["topic_id"]].project_hits,
            }
            for item in ranked[:min(8, len(ranked))]
            if item["topic_id"] in states
        ],
        "score_matrix": {
            tid: working_scores[tid]
            for item in ranked[:min(8, len(ranked))]
            if (tid := item["topic_id"]) in working_scores
        },
        "topic_states": {
            tid: {
                "features": states[tid].compute_features(),
                "keyword_hits": states[tid].keyword_hits,
                "business_hits": states[tid].business_hits,
                "novelty_hits": states[tid].novelty_hits,
                "code_hits": states[tid].code_hits,
                "doc_hits": states[tid].doc_hits,
                "history_hits": states[tid].history_hits,
                "projects": sorted(states[tid].project_hits.keys()),
            }
            for item in ranked[:min(8, len(ranked))]
            if (tid := item["topic_id"]) in states
        },
        "previous_decisions": previous_decisions or [],
        "previous_discussion": previous_discussion or [],
    }

    result = run_llm_command(
        payload=payload,
        command=resolved_cmd,
        timeout=timeout,
    )

    _agent_ids = known_agent_ids or set(_defs.keys())
    score_adjustments: dict[str, dict[str, ScoreAdjustment]] = {topic_id: {} for topic_id in states}
    action_log: list[dict] = []
    parsed_decisions: list[OrchestrationDecision] = []

    if result.status != "ok":
        meta = {"status": result.status, "reason": result.parsed.get("reason", "llm 실행 실패")}
        if isinstance(result.parsed, dict):
            stderr_value = result.parsed.get("stderr")
            if stderr_value:
                meta["stderr"] = str(stderr_value)
        return score_adjustments, parsed_decisions, [], action_log, meta

    response = result.parsed

    # Parse score adjustments (supports both v1 and v2 formats)
    updates = response.get("score_adjustments")
    if isinstance(updates, dict):
        for topic_id, per_agent in updates.items():
            if topic_id not in score_adjustments:
                continue
            if not isinstance(per_agent, dict):
                continue
            for agent, value in per_agent.items():
                agent_clean = agent.replace("score_", "")
                if agent_clean not in _agent_ids and agent not in _agent_ids:
                    continue
                # Parse both formats:
                # v1: {"agent": 1.5}
                # v2: {"agent": {"delta": 1.5, "confidence": 0.9}}
                if isinstance(value, dict):
                    # v2 format with confidence
                    try:
                        parsed_delta = _clamp_score(float(value.get("delta", 0.0)), -3.0, 3.0)
                        parsed_confidence = _coerce_confidence(value.get("confidence", 0.5), 0.5)
                    except (TypeError, ValueError):
                        continue
                else:
                    # v1 format (just float delta, default confidence)
                    try:
                        parsed_delta = _clamp_score(float(value), -3.0, 3.0)
                        parsed_confidence = 0.5  # default mid confidence for v1
                    except (TypeError, ValueError):
                        continue
                score_adjustments[topic_id][agent_clean] = ScoreAdjustment(
                    delta=parsed_delta,
                    confidence=parsed_confidence,
                )

    # Parse decisions
    decision_items = response.get("decisions")
    if isinstance(decision_items, list):
        _seen_decision_topics: set[str] = set()
        for item in decision_items:
            if not isinstance(item, dict):
                continue
            parsed = parse_llm_decision_record(item, states, service_scope, _agent_ids)
            if parsed.topic_id not in _seen_decision_topics:
                _seen_decision_topics.add(parsed.topic_id)
                parsed_decisions.append(parsed)

    if isinstance(response.get("action_log"), list):
        action_log = [entry for entry in response.get("action_log") if isinstance(entry, dict)]

    round_summary = response.get("round_summary", {"round": round_no, "agent": "llm"})
    meta = {"status": "ok", "result": response}

    return score_adjustments, parsed_decisions, [round_summary] if round_summary else [], action_log, meta
