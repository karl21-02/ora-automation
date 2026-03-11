"""Structured debate module for LLM-driven deliberation.

Implements Advocate → Challenger → Mediation debate structure.
All logic is LLM-driven with no hardcoded rules.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from .config import LLM_DELIBERATION_TIMEOUT_SECONDS
from .llm_client import run_llm_command
from .types import (
    AdvocatePhase,
    ChallengerPhase,
    DebateArgument,
    MediationPhase,
    ScoreAdjustment,
    StructuredDebateResult,
    StructuredDebateRound,
    TopicState,
)

logger = logging.getLogger(__name__)

# Environment variable for structured debate LLM command
LLM_STRUCTURED_DEBATE_CMD_ENV = "ORA_LLM_STRUCTURED_DEBATE_CMD"

# Score bounds
SCORE_MIN = 0.0
SCORE_MAX = 10.0

# Convergence threshold for structured debate
STRUCTURED_DEBATE_CONVERGENCE_THRESHOLD = 0.5


def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value to range with 4 decimal precision."""
    return round(max(lo, min(hi, value)), 4)


def _coerce_confidence(value: object, default: float = 0.5) -> float:
    """Safely parse confidence to 0.0~1.0 range."""
    try:
        return _clamp(float(value), 0.0, 1.0)
    except (TypeError, ValueError):
        return default


def _select_roles_via_llm(
    topic_id: str,
    topic_name: str,
    current_scores: dict[str, dict[str, float]],
    agent_ids: list[str],
    agent_definitions: dict[str, dict],
    round_num: int,
    previous_roles: dict[str, str] | None = None,
    command: str | None = None,
    timeout: float = LLM_DELIBERATION_TIMEOUT_SECONDS,
) -> tuple[list[str], list[str], str]:
    """LLM selects advocates, challengers, and mediator dynamically.

    Toss style: Roles are NOT fixed by score.
    - Devil's Advocate pattern: anyone can challenge regardless of their score
    - Roles can change each round for perspective diversity
    - Selection based on expertise, not just opinion

    Returns (advocates, challengers, mediator_id)
    """
    resolved_cmd = command
    if not resolved_cmd:
        resolved_cmd = os.getenv(LLM_STRUCTURED_DEBATE_CMD_ENV, "").strip() or None

    payload = {
        "version": "structured-debate-role-selection-v1",
        "instructions": {
            "task": (
                "토스 스타일 역할 배정. 점수 높다고 advocate, 낮다고 challenger 아님. "
                "누가 이 토픽에 대해 설득력 있는 '찬성' 논거를 펼칠 수 있는지, "
                "누가 '반대' 관점에서 날카로운 질문을 던질 수 있는지 판단하세요."
            ),
            "devil_advocate": (
                "Devil's Advocate 패턴: 평소 찬성하는 사람도 이번엔 반대할 수 있음. "
                "이전 라운드와 다른 조합으로 다양한 관점 확보."
            ),
            "selection_criteria": [
                "전문성 (domain expertise) - 해당 토픽 관련 역할/도메인",
                "다양성 (diversity) - 이전 라운드와 다른 조합 권장",
                "균형 (balance) - advocate/challenger 비슷한 역량",
            ],
            "toss_principle": "Disagree and Commit - 토론 중엔 날카롭게, 결정 후엔 100% 실행",
        },
        "output_contract": {
            "advocates": ["agent_id - 이 토픽 지지 논거 담당"],
            "challengers": ["agent_id - 반박/질문 담당"],
            "mediator": "agent_id - 양측 종합 및 결론",
            "rationale": "역할 배정 이유",
        },
        "topic": {
            "topic_id": topic_id,
            "topic_name": topic_name,
            "current_scores": current_scores.get(topic_id, {}),
        },
        "round_num": round_num,
        "previous_roles": previous_roles or {},
        "available_agents": [
            {
                "agent_id": aid,
                "role": agent_definitions.get(aid, {}).get("role", ""),
                "domain": agent_definitions.get(aid, {}).get("domain", ""),
                "tier": agent_definitions.get(aid, {}).get("tier", 2),
                "team": agent_definitions.get(aid, {}).get("team", ""),
            }
            for aid in agent_ids
        ],
    }

    result = run_llm_command(
        payload=payload,
        command=resolved_cmd,
        timeout=timeout,
    )

    # Fallback: split evenly
    mid = max(1, len(agent_ids) // 2)
    default_advocates = agent_ids[:mid]
    default_challengers = agent_ids[mid:] if len(agent_ids) > 1 else []
    default_mediator = agent_ids[0] if agent_ids else "unknown"

    if result.status != "ok":
        return default_advocates, default_challengers, default_mediator

    response = result.parsed

    # Parse advocates
    advocates = response.get("advocates", [])
    if not isinstance(advocates, list):
        advocates = default_advocates
    else:
        advocates = [a for a in advocates if a in agent_ids]
        if not advocates:
            advocates = default_advocates

    # Parse challengers
    challengers = response.get("challengers", [])
    if not isinstance(challengers, list):
        challengers = default_challengers
    else:
        challengers = [c for c in challengers if c in agent_ids]
        if not challengers and len(agent_ids) > len(advocates):
            challengers = [a for a in agent_ids if a not in advocates][:1]

    # Parse mediator (prefer C-level / tier 1)
    mediator = str(response.get("mediator", "")).strip()
    if mediator not in agent_ids:
        tier_sorted = sorted(
            agent_ids,
            key=lambda a: agent_definitions.get(a, {}).get("tier", 2),
        )
        mediator = tier_sorted[0] if tier_sorted else default_mediator

    return advocates, challengers, mediator


def _select_roles_fallback(
    agent_ids: list[str],
    agent_definitions: dict[str, dict],
) -> tuple[list[str], list[str], str]:
    """Fallback role selection when LLM is unavailable."""
    mid = max(1, len(agent_ids) // 2)
    advocates = agent_ids[:mid]
    challengers = agent_ids[mid:] if len(agent_ids) > 1 else []

    # Mediator: prefer highest tier (C-level)
    tier_sorted = sorted(
        agent_ids,
        key=lambda a: agent_definitions.get(a, {}).get("tier", 2),
    )
    mediator = tier_sorted[0] if tier_sorted else (agent_ids[0] if agent_ids else "unknown")

    return advocates, challengers, mediator


def run_advocate_phase(
    topic_id: str,
    topic_name: str,
    advocates: list[str],
    current_scores: dict[str, dict[str, float]],
    topic_state: TopicState,
    agent_definitions: dict[str, dict],
    command: str | None = None,
    timeout: float = LLM_DELIBERATION_TIMEOUT_SECONDS,
) -> AdvocatePhase:
    """Run the advocate phase: supporters present arguments for the topic.

    Returns AdvocatePhase with arguments from each advocate.
    """
    resolved_cmd = command
    if not resolved_cmd:
        resolved_cmd = os.getenv(LLM_STRUCTURED_DEBATE_CMD_ENV, "").strip() or None

    payload = {
        "version": "structured-debate-advocate-v1",
        "phase": "advocate",
        "instructions": {
            "task": (
                "You are presenting arguments IN FAVOR of this topic. "
                "As advocates, provide compelling reasons why this topic should be prioritized. "
                "Each advocate agent should contribute 2-3 key arguments with supporting evidence."
            ),
            "output_rules": (
                "For each argument, provide: "
                "1. A clear claim statement "
                "2. Supporting evidence (data points, precedents, market signals) "
                "3. Confidence level (0.0~1.0) based on strength of evidence"
            ),
        },
        "output_contract": {
            "arguments": [
                {
                    "agent_id": "advocate agent id",
                    "claim": "main argument claim",
                    "evidence": ["evidence point 1", "evidence point 2"],
                    "confidence": "0.0~1.0",
                }
            ],
        },
        "topic": {
            "topic_id": topic_id,
            "topic_name": topic_name,
            "current_scores": current_scores.get(topic_id, {}),
            "features": topic_state.compute_features(),
            "evidence_count": len(topic_state.evidence),
        },
        "advocates": advocates,
        "advocate_profiles": {
            agent_id: {
                "role": agent_definitions.get(agent_id, {}).get("role", ""),
                "objective": agent_definitions.get(agent_id, {}).get("objective", ""),
                "weights": agent_definitions.get(agent_id, {}).get("weights", {}),
            }
            for agent_id in advocates
        },
    }

    result = run_llm_command(
        payload=payload,
        command=resolved_cmd,
        timeout=timeout,
    )

    arguments: list[DebateArgument] = []

    if result.status == "ok":
        response = result.parsed
        raw_arguments = response.get("arguments", [])

        if isinstance(raw_arguments, list):
            for arg in raw_arguments:
                if not isinstance(arg, dict):
                    continue
                agent_id = str(arg.get("agent_id", "")).strip()
                if not agent_id or agent_id not in advocates:
                    # Assign to first advocate if invalid
                    agent_id = advocates[0] if advocates else "unknown"

                claim = str(arg.get("claim", "")).strip()
                if not claim:
                    continue

                evidence = arg.get("evidence", [])
                if isinstance(evidence, str):
                    evidence = [evidence]
                elif not isinstance(evidence, list):
                    evidence = []
                evidence = [str(e).strip() for e in evidence if e]

                confidence = _coerce_confidence(arg.get("confidence", 0.7), 0.7)

                arguments.append(DebateArgument(
                    agent_id=agent_id,
                    position="advocate",
                    claim=claim,
                    evidence=evidence,
                    confidence=confidence,
                ))

    return AdvocatePhase(
        topic_id=topic_id,
        advocates=advocates,
        arguments=arguments,
        meta={"status": result.status},
    )


def run_challenger_phase(
    topic_id: str,
    topic_name: str,
    challengers: list[str],
    advocate_phase: AdvocatePhase,
    current_scores: dict[str, dict[str, float]],
    topic_state: TopicState,
    agent_definitions: dict[str, dict],
    command: str | None = None,
    timeout: float = LLM_DELIBERATION_TIMEOUT_SECONDS,
) -> ChallengerPhase:
    """Run the challenger phase: opponents rebut advocate arguments.

    Returns ChallengerPhase with rebuttals to each advocate argument.
    """
    resolved_cmd = command
    if not resolved_cmd:
        resolved_cmd = os.getenv(LLM_STRUCTURED_DEBATE_CMD_ENV, "").strip() or None

    payload = {
        "version": "structured-debate-challenger-v1",
        "phase": "challenger",
        "instructions": {
            "task": (
                "You are challenging the advocate arguments. "
                "For each advocate claim, identify weaknesses, risks, or counterarguments. "
                "Be constructive - point out legitimate concerns, not just opposition."
            ),
            "output_rules": (
                "For each rebuttal: "
                "1. Reference which advocate claim you're addressing "
                "2. Present your counterargument with supporting evidence "
                "3. Confidence level (0.0~1.0) in your rebuttal"
            ),
        },
        "output_contract": {
            "rebuttals": [
                {
                    "agent_id": "challenger agent id",
                    "target_claim": "which advocate claim this addresses",
                    "claim": "counterargument",
                    "evidence": ["evidence point 1"],
                    "confidence": "0.0~1.0",
                }
            ],
        },
        "topic": {
            "topic_id": topic_id,
            "topic_name": topic_name,
            "current_scores": current_scores.get(topic_id, {}),
        },
        "advocate_arguments": [
            {
                "agent_id": arg.agent_id,
                "claim": arg.claim,
                "evidence": arg.evidence,
                "confidence": arg.confidence,
            }
            for arg in advocate_phase.arguments
        ],
        "challengers": challengers,
        "challenger_profiles": {
            agent_id: {
                "role": agent_definitions.get(agent_id, {}).get("role", ""),
                "objective": agent_definitions.get(agent_id, {}).get("objective", ""),
                "weights": agent_definitions.get(agent_id, {}).get("weights", {}),
            }
            for agent_id in challengers
        },
    }

    result = run_llm_command(
        payload=payload,
        command=resolved_cmd,
        timeout=timeout,
    )

    rebuttals: list[DebateArgument] = []

    if result.status == "ok":
        response = result.parsed
        raw_rebuttals = response.get("rebuttals", [])

        if isinstance(raw_rebuttals, list):
            for reb in raw_rebuttals:
                if not isinstance(reb, dict):
                    continue
                agent_id = str(reb.get("agent_id", "")).strip()
                if not agent_id or agent_id not in challengers:
                    agent_id = challengers[0] if challengers else "unknown"

                claim = str(reb.get("claim", "")).strip()
                if not claim:
                    continue

                evidence = reb.get("evidence", [])
                if isinstance(evidence, str):
                    evidence = [evidence]
                elif not isinstance(evidence, list):
                    evidence = []
                evidence = [str(e).strip() for e in evidence if e]

                confidence = _coerce_confidence(reb.get("confidence", 0.6), 0.6)

                rebuttals.append(DebateArgument(
                    agent_id=agent_id,
                    position="challenger",
                    claim=claim,
                    evidence=evidence,
                    confidence=confidence,
                ))

    return ChallengerPhase(
        topic_id=topic_id,
        challengers=challengers,
        rebuttals=rebuttals,
        meta={"status": result.status},
    )


def run_mediation_phase(
    topic_id: str,
    topic_name: str,
    mediator_id: str,
    advocate_phase: AdvocatePhase,
    challenger_phase: ChallengerPhase,
    current_scores: dict[str, dict[str, float]],
    agent_definitions: dict[str, dict],
    command: str | None = None,
    timeout: float = LLM_DELIBERATION_TIMEOUT_SECONDS,
) -> MediationPhase:
    """Run the mediation phase: synthesize arguments and propose consensus.

    Returns MediationPhase with proposed score and synthesis.
    """
    resolved_cmd = command
    if not resolved_cmd:
        resolved_cmd = os.getenv(LLM_STRUCTURED_DEBATE_CMD_ENV, "").strip() or None

    # Calculate average current score
    topic_scores = current_scores.get(topic_id, {})
    score_values = [v for v in topic_scores.values() if isinstance(v, (int, float))]
    avg_score = sum(score_values) / len(score_values) if score_values else 5.0

    payload = {
        "version": "structured-debate-mediation-v1",
        "phase": "mediation",
        "instructions": {
            "task": (
                "You are the mediator synthesizing the debate. "
                "Evaluate both advocate and challenger arguments objectively. "
                "Propose a consensus score that balances both perspectives."
            ),
            "output_rules": (
                "Provide: "
                "1. A proposed consensus score (0.0~10.0) "
                "2. Acceptable score range based on unresolved disagreements "
                "3. List of resolved points (where consensus was reached) "
                "4. List of unresolved points (for next round) "
                "5. Synthesis summarizing the balanced view "
                "6. Confidence in your proposed score (0.0~1.0)"
            ),
        },
        "output_contract": {
            "proposed_score": "float 0.0~10.0",
            "score_range": {"min": "float", "max": "float"},
            "resolved_points": ["point 1", "point 2"],
            "unresolved_points": ["issue 1"],
            "next_round_focus": ["what to discuss next"],
            "synthesis": "balanced summary",
            "confidence": "0.0~1.0",
        },
        "topic": {
            "topic_id": topic_id,
            "topic_name": topic_name,
            "current_average_score": round(avg_score, 2),
        },
        "advocate_arguments": [
            {
                "agent_id": arg.agent_id,
                "claim": arg.claim,
                "evidence": arg.evidence,
                "confidence": arg.confidence,
            }
            for arg in advocate_phase.arguments
        ],
        "challenger_rebuttals": [
            {
                "agent_id": reb.agent_id,
                "claim": reb.claim,
                "evidence": reb.evidence,
                "confidence": reb.confidence,
            }
            for reb in challenger_phase.rebuttals
        ],
        "mediator": {
            "agent_id": mediator_id,
            "role": agent_definitions.get(mediator_id, {}).get("role", ""),
            "objective": agent_definitions.get(mediator_id, {}).get("objective", ""),
        },
    }

    result = run_llm_command(
        payload=payload,
        command=resolved_cmd,
        timeout=timeout,
    )

    # Default values
    proposed_score = avg_score
    score_range = (SCORE_MIN, SCORE_MAX)
    resolved_points: list[str] = []
    unresolved_points: list[str] = []
    next_round_focus: list[str] = []
    synthesis = ""
    confidence = 0.5

    if result.status == "ok":
        response = result.parsed

        # Parse proposed score
        try:
            proposed_score = _clamp(float(response.get("proposed_score", avg_score)), SCORE_MIN, SCORE_MAX)
        except (TypeError, ValueError):
            pass

        # Parse score range
        range_data = response.get("score_range", {})
        if isinstance(range_data, dict):
            try:
                range_min = _clamp(float(range_data.get("min", SCORE_MIN)), SCORE_MIN, SCORE_MAX)
                range_max = _clamp(float(range_data.get("max", SCORE_MAX)), SCORE_MIN, SCORE_MAX)
                score_range = (min(range_min, range_max), max(range_min, range_max))
            except (TypeError, ValueError):
                pass

        # Parse lists
        resolved_points = _parse_string_list(response.get("resolved_points", []))
        unresolved_points = _parse_string_list(response.get("unresolved_points", []))
        next_round_focus = _parse_string_list(response.get("next_round_focus", []))

        synthesis = str(response.get("synthesis", "")).strip()
        confidence = _coerce_confidence(response.get("confidence", 0.5), 0.5)

    return MediationPhase(
        topic_id=topic_id,
        mediator_id=mediator_id,
        proposed_score=proposed_score,
        score_range=score_range,
        resolved_points=resolved_points,
        unresolved_points=unresolved_points,
        next_round_focus=next_round_focus,
        synthesis=synthesis,
        confidence=confidence,
    )


def _parse_string_list(value: Any) -> list[str]:
    """Parse a value into a list of non-empty strings."""
    if not isinstance(value, list):
        return []
    return [str(s).strip() for s in value if s and str(s).strip()]


def run_structured_debate_round(
    round_num: int,
    topic_id: str,
    topic_name: str,
    current_scores: dict[str, dict[str, float]],
    topic_state: TopicState,
    agent_ids: list[str],
    agent_definitions: dict[str, dict],
    previous_round: StructuredDebateRound | None = None,
    command: str | None = None,
    timeout: float = LLM_DELIBERATION_TIMEOUT_SECONDS,
) -> StructuredDebateRound:
    """Run a complete structured debate round: Advocate → Challenger → Mediation.

    Toss style: Roles are dynamically assigned by LLM each round.
    Devil's Advocate pattern - anyone can take any position.

    Args:
        round_num: Current round number
        topic_id: Topic being debated
        topic_name: Human-readable topic name
        current_scores: Current scores {topic_id: {agent_key: score}}
        topic_state: TopicState object with evidence
        agent_ids: List of participating agent IDs
        agent_definitions: Agent definitions {agent_id: {...}}
        previous_round: Previous round result (for context)
        command: LLM command override
        timeout: LLM timeout in seconds

    Returns:
        StructuredDebateRound with all phases
    """
    # Build previous roles from previous round
    previous_roles: dict[str, str] = {}
    if previous_round:
        for adv in previous_round.meta.get("advocates", []):
            previous_roles[adv] = "advocate"
        for chl in previous_round.meta.get("challengers", []):
            previous_roles[chl] = "challenger"
        mediator = previous_round.meta.get("mediator")
        if mediator:
            previous_roles[mediator] = "mediator"

    # Toss style: LLM dynamically assigns roles each round
    advocates, challengers, mediator_id = _select_roles_via_llm(
        topic_id=topic_id,
        topic_name=topic_name,
        current_scores=current_scores,
        agent_ids=agent_ids,
        agent_definitions=agent_definitions,
        round_num=round_num,
        previous_roles=previous_roles,
        command=command,
        timeout=timeout,
    )

    # Fallback if LLM returns empty
    if not advocates or not challengers:
        advocates, challengers, mediator_id = _select_roles_fallback(
            agent_ids=agent_ids,
            agent_definitions=agent_definitions,
        )

    # Phase 1: Advocate
    advocate_phase = run_advocate_phase(
        topic_id=topic_id,
        topic_name=topic_name,
        advocates=advocates,
        current_scores=current_scores,
        topic_state=topic_state,
        agent_definitions=agent_definitions,
        command=command,
        timeout=timeout,
    )

    # Phase 2: Challenger
    challenger_phase = run_challenger_phase(
        topic_id=topic_id,
        topic_name=topic_name,
        challengers=challengers,
        advocate_phase=advocate_phase,
        current_scores=current_scores,
        topic_state=topic_state,
        agent_definitions=agent_definitions,
        command=command,
        timeout=timeout,
    )

    # Phase 3: Mediation
    mediation_phase = run_mediation_phase(
        topic_id=topic_id,
        topic_name=topic_name,
        mediator_id=mediator_id,
        advocate_phase=advocate_phase,
        challenger_phase=challenger_phase,
        current_scores=current_scores,
        agent_definitions=agent_definitions,
        command=command,
        timeout=timeout,
    )

    # Check convergence: if score range is tight and confidence is high
    score_range_width = mediation_phase.score_range[1] - mediation_phase.score_range[0]
    converged = (
        score_range_width <= STRUCTURED_DEBATE_CONVERGENCE_THRESHOLD
        and mediation_phase.confidence >= 0.7
        and len(mediation_phase.unresolved_points) == 0
    )

    return StructuredDebateRound(
        round_num=round_num,
        topic_id=topic_id,
        topic_name=topic_name,
        advocate_phase=advocate_phase,
        challenger_phase=challenger_phase,
        mediation_phase=mediation_phase,
        converged=converged,
        meta={
            "advocates": advocates,
            "challengers": challengers,
            "mediator": mediator_id,
        },
    )


def run_structured_debate(
    topics: dict[str, TopicState],
    initial_scores: dict[str, dict[str, float]],
    agent_ids: list[str],
    agent_definitions: dict[str, dict],
    max_rounds: int = 3,
    command: str | None = None,
    timeout: float = LLM_DELIBERATION_TIMEOUT_SECONDS,
) -> StructuredDebateResult:
    """Run structured debate across all topics until convergence or max rounds.

    Args:
        topics: {topic_id: TopicState}
        initial_scores: {topic_id: {agent_key: score}}
        agent_ids: List of participating agent IDs
        agent_definitions: Agent definitions
        max_rounds: Maximum rounds per topic
        command: LLM command override
        timeout: LLM timeout in seconds

    Returns:
        StructuredDebateResult with all debates and final scores
    """
    topic_debates: dict[str, list[StructuredDebateRound]] = {}
    working_scores = {tid: dict(scores) for tid, scores in initial_scores.items()}
    rounds_executed = 0
    all_converged = True

    for topic_id, topic_state in topics.items():
        topic_name = topic_state.topic_name
        topic_debates[topic_id] = []
        previous_round: StructuredDebateRound | None = None
        topic_converged = False

        for round_num in range(1, max_rounds + 1):
            debate_round = run_structured_debate_round(
                round_num=round_num,
                topic_id=topic_id,
                topic_name=topic_name,
                current_scores=working_scores,
                topic_state=topic_state,
                agent_ids=agent_ids,
                agent_definitions=agent_definitions,
                previous_round=previous_round,
                command=command,
                timeout=timeout,
            )

            topic_debates[topic_id].append(debate_round)
            rounds_executed = max(rounds_executed, round_num)

            # Update working scores with mediation result
            proposed = debate_round.mediation_phase.proposed_score
            confidence = debate_round.mediation_phase.confidence

            # Apply mediated score to all agents with confidence weighting
            for agent_id in agent_ids:
                key = f"score_{agent_id.lower()}"
                if key not in working_scores[topic_id]:
                    key = agent_id.lower()
                if key in working_scores[topic_id]:
                    current = working_scores[topic_id][key]
                    # Blend current score with proposed based on confidence
                    new_score = current * (1 - confidence) + proposed * confidence
                    working_scores[topic_id][key] = _clamp(new_score, SCORE_MIN, SCORE_MAX)

            if debate_round.converged:
                topic_converged = True
                break

            previous_round = debate_round

        if not topic_converged:
            all_converged = False

    # Compute final scores as averages
    final_scores: dict[str, float] = {}
    for topic_id, scores in working_scores.items():
        values = [v for v in scores.values() if isinstance(v, (int, float))]
        final_scores[topic_id] = round(sum(values) / len(values), 4) if values else 5.0

    return StructuredDebateResult(
        topic_debates=topic_debates,
        final_scores=final_scores,
        rounds_executed=rounds_executed,
        all_converged=all_converged,
        meta={
            "max_rounds": max_rounds,
            "topics_count": len(topics),
            "agent_count": len(agent_ids),
        },
    )


def extract_score_adjustments_from_debate(
    debate_result: StructuredDebateResult,
) -> dict[str, dict[str, ScoreAdjustment]]:
    """Convert structured debate results to score adjustments format.

    This allows integration with the existing deliberation pipeline.
    """
    adjustments: dict[str, dict[str, ScoreAdjustment]] = {}

    for topic_id, rounds in debate_result.topic_debates.items():
        if not rounds:
            continue

        # Use the last round's mediation as the adjustment
        last_round = rounds[-1]
        mediation = last_round.mediation_phase

        # Create adjustment for the mediator
        adjustments[topic_id] = {
            mediation.mediator_id: ScoreAdjustment(
                delta=mediation.proposed_score - 5.0,  # Delta from neutral
                confidence=mediation.confidence,
            )
        }

    return adjustments
