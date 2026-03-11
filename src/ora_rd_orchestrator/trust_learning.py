"""Dynamic trust_map learning via LLM analysis.

After each deliberation session, this module analyzes agent contributions
and updates trust relationships based on:
- Score prediction accuracy (did agent's scores align with final consensus?)
- Argument quality (were rationales well-reasoned?)
- Collaboration patterns (did agents build on each other's insights?)

All logic is LLM-driven. No hardcoded rules.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from .config import LLM_DELIBERATION_TIMEOUT_SECONDS
from .llm_client import run_llm_command
from .types import (
    OrchestrationDecision,
    ScoreAdjustment,
    TrustLearningResult,
    TrustUpdate,
)

logger = logging.getLogger(__name__)

# Environment variable for trust learning LLM command
LLM_TRUST_LEARNING_CMD_ENV = "ORA_LLM_TRUST_LEARNING_CMD"

# Trust update bounds
TRUST_DELTA_MIN = -0.2
TRUST_DELTA_MAX = 0.2
TRUST_VALUE_MIN = 0.1
TRUST_VALUE_MAX = 1.0


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to range with 4 decimal precision."""
    return round(max(lo, min(hi, value)), 4)


def _coerce_confidence(value: object, default: float = 0.5) -> float:
    """Safely parse confidence to 0.0~1.0 range."""
    try:
        return _clamp(float(value), 0.0, 1.0)
    except (TypeError, ValueError):
        return default


def compute_trust_updates(
    deliberation_history: list[dict],
    score_adjustments: dict[str, dict[str, ScoreAdjustment | float]],
    final_scores: dict[str, dict[str, float]],
    decisions: list[OrchestrationDecision],
    agent_definitions: dict[str, dict[str, Any]],
    current_trust_map: dict[str, dict[str, float]],
    command: str | None = None,
    timeout: float = LLM_DELIBERATION_TIMEOUT_SECONDS,
) -> TrustLearningResult:
    """Compute trust updates by analyzing deliberation outcomes via LLM.

    Args:
        deliberation_history: List of round summaries from deliberation
        score_adjustments: Score changes made during deliberation
        final_scores: Final consensus scores {topic_id: {agent_key: score}}
        decisions: Final decisions from deliberation
        agent_definitions: Agent metadata {agent_id: {...}}
        current_trust_map: Current trust relationships {agent_id: {other_id: trust}}
        command: LLM command override (uses env var if None)
        timeout: LLM timeout in seconds

    Returns:
        TrustLearningResult containing computed trust updates
    """
    resolved_cmd = command
    if not resolved_cmd:
        resolved_cmd = os.getenv(LLM_TRUST_LEARNING_CMD_ENV, "").strip() or None

    # Build agent participation summary
    agent_contributions: dict[str, dict[str, Any]] = {}
    for agent_id in agent_definitions:
        agent_contributions[agent_id] = {
            "topics_scored": 0,
            "avg_confidence": 0.0,
            "total_delta": 0.0,
            "decisions_owned": 0,
        }

    # Analyze score adjustments
    confidence_sum: dict[str, float] = {}
    confidence_count: dict[str, int] = {}
    for topic_id, per_agent in score_adjustments.items():
        for agent_name, adjustment in per_agent.items():
            agent_key = agent_name.replace("score_", "")
            if agent_key not in agent_contributions:
                continue
            agent_contributions[agent_key]["topics_scored"] += 1
            if isinstance(adjustment, ScoreAdjustment):
                agent_contributions[agent_key]["total_delta"] += abs(adjustment.delta)
                confidence_sum[agent_key] = confidence_sum.get(agent_key, 0.0) + adjustment.confidence
                confidence_count[agent_key] = confidence_count.get(agent_key, 0) + 1
            else:
                agent_contributions[agent_key]["total_delta"] += abs(float(adjustment))

    # Compute average confidence per agent
    for agent_key in confidence_sum:
        if confidence_count.get(agent_key, 0) > 0:
            agent_contributions[agent_key]["avg_confidence"] = round(
                confidence_sum[agent_key] / confidence_count[agent_key], 4
            )

    # Count decisions owned
    for decision in decisions:
        owner = decision.owner
        if owner in agent_contributions:
            agent_contributions[owner]["decisions_owned"] += 1

    # Build LLM payload
    payload = {
        "version": "trust-learning-v1",
        "instructions": {
            "task": (
                "Analyze the deliberation outcomes and determine how trust between agents "
                "should be updated. Consider: "
                "1) Score alignment: Did an agent's scores align with final consensus? "
                "2) Argument quality: Were their rationales well-reasoned and supported by evidence? "
                "3) Collaboration: Did they build constructively on others' insights? "
                "4) Domain expertise: Did they contribute unique domain knowledge?"
            ),
            "output_format": (
                "Return trust_updates as a list of {source_agent, target_agent, delta, confidence, reason}. "
                "delta: -0.2 to +0.2 (negative = less trust, positive = more trust). "
                "confidence: 0.0 to 1.0 (how certain you are about this update). "
                "Only include updates where there's meaningful signal (avoid noise)."
            ),
            "constraints": (
                "Be conservative with trust changes. Large swings (>0.1) require strong evidence. "
                "Agents should not rate themselves. "
                "Consider the current trust relationships when proposing changes."
            ),
        },
        "output_contract": {
            "trust_updates": [
                {
                    "source_agent": "agent who is updating their trust",
                    "target_agent": "agent being evaluated",
                    "delta": "-0.2 to +0.2",
                    "confidence": "0.0 to 1.0",
                    "reason": "explanation for this trust change",
                    "evidence_topic_ids": ["topic_ids that informed this"],
                }
            ],
            "summary": "brief summary of trust dynamics observed",
        },
        "current_trust_map": current_trust_map,
        "agent_contributions": agent_contributions,
        "agent_definitions": {
            agent_id: {
                "role": defn.get("role", ""),
                "tier": defn.get("tier", 2),
                "team": defn.get("team", ""),
                "weights": defn.get("weights", {}),
            }
            for agent_id, defn in agent_definitions.items()
        },
        "deliberation_summary": {
            "rounds": len(deliberation_history),
            "topics_discussed": list(final_scores.keys())[:10],
            "decisions_made": len(decisions),
        },
        "final_scores_sample": {
            tid: scores
            for i, (tid, scores) in enumerate(final_scores.items())
            if i < 5  # Sample first 5 topics
        },
        "decisions_sample": [
            {
                "owner": d.owner,
                "topic_id": d.topic_id,
                "risk": d.risk,
                "confidence": d.confidence,
                "rationale": d.rationale[:200] if d.rationale else "",
            }
            for d in decisions[:5]  # Sample first 5 decisions
        ],
    }

    result = run_llm_command(
        payload=payload,
        command=resolved_cmd,
        timeout=timeout,
    )

    if result.status != "ok":
        logger.warning("Trust learning LLM failed: %s", result.parsed.get("reason", "unknown"))
        return TrustLearningResult(
            updates=[],
            meta={"status": result.status, "reason": result.parsed.get("reason", "llm failed")},
        )

    response = result.parsed
    updates: list[TrustUpdate] = []

    # Parse trust updates from LLM response
    raw_updates = response.get("trust_updates", [])
    if isinstance(raw_updates, list):
        seen_pairs: set[tuple[str, str]] = set()
        for item in raw_updates:
            if not isinstance(item, dict):
                continue

            source = str(item.get("source_agent", "")).strip()
            target = str(item.get("target_agent", "")).strip()

            # Validate agents exist
            if not source or not target:
                continue
            if source not in agent_definitions or target not in agent_definitions:
                continue
            # No self-rating
            if source == target:
                continue
            # Deduplicate
            pair = (source, target)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            # Parse and clamp values
            try:
                delta = _clamp(float(item.get("delta", 0.0)), TRUST_DELTA_MIN, TRUST_DELTA_MAX)
            except (TypeError, ValueError):
                delta = 0.0

            confidence = _coerce_confidence(item.get("confidence", 0.5), 0.5)
            reason = str(item.get("reason", "")).strip() or "LLM trust update"
            evidence = item.get("evidence_topic_ids", [])
            if not isinstance(evidence, list):
                evidence = []

            updates.append(TrustUpdate(
                source_agent=source,
                target_agent=target,
                delta=delta,
                confidence=confidence,
                reason=reason,
                evidence_topic_ids=[str(e) for e in evidence if e],
            ))

    return TrustLearningResult(
        updates=updates,
        meta={
            "status": "ok",
            "summary": response.get("summary", ""),
            "updates_count": len(updates),
        },
    )


def merge_trust_maps(
    base_trust_map: dict[str, dict[str, float]],
    learning_result: TrustLearningResult,
    min_trust: float = TRUST_VALUE_MIN,
    max_trust: float = TRUST_VALUE_MAX,
    decay_factor: float = 0.9,
) -> dict[str, dict[str, float]]:
    """Merge learned trust updates into base trust map.

    Creates a new dict (does not modify base_trust_map).

    Args:
        base_trust_map: Original trust relationships
        learning_result: Trust learning result with updates
        min_trust: Minimum allowed trust value
        max_trust: Maximum allowed trust value
        decay_factor: Dampening factor for updates (0.9 = 90% of proposed change)

    Returns:
        New trust map with updates applied
    """
    # Deep copy base
    merged: dict[str, dict[str, float]] = {
        agent: dict(targets) for agent, targets in base_trust_map.items()
    }

    # Apply updates
    return learning_result.apply_to_trust_map(
        merged,
        min_trust=min_trust,
        max_trust=max_trust,
        decay_factor=decay_factor,
    )
