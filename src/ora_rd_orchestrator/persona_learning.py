"""Dynamic persona learning via LLM analysis.

After each deliberation session, this module analyzes agent performance
and suggests persona adjustments:
- Weight rebalancing (impact, feasibility, novelty, etc.)
- Behavioral directive additions/removals
- Constraint modifications

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
    PersonaAdjustment,
    PersonaLearningResult,
    WeightAdjustment,
)

logger = logging.getLogger(__name__)

# Environment variable for persona learning LLM command
LLM_PERSONA_LEARNING_CMD_ENV = "ORA_LLM_PERSONA_LEARNING_CMD"

# Weight adjustment bounds
WEIGHT_DELTA_MIN = -0.1
WEIGHT_DELTA_MAX = 0.1
WEIGHT_VALUE_MIN = 0.0
WEIGHT_VALUE_MAX = 1.0


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to range with 4 decimal precision."""
    return round(max(lo, min(hi, value)), 4)


def _coerce_confidence(value: object, default: float = 0.5) -> float:
    """Safely parse confidence to 0.0~1.0 range."""
    try:
        return _clamp(float(value), 0.0, 1.0)
    except (TypeError, ValueError):
        return default


def compute_persona_adjustments(
    deliberation_history: list[dict],
    final_scores: dict[str, dict[str, float]],
    decisions: list[OrchestrationDecision],
    agent_definitions: dict[str, dict[str, Any]],
    current_weights: dict[str, dict[str, float]],
    current_directives: dict[str, list[str]],
    current_constraints: dict[str, list[str]],
    command: str | None = None,
    timeout: float = LLM_DELIBERATION_TIMEOUT_SECONDS,
) -> PersonaLearningResult:
    """Compute persona adjustments by analyzing deliberation outcomes via LLM.

    Args:
        deliberation_history: List of round summaries from deliberation
        final_scores: Final consensus scores {topic_id: {agent_key: score}}
        decisions: Final decisions from deliberation
        agent_definitions: Agent metadata {agent_id: {...}}
        current_weights: Current agent weights {agent_id: {weight_name: value}}
        current_directives: Current behavioral directives {agent_id: [directives]}
        current_constraints: Current constraints {agent_id: [constraints]}
        command: LLM command override (uses env var if None)
        timeout: LLM timeout in seconds

    Returns:
        PersonaLearningResult containing computed adjustments
    """
    resolved_cmd = command
    if not resolved_cmd:
        resolved_cmd = os.getenv(LLM_PERSONA_LEARNING_CMD_ENV, "").strip() or None

    # Build agent performance summary
    agent_performance: dict[str, dict[str, Any]] = {}
    for agent_id, defn in agent_definitions.items():
        agent_performance[agent_id] = {
            "role": defn.get("role", ""),
            "tier": defn.get("tier", 2),
            "current_weights": current_weights.get(agent_id, {}),
            "directives_count": len(current_directives.get(agent_id, [])),
            "constraints_count": len(current_constraints.get(agent_id, [])),
            "decisions_owned": 0,
            "avg_decision_confidence": 0.0,
            "topics_influenced": 0,
        }

    # Analyze decisions
    decision_confidences: dict[str, list[float]] = {}
    for decision in decisions:
        owner = decision.owner
        if owner in agent_performance:
            agent_performance[owner]["decisions_owned"] += 1
            decision_confidences.setdefault(owner, []).append(decision.confidence)

    # Compute average confidence per agent
    for agent_id, confidences in decision_confidences.items():
        if confidences:
            agent_performance[agent_id]["avg_decision_confidence"] = round(
                sum(confidences) / len(confidences), 4
            )

    # Count topics influenced (simplified: check presence in final_scores)
    for topic_id, scores in final_scores.items():
        for score_key in scores:
            # Extract agent_id from score_key (e.g., "researcher" from "score_researcher")
            agent_id = score_key.replace("score_", "")
            if agent_id in agent_performance:
                agent_performance[agent_id]["topics_influenced"] += 1

    # Build LLM payload
    payload = {
        "version": "persona-learning-v1",
        "instructions": {
            "task": (
                "Analyze each agent's performance in the deliberation and suggest persona adjustments. "
                "Consider: "
                "1) Weight balance: Are the agent's scoring weights aligned with their role and actual contribution? "
                "2) Behavioral patterns: Should any directives be added/removed based on observed behavior? "
                "3) Constraint effectiveness: Are current constraints helping or hindering the agent? "
                "4) Role alignment: Is the agent performing according to their designated role?"
            ),
            "output_format": (
                "Return persona_adjustments as a list of adjustments per agent. Each adjustment includes: "
                "weight_adjustments: [{weight_name, delta (-0.1 to +0.1), confidence, reason}], "
                "add_directives: [new directive strings], "
                "remove_directives: [directive strings to remove], "
                "add_constraints: [new constraint strings], "
                "remove_constraints: [constraint strings to remove], "
                "overall_assessment: brief assessment of the agent's performance"
            ),
            "constraints": (
                "Be conservative with adjustments. Only suggest changes with clear evidence. "
                "Weight deltas should be small (-0.1 to +0.1 per adjustment). "
                "Directive/constraint changes should be rare and well-justified. "
                "Weights should generally sum to approximately 1.0 across all weight types."
            ),
        },
        "output_contract": {
            "persona_adjustments": [
                {
                    "agent_id": "agent identifier",
                    "weight_adjustments": [
                        {
                            "weight_name": "impact|feasibility|novelty|risk|etc",
                            "delta": "-0.1 to +0.1",
                            "confidence": "0.0 to 1.0",
                            "reason": "why this adjustment",
                        }
                    ],
                    "add_directives": ["new directive to add"],
                    "remove_directives": ["directive to remove"],
                    "add_constraints": ["new constraint to add"],
                    "remove_constraints": ["constraint to remove"],
                    "overall_assessment": "brief performance assessment",
                    "confidence": "0.0 to 1.0",
                }
            ],
            "summary": "brief summary of persona learning analysis",
        },
        "agent_performance": agent_performance,
        "current_personas": {
            agent_id: {
                "weights": current_weights.get(agent_id, {}),
                "directives": current_directives.get(agent_id, [])[:5],  # Sample
                "constraints": current_constraints.get(agent_id, [])[:5],  # Sample
            }
            for agent_id in agent_definitions
        },
        "deliberation_summary": {
            "rounds": len(deliberation_history),
            "topics_count": len(final_scores),
            "decisions_count": len(decisions),
        },
        "decisions_sample": [
            {
                "owner": d.owner,
                "topic_id": d.topic_id,
                "risk": d.risk,
                "confidence": d.confidence,
                "rationale": d.rationale[:150] if d.rationale else "",
            }
            for d in decisions[:5]  # Sample first 5
        ],
    }

    result = run_llm_command(
        payload=payload,
        command=resolved_cmd,
        timeout=timeout,
    )

    if result.status != "ok":
        logger.warning("Persona learning LLM failed: %s", result.parsed.get("reason", "unknown"))
        return PersonaLearningResult(
            adjustments=[],
            meta={"status": result.status, "reason": result.parsed.get("reason", "llm failed")},
        )

    response = result.parsed
    adjustments: list[PersonaAdjustment] = []

    # Parse persona adjustments from LLM response
    raw_adjustments = response.get("persona_adjustments", [])
    if isinstance(raw_adjustments, list):
        seen_agents: set[str] = set()
        for item in raw_adjustments:
            if not isinstance(item, dict):
                continue

            agent_id = str(item.get("agent_id", "")).strip()

            # Validate agent exists
            if not agent_id or agent_id not in agent_definitions:
                continue
            # Deduplicate
            if agent_id in seen_agents:
                continue
            seen_agents.add(agent_id)

            # Parse weight adjustments
            weight_adjustments: list[WeightAdjustment] = []
            raw_weights = item.get("weight_adjustments", [])
            if isinstance(raw_weights, list):
                for wa in raw_weights:
                    if not isinstance(wa, dict):
                        continue
                    weight_name = str(wa.get("weight_name", "")).strip()
                    if not weight_name:
                        continue
                    try:
                        delta = _clamp(
                            float(wa.get("delta", 0.0)),
                            WEIGHT_DELTA_MIN,
                            WEIGHT_DELTA_MAX,
                        )
                    except (TypeError, ValueError):
                        delta = 0.0
                    confidence = _coerce_confidence(wa.get("confidence", 0.5), 0.5)
                    reason = str(wa.get("reason", "")).strip() or "LLM weight adjustment"

                    weight_adjustments.append(WeightAdjustment(
                        weight_name=weight_name,
                        delta=delta,
                        confidence=confidence,
                        reason=reason,
                    ))

            # Parse directives
            add_directives = _parse_string_list(item.get("add_directives", []))
            remove_directives = _parse_string_list(item.get("remove_directives", []))

            # Parse constraints
            add_constraints = _parse_string_list(item.get("add_constraints", []))
            remove_constraints = _parse_string_list(item.get("remove_constraints", []))

            overall_assessment = str(item.get("overall_assessment", "")).strip()
            confidence = _coerce_confidence(item.get("confidence", 0.5), 0.5)

            adjustments.append(PersonaAdjustment(
                agent_id=agent_id,
                weight_adjustments=weight_adjustments,
                add_directives=add_directives,
                remove_directives=remove_directives,
                add_constraints=add_constraints,
                remove_constraints=remove_constraints,
                overall_assessment=overall_assessment,
                confidence=confidence,
            ))

    return PersonaLearningResult(
        adjustments=adjustments,
        meta={
            "status": "ok",
            "summary": response.get("summary", ""),
            "adjustments_count": len(adjustments),
        },
    )


def _parse_string_list(value: Any) -> list[str]:
    """Parse a value into a list of non-empty strings."""
    if not isinstance(value, list):
        return []
    return [str(s).strip() for s in value if s and str(s).strip()]


def merge_persona_adjustments(
    base_weights: dict[str, dict[str, float]],
    base_directives: dict[str, list[str]],
    base_constraints: dict[str, list[str]],
    learning_result: PersonaLearningResult,
    min_weight: float = WEIGHT_VALUE_MIN,
    max_weight: float = WEIGHT_VALUE_MAX,
    decay_factor: float = 0.9,
) -> tuple[dict[str, dict[str, float]], dict[str, list[str]], dict[str, list[str]]]:
    """Merge learned adjustments into base personas.

    Creates new dicts (does not modify inputs).

    Args:
        base_weights: Original weights {agent_id: {weight_name: value}}
        base_directives: Original directives {agent_id: [directives]}
        base_constraints: Original constraints {agent_id: [constraints]}
        learning_result: Persona learning result
        min_weight: Minimum weight value
        max_weight: Maximum weight value
        decay_factor: Dampening for weight adjustments

    Returns:
        Tuple of (merged_weights, merged_directives, merged_constraints)
    """
    # Deep copy bases
    merged_weights = {agent: dict(weights) for agent, weights in base_weights.items()}
    merged_directives = {agent: list(dirs) for agent, dirs in base_directives.items()}
    merged_constraints = {agent: list(cons) for agent, cons in base_constraints.items()}

    # Apply weight adjustments
    learning_result.apply_to_weights(
        merged_weights,
        min_weight=min_weight,
        max_weight=max_weight,
        decay_factor=decay_factor,
    )

    # Apply directive changes
    for adj in learning_result.adjustments:
        agent_id = adj.agent_id

        # Ensure agent has entries
        if agent_id not in merged_directives:
            merged_directives[agent_id] = []
        if agent_id not in merged_constraints:
            merged_constraints[agent_id] = []

        # Add new directives (avoid duplicates)
        for directive in adj.add_directives:
            if directive not in merged_directives[agent_id]:
                merged_directives[agent_id].append(directive)

        # Remove directives
        for directive in adj.remove_directives:
            if directive in merged_directives[agent_id]:
                merged_directives[agent_id].remove(directive)

        # Add new constraints (avoid duplicates)
        for constraint in adj.add_constraints:
            if constraint not in merged_constraints[agent_id]:
                merged_constraints[agent_id].append(constraint)

        # Remove constraints
        for constraint in adj.remove_constraints:
            if constraint in merged_constraints[agent_id]:
                merged_constraints[agent_id].remove(constraint)

    return merged_weights, merged_directives, merged_constraints
