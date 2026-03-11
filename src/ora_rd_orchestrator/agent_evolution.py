"""Agent Evolution module - Toss Style.

Implements fast feedback loops and automatic evolution with safety guardrails.
No hardcoded rules - all decisions made by LLM.

Key principles:
1. Immediate feedback (no 3-month wait)
2. Auto-apply small changes, flag large ones
3. Always rollback-capable
4. Silo autonomy respected
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

from .config import LLM_DELIBERATION_TIMEOUT_SECONDS
from .llm_client import run_llm_command
from .types import (
    AgentPersona,
    AgentSnapshot,
    ConvergencePipelineState,
    EvolutionProposal,
    EvolutionResult,
    EvolutionSignal,
    OrchestrationDecision,
)

logger = logging.getLogger(__name__)

# Environment variable for evolution LLM command
LLM_EVOLUTION_CMD_ENV = "ORA_LLM_EVOLUTION_CMD"

# Thresholds for change magnitude (Toss style: small = auto, large = review)
MAGNITUDE_MICRO_THRESHOLD = 0.05   # Auto-apply silently
MAGNITUDE_SMALL_THRESHOLD = 0.15  # Auto-apply with logging
# >= 0.15 is "large" - flag for review


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to range."""
    return round(max(lo, min(hi, value)), 4)


def _classify_magnitude(delta: float) -> tuple[str, bool]:
    """Classify change magnitude and whether to auto-apply.

    Toss style:
    - micro (<0.05): Auto-apply silently
    - small (<0.15): Auto-apply with monitoring
    - large (>=0.15): Flag for review
    """
    abs_delta = abs(delta)
    if abs_delta < MAGNITUDE_MICRO_THRESHOLD:
        return "micro", True
    elif abs_delta < MAGNITUDE_SMALL_THRESHOLD:
        return "small", True
    else:
        return "large", False


# ---------------------------------------------------------------------------
# Signal Collection (E-2)
# ---------------------------------------------------------------------------

def compute_evolution_signals(
    convergence_state: ConvergencePipelineState,
    agent_definitions: dict[str, dict],
    personas: dict[str, AgentPersona],
    historical_performance: dict[str, list[dict]] | None = None,
) -> list[EvolutionSignal]:
    """Compute evolution signals from a completed orchestration.

    Toss style: Immediate feedback after each run.

    Signal types:
    - score_accuracy: How close agent's scores were to final consensus
    - consensus_contribution: How much agent helped reach consensus
    - argument_quality: Quality of arguments in structured debate
    - convergence_speed: How quickly agent's positions converged

    Args:
        convergence_state: Result of convergence pipeline
        agent_definitions: Current agent definitions
        personas: Current agent personas
        historical_performance: Previous signals per agent (for baseline)

    Returns:
        List of EvolutionSignal for this run
    """
    signals: list[EvolutionSignal] = []

    # Extract final scores for baseline comparison
    final_scores = convergence_state.final_scores

    # 1. Score accuracy signals - how close to final consensus
    for level1_result in convergence_state.level1_results:
        for agent_id in level1_result.agent_ids:
            agent_topic_scores = level1_result.topic_scores
            for topic_id, topic_final in final_scores.items():
                if topic_id not in agent_topic_scores:
                    continue

                agent_scores = agent_topic_scores[topic_id]
                if not isinstance(agent_scores, dict):
                    continue

                # Find agent's score
                agent_key = f"score_{agent_id.lower()}"
                if agent_key not in agent_scores:
                    agent_key = agent_id.lower()
                if agent_key not in agent_scores:
                    continue

                agent_score = agent_scores[agent_key]

                # Calculate final topic score (average)
                final_values = [v for v in topic_final.values() if isinstance(v, (int, float))]
                if not final_values:
                    continue
                final_avg = sum(final_values) / len(final_values)

                # Delta from consensus
                delta = agent_score - final_avg

                # Historical baseline (if available)
                baseline = 0.0
                if historical_performance and agent_id in historical_performance:
                    recent = historical_performance[agent_id][-5:]  # Last 5 runs
                    if recent:
                        baseline = sum(h.get("score_delta", 0) for h in recent) / len(recent)

                signals.append(EvolutionSignal(
                    agent_id=agent_id,
                    signal_type="score_accuracy",
                    measured_value=abs(delta),
                    baseline_value=abs(baseline),
                    delta=abs(delta) - abs(baseline),
                    confidence=0.7,
                    context={
                        "topic_id": topic_id,
                        "agent_score": agent_score,
                        "final_consensus": final_avg,
                    },
                ))

    # 2. Consensus contribution signals
    decisions = convergence_state.decisions
    decision_owners: dict[str, int] = {}
    for decision in decisions:
        owner = decision.owner
        decision_owners[owner] = decision_owners.get(owner, 0) + 1

    total_decisions = len(decisions)
    for agent_id in agent_definitions:
        contribution = decision_owners.get(agent_id, 0)
        expected = total_decisions / max(1, len(agent_definitions))

        signals.append(EvolutionSignal(
            agent_id=agent_id,
            signal_type="consensus_contribution",
            measured_value=contribution,
            baseline_value=expected,
            delta=contribution - expected,
            confidence=0.6,
            context={"total_decisions": total_decisions},
        ))

    # 3. Convergence speed signals (from execution log)
    for entry in convergence_state.execution_log:
        if entry.get("type") == "chapter":
            chapter_id = entry.get("chapter_id", "")
            rounds = entry.get("rounds", 0)
            converged = entry.get("converged", False)

            # Find agents in this chapter
            for level1 in convergence_state.level1_results:
                if level1.chapter_id == chapter_id:
                    for agent_id in level1.agent_ids:
                        signals.append(EvolutionSignal(
                            agent_id=agent_id,
                            signal_type="convergence_speed",
                            measured_value=rounds,
                            baseline_value=2.0,  # Expected average
                            delta=rounds - 2.0,
                            confidence=0.5 if converged else 0.3,
                            context={
                                "chapter_id": chapter_id,
                                "converged": converged,
                            },
                        ))

    return signals


# ---------------------------------------------------------------------------
# Pattern Analysis (E-3)
# ---------------------------------------------------------------------------

def analyze_agent_evolution(
    signals: list[EvolutionSignal],
    agent_definitions: dict[str, dict],
    personas: dict[str, AgentPersona],
    recent_history: dict[str, list[EvolutionSignal]] | None = None,
    command: str | None = None,
    timeout: float = LLM_DELIBERATION_TIMEOUT_SECONDS,
) -> list[EvolutionProposal]:
    """Analyze signals and propose evolution changes.

    Toss style: LLM analyzes patterns and proposes specific changes.
    No hardcoded rules - LLM decides what to adjust.

    Args:
        signals: Current run's signals
        agent_definitions: Current agent definitions
        personas: Current agent personas
        recent_history: Historical signals per agent (last N runs)
        command: LLM command override
        timeout: LLM timeout

    Returns:
        List of EvolutionProposal
    """
    resolved_cmd = command
    if not resolved_cmd:
        resolved_cmd = os.getenv(LLM_EVOLUTION_CMD_ENV, "").strip() or None

    # Group signals by agent
    agent_signals: dict[str, list[dict]] = {}
    for sig in signals:
        if sig.agent_id not in agent_signals:
            agent_signals[sig.agent_id] = []
        agent_signals[sig.agent_id].append(sig.to_dict())

    # Build agent profiles
    agent_profiles: dict[str, dict] = {}
    for agent_id, defn in agent_definitions.items():
        persona = personas.get(agent_id)
        agent_profiles[agent_id] = {
            "current_weights": persona.weights if persona else defn.get("weights", {}),
            "current_directives": persona.behavioral_directives if persona else defn.get("behavioral_directives", []),
            "role": defn.get("role", ""),
            "tier": defn.get("tier", 2),
            "team": defn.get("team", ""),
        }

    payload = {
        "version": "agent-evolution-v1",
        "instructions": {
            "task": (
                "토스 스타일 에이전트 진화 분석. "
                "각 에이전트의 성과 시그널을 분석하고, 개선 제안을 생성하세요."
            ),
            "principles": [
                "데이터 기반: 시그널에서 패턴을 찾아 제안",
                "점진적 변화: 작은 조정 권장 (delta < 0.1)",
                "롤백 가능: 큰 변화는 신중히",
                "자율성 존중: 각 에이전트의 역할 특성 고려",
            ],
            "output_rules": (
                "각 제안에는 반드시 포함: "
                "1. agent_id, proposal_type "
                "2. specific changes (weight adjustments, directives) "
                "3. rationale (왜 이 변화가 필요한지) "
                "4. confidence (0.0~1.0)"
            ),
        },
        "output_contract": {
            "proposals": [
                {
                    "agent_id": "string",
                    "proposal_type": "weight_adjust | directive_add | directive_remove | trust_adjust",
                    "changes": {
                        "weight_adjustments": [{"weight_name": "str", "delta": "float"}],
                        "add_directives": ["string"],
                        "remove_directives": ["string"],
                        "trust_adjustments": [{"target_agent": "str", "delta": "float"}],
                    },
                    "rationale": "string",
                    "confidence": "float 0.0~1.0",
                    "signals_used": ["signal_type list"],
                }
            ],
        },
        "agent_signals": agent_signals,
        "agent_profiles": agent_profiles,
        "recent_history": recent_history or {},
    }

    result = run_llm_command(
        payload=payload,
        command=resolved_cmd,
        timeout=timeout,
    )

    proposals: list[EvolutionProposal] = []

    if result.status != "ok":
        logger.warning("Evolution analysis LLM failed: %s", result.status)
        return proposals

    response = result.parsed
    raw_proposals = response.get("proposals", [])

    if not isinstance(raw_proposals, list):
        return proposals

    for prop in raw_proposals:
        if not isinstance(prop, dict):
            continue

        agent_id = str(prop.get("agent_id", "")).strip()
        if not agent_id or agent_id not in agent_definitions:
            continue

        proposal_type = str(prop.get("proposal_type", "")).strip()
        if not proposal_type:
            continue

        changes = prop.get("changes", {})
        if not isinstance(changes, dict):
            changes = {}

        # Calculate max delta for magnitude classification
        max_delta = 0.0
        weight_adjs = changes.get("weight_adjustments", [])
        if isinstance(weight_adjs, list):
            for wa in weight_adjs:
                if isinstance(wa, dict):
                    delta = abs(float(wa.get("delta", 0)))
                    max_delta = max(max_delta, delta)

        trust_adjs = changes.get("trust_adjustments", [])
        if isinstance(trust_adjs, list):
            for ta in trust_adjs:
                if isinstance(ta, dict):
                    delta = abs(float(ta.get("delta", 0)))
                    max_delta = max(max_delta, delta)

        # Directive changes are considered "small" magnitude
        if changes.get("add_directives") or changes.get("remove_directives"):
            max_delta = max(max_delta, 0.08)

        magnitude, auto_apply = _classify_magnitude(max_delta)

        confidence = _clamp(float(prop.get("confidence", 0.5)), 0.0, 1.0)
        # Lower confidence reduces auto_apply threshold
        if confidence < 0.6 and magnitude == "small":
            auto_apply = False

        signals_used = prop.get("signals_used", [])
        if not isinstance(signals_used, list):
            signals_used = []

        proposals.append(EvolutionProposal(
            agent_id=agent_id,
            proposal_type=proposal_type,
            change_magnitude=magnitude,
            auto_apply=auto_apply,
            details=changes,
            rationale=str(prop.get("rationale", "")),
            confidence=confidence,
            signals_used=[str(s) for s in signals_used],
        ))

    return proposals


# ---------------------------------------------------------------------------
# Apply Evolution (E-4)
# ---------------------------------------------------------------------------

def create_agent_snapshot(
    agent_id: str,
    persona: AgentPersona,
    reason: str,
    version: int = 1,
) -> AgentSnapshot:
    """Create a snapshot of agent state for rollback.

    Toss style: Always snapshot before evolution.
    """
    return AgentSnapshot(
        agent_id=agent_id,
        version=version,
        weights=dict(persona.weights) if persona.weights else {},
        behavioral_directives=list(persona.behavioral_directives) if persona.behavioral_directives else [],
        constraints=list(persona.constraints) if persona.constraints else [],
        trust_map=dict(persona.trust_map) if persona.trust_map else {},
        created_at=datetime.utcnow().isoformat(),
        reason=reason,
    )


def apply_evolution_proposal(
    proposal: EvolutionProposal,
    persona: AgentPersona,
) -> tuple[AgentPersona, dict[str, Any]]:
    """Apply a single evolution proposal to an agent persona.

    Returns updated persona and change log.
    """
    changes_applied: dict[str, Any] = {
        "agent_id": proposal.agent_id,
        "proposal_type": proposal.proposal_type,
        "changes": [],
    }

    details = proposal.details

    # Apply weight adjustments
    weight_adjs = details.get("weight_adjustments", [])
    if isinstance(weight_adjs, list):
        new_weights = dict(persona.weights) if persona.weights else {}
        for wa in weight_adjs:
            if not isinstance(wa, dict):
                continue
            weight_name = str(wa.get("weight_name", "")).strip()
            if not weight_name:
                continue
            delta = float(wa.get("delta", 0))
            old_value = new_weights.get(weight_name, 0.2)
            new_value = _clamp(old_value + delta, 0.0, 1.0)
            new_weights[weight_name] = new_value
            changes_applied["changes"].append({
                "type": "weight",
                "name": weight_name,
                "old": old_value,
                "new": new_value,
            })
        persona.weights = new_weights

    # Apply directive additions
    add_dirs = details.get("add_directives", [])
    if isinstance(add_dirs, list):
        current = list(persona.behavioral_directives) if persona.behavioral_directives else []
        for directive in add_dirs:
            if directive and directive not in current:
                current.append(directive)
                changes_applied["changes"].append({
                    "type": "directive_add",
                    "value": directive,
                })
        persona.behavioral_directives = current

    # Apply directive removals
    remove_dirs = details.get("remove_directives", [])
    if isinstance(remove_dirs, list):
        current = list(persona.behavioral_directives) if persona.behavioral_directives else []
        for directive in remove_dirs:
            if directive in current:
                current.remove(directive)
                changes_applied["changes"].append({
                    "type": "directive_remove",
                    "value": directive,
                })
        persona.behavioral_directives = current

    # Apply trust adjustments
    trust_adjs = details.get("trust_adjustments", [])
    if isinstance(trust_adjs, list):
        new_trust = dict(persona.trust_map) if persona.trust_map else {}
        for ta in trust_adjs:
            if not isinstance(ta, dict):
                continue
            target = str(ta.get("target_agent", "")).strip()
            if not target:
                continue
            delta = float(ta.get("delta", 0))
            old_value = new_trust.get(target, 0.5)
            new_value = _clamp(old_value + delta, 0.1, 1.0)
            new_trust[target] = new_value
            changes_applied["changes"].append({
                "type": "trust",
                "target": target,
                "old": old_value,
                "new": new_value,
            })
        persona.trust_map = new_trust

    return persona, changes_applied


def run_evolution_cycle(
    convergence_state: ConvergencePipelineState,
    agent_definitions: dict[str, dict],
    personas: dict[str, AgentPersona],
    historical_performance: dict[str, list[dict]] | None = None,
    command: str | None = None,
    timeout: float = LLM_DELIBERATION_TIMEOUT_SECONDS,
) -> tuple[EvolutionResult, dict[str, AgentPersona]]:
    """Run a complete evolution cycle.

    Toss style:
    1. Collect signals from this run
    2. Analyze patterns with LLM
    3. Auto-apply safe changes, flag large ones
    4. Create snapshots for rollback

    Returns:
        (EvolutionResult, updated_personas)
    """
    # Step 1: Collect signals
    signals = compute_evolution_signals(
        convergence_state=convergence_state,
        agent_definitions=agent_definitions,
        personas=personas,
        historical_performance=historical_performance,
    )

    # Step 2: Analyze and propose
    proposals = analyze_agent_evolution(
        signals=signals,
        agent_definitions=agent_definitions,
        personas=personas,
        recent_history=None,  # Could pass historical signals here
        command=command,
        timeout=timeout,
    )

    # Step 3: Apply changes
    auto_applied: list[str] = []
    flagged_for_review: list[str] = []
    snapshots_created: list[str] = []
    updated_personas = dict(personas)

    for proposal in proposals:
        agent_id = proposal.agent_id
        if agent_id not in updated_personas:
            continue

        persona = updated_personas[agent_id]

        if proposal.auto_apply:
            # Create snapshot before applying
            snapshot = create_agent_snapshot(
                agent_id=agent_id,
                persona=persona,
                reason=f"Pre-evolution snapshot: {proposal.proposal_type}",
            )
            snapshots_created.append(agent_id)

            # Apply changes
            updated_persona, _ = apply_evolution_proposal(proposal, persona)
            updated_personas[agent_id] = updated_persona
            auto_applied.append(agent_id)

            logger.info(
                "Auto-applied %s evolution for %s (magnitude=%s, confidence=%.2f)",
                proposal.proposal_type,
                agent_id,
                proposal.change_magnitude,
                proposal.confidence,
            )
        else:
            flagged_for_review.append(agent_id)
            logger.info(
                "Flagged for review: %s evolution for %s (magnitude=%s)",
                proposal.proposal_type,
                agent_id,
                proposal.change_magnitude,
            )

    result = EvolutionResult(
        signals_collected=signals,
        proposals=proposals,
        auto_applied=list(set(auto_applied)),
        flagged_for_review=list(set(flagged_for_review)),
        snapshots_created=list(set(snapshots_created)),
        meta={
            "total_signals": len(signals),
            "total_proposals": len(proposals),
        },
    )

    return result, updated_personas


def rollback_agent(
    agent_id: str,
    snapshot: AgentSnapshot,
    current_persona: AgentPersona,
) -> AgentPersona:
    """Rollback an agent to a previous snapshot.

    Toss style: Fast rollback when evolution doesn't work.
    """
    current_persona.weights = dict(snapshot.weights)
    current_persona.behavioral_directives = list(snapshot.behavioral_directives)
    current_persona.constraints = list(snapshot.constraints)
    current_persona.trust_map = dict(snapshot.trust_map)

    logger.info("Rolled back agent %s to version %d", agent_id, snapshot.version)

    return current_persona
