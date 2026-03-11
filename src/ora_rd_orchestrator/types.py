"""Data types for the R&D orchestrator."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Evidence:
    file: str
    line_no: int
    snippet: str
    topic_hit: str


@dataclass
class DebateEvent:
    round: int
    speaker: str
    action: str
    topic_id: str
    topic_name: str
    delta: float
    reason: str
    target_agents: list[str]
    confidence: float
    evidence_weight: float


@dataclass
class ScoreAdjustment:
    """Score adjustment from an agent with confidence level."""
    delta: float
    confidence: float = 0.5  # 0.0 ~ 1.0, default mid confidence

    def to_dict(self) -> dict:
        return {"delta": self.delta, "confidence": self.confidence}


@dataclass
class TrustUpdate:
    """Trust adjustment between two agents based on deliberation outcome.

    Represents how much agent A's trust in agent B should change based on
    how accurate/helpful B's contributions were in deliberation.
    """
    source_agent: str           # Agent whose trust_map is being updated
    target_agent: str           # Agent being evaluated
    delta: float                # Trust change: -0.2 ~ +0.2
    confidence: float           # How confident we are in this update: 0.0 ~ 1.0
    reason: str                 # LLM-generated explanation
    evidence_topic_ids: list[str] = field(default_factory=list)  # Topics that informed this

    def to_dict(self) -> dict:
        return {
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "delta": self.delta,
            "confidence": self.confidence,
            "reason": self.reason,
            "evidence_topic_ids": self.evidence_topic_ids,
        }


@dataclass
class TrustLearningResult:
    """Result of trust learning after a deliberation session.

    Contains all trust updates computed by analyzing deliberation outcomes.
    """
    updates: list[TrustUpdate] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)  # LLM metadata, timing, etc.

    def to_dict(self) -> dict:
        return {
            "updates": [u.to_dict() for u in self.updates],
            "meta": self.meta,
        }

    def apply_to_trust_map(
        self,
        trust_map: dict[str, dict[str, float]],
        min_trust: float = 0.1,
        max_trust: float = 1.0,
        decay_factor: float = 0.9,
    ) -> dict[str, dict[str, float]]:
        """Apply updates to trust_map in-place, with bounds and decay.

        Args:
            trust_map: {agent_id: {other_agent_id: trust_score}}
            min_trust: Minimum trust value (prevents complete distrust)
            max_trust: Maximum trust value
            decay_factor: Applied to delta based on confidence

        Returns:
            Updated trust_map (same reference, modified in-place)
        """
        for update in self.updates:
            src = update.source_agent
            tgt = update.target_agent
            if src not in trust_map:
                trust_map[src] = {}

            current = trust_map[src].get(tgt, 0.5)  # default neutral trust
            # Scale delta by confidence
            effective_delta = update.delta * update.confidence * decay_factor
            new_trust = current + effective_delta
            # Clamp to bounds
            trust_map[src][tgt] = max(min_trust, min(max_trust, round(new_trust, 4)))

        return trust_map


@dataclass
class WeightAdjustment:
    """Single weight adjustment for an agent's scoring weights."""
    weight_name: str          # e.g., "impact", "feasibility", "novelty"
    delta: float              # Change: -0.1 ~ +0.1
    confidence: float         # How confident: 0.0 ~ 1.0
    reason: str               # Why this adjustment

    def to_dict(self) -> dict:
        return {
            "weight_name": self.weight_name,
            "delta": self.delta,
            "confidence": self.confidence,
            "reason": self.reason,
        }


@dataclass
class PersonaAdjustment:
    """Adjustments to an agent's persona based on deliberation outcomes.

    Includes weight changes, behavioral directive suggestions, and
    constraint modifications.
    """
    agent_id: str
    weight_adjustments: list[WeightAdjustment] = field(default_factory=list)
    add_directives: list[str] = field(default_factory=list)      # New directives to add
    remove_directives: list[str] = field(default_factory=list)   # Directives to remove
    add_constraints: list[str] = field(default_factory=list)     # New constraints
    remove_constraints: list[str] = field(default_factory=list)  # Constraints to remove
    overall_assessment: str = ""                                  # LLM's overall assessment
    confidence: float = 0.5                                       # Overall confidence

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "weight_adjustments": [w.to_dict() for w in self.weight_adjustments],
            "add_directives": self.add_directives,
            "remove_directives": self.remove_directives,
            "add_constraints": self.add_constraints,
            "remove_constraints": self.remove_constraints,
            "overall_assessment": self.overall_assessment,
            "confidence": self.confidence,
        }


@dataclass
class PersonaLearningResult:
    """Result of persona learning after deliberation.

    Contains all persona adjustments computed by analyzing agent performance.
    """
    adjustments: list[PersonaAdjustment] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "adjustments": [a.to_dict() for a in self.adjustments],
            "meta": self.meta,
        }

    def apply_to_weights(
        self,
        agent_weights: dict[str, dict[str, float]],
        min_weight: float = 0.0,
        max_weight: float = 1.0,
        decay_factor: float = 0.9,
    ) -> dict[str, dict[str, float]]:
        """Apply weight adjustments to agent weights.

        Args:
            agent_weights: {agent_id: {weight_name: value}}
            min_weight: Minimum weight value
            max_weight: Maximum weight value
            decay_factor: Dampening factor for adjustments

        Returns:
            Updated weights dict (modified in-place)
        """
        for adjustment in self.adjustments:
            agent_id = adjustment.agent_id
            if agent_id not in agent_weights:
                agent_weights[agent_id] = {}

            for wa in adjustment.weight_adjustments:
                current = agent_weights[agent_id].get(wa.weight_name, 0.2)
                effective_delta = wa.delta * wa.confidence * decay_factor
                new_value = current + effective_delta
                agent_weights[agent_id][wa.weight_name] = max(
                    min_weight, min(max_weight, round(new_value, 4))
                )

        return agent_weights


@dataclass
class OrchestrationDecision:
    decision_id: str
    owner: str
    rationale: str
    risk: str
    next_action: str
    due: str
    topic_id: str
    topic_name: str
    service: list[str]
    score_delta: float
    confidence: float
    fail_label: str

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "owner": self.owner,
            "rationale": self.rationale,
            "risk": self.risk,
            "next_action": self.next_action,
            "due": self.due,
            "topic_id": self.topic_id,
            "topic_name": self.topic_name,
            "service": self.service,
            "score_delta": self.score_delta,
            "confidence": self.confidence,
            "fail_label": self.fail_label,
        }


@dataclass
class TopicState:
    topic_id: str
    topic_name: str
    keyword_hits: int = 0
    business_hits: int = 0
    novelty_hits: int = 0
    code_hits: int = 0
    doc_hits: int = 0
    history_hits: int = 0
    project_hits: dict[str, int] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    project_count: int = 0
    _features_cache: dict[str, float] | None = field(default=None, repr=False, compare=False)
    _features_cache_key: tuple | None = field(default=None, repr=False, compare=False)

    def normalized_score(self, value: float) -> float:
        return max(0.0, min(10.0, round(value, 2)))

    def _cache_key(self) -> tuple:
        return (self.keyword_hits, self.business_hits, self.novelty_hits,
                self.code_hits, self.doc_hits, self.history_hits, self.project_count)

    def compute_features(self) -> dict[str, float]:
        """Legacy feature computation formula. Kept for backward compat.

        In LLM-driven mode, scoring.py replaces this with LLM calls.
        """
        key = self._cache_key()
        if self._features_cache is not None and self._features_cache_key == key:
            return self._features_cache

        weighted_hits = self.keyword_hits + (self.code_hits * 0.4) + (self.doc_hits * 0.25)
        project_factor = math.log1p(self.project_count)

        impact = self.normalized_score(
            2.0 + 0.9 * math.log1p(self.keyword_hits + 1)
            + 0.7 * project_factor
            + 0.08 * self.business_hits
        )

        feasibility = self.normalized_score(
            2.1 + 1.7 * math.log1p(self.code_hits + 1) + 0.8 * project_factor
        )

        novelty = self.normalized_score(
            1.5 + 1.2 * math.log1p(self.novelty_hits + 1)
            + 0.4 * self.doc_hits
        )

        research_signal = self.normalized_score(
            1.2 + 0.8 * math.log1p(self.history_hits + 1) + 0.7 * math.log1p(self.keyword_hits + 1)
        )

        risk_penalty = self.normalized_score(
            max(0.0, 5.0 - (0.9 * self.code_hits + 0.6 * self.project_count))
        )

        result = {
            "impact": impact,
            "feasibility": feasibility,
            "novelty": novelty,
            "research_signal": research_signal,
            "risk_penalty": risk_penalty,
            "weighted_hits": round(weighted_hits, 2),
        }
        self._features_cache = result
        self._features_cache_key = key
        return result

    def to_dict(self) -> dict:
        feature = self.compute_features()
        return {
            "topic_id": self.topic_id,
            "topic_name": self.topic_name,
            "keyword_hits": self.keyword_hits,
            "business_hits": self.business_hits,
            "novelty_hits": self.novelty_hits,
            "code_hits": self.code_hits,
            "doc_hits": self.doc_hits,
            "history_hits": self.history_hits,
            "project_count": self.project_count,
            "projects": sorted(self.project_hits.keys()),
            "features": feature,
            "evidence": [
                {
                    "file": e.file,
                    "line_no": e.line_no,
                    "snippet": e.snippet,
                    "topic_hit": e.topic_hit,
                }
                for e in self.evidence[:12]
            ],
        }


@dataclass
class TierResult:
    tier: int
    tier_label: str  # "practitioners"|"team_leads"|"directors"|"executives"
    agent_scores: dict[str, dict[str, float]]  # {topic_id: {agent_key: score}}
    aggregated_scores: dict[str, float] | None = None
    ranking: list[dict] = field(default_factory=list)
    debate_log: list[dict] | None = None
    flags: dict[str, list[str]] = field(default_factory=dict)  # QA gate warnings
    metadata: dict = field(default_factory=dict)


@dataclass
class HierarchicalPipelineState:
    mode: str = "hierarchical"  # "hierarchical"|"flat"
    tier_results: dict[int, TierResult] = field(default_factory=dict)
    final_ranking: list[dict] = field(default_factory=list)
    execution_log: list[dict] = field(default_factory=list)


@dataclass
class ChapterDeliberationResult:
    chapter_id: str
    chapter_name: str
    agent_ids: list[str]
    topic_scores: dict[str, dict[str, float]]  # {topic_id: {score_key: val}}
    rounds_executed: int
    converged: bool
    discussion: list[dict] = field(default_factory=list)


@dataclass
class SiloDeliberationResult:
    silo_id: str
    silo_name: str
    chapter_ids: list[str]
    topic_scores: dict[str, float]  # {topic_id: aggregated_score}
    rounds_executed: int
    converged: bool
    discussion: list[dict] = field(default_factory=list)


@dataclass
class ConvergencePipelineState:
    level1_results: list[ChapterDeliberationResult] = field(default_factory=list)
    clevel_scores: dict[str, dict[str, float]] = field(default_factory=dict)
    level2_results: list[SiloDeliberationResult] = field(default_factory=list)
    level3_scores: dict[str, dict[str, float]] = field(default_factory=dict)
    level3_rounds: int = 0
    level3_converged: bool = False
    final_scores: dict[str, dict[str, float]] = field(default_factory=dict)
    decisions: list[OrchestrationDecision] = field(default_factory=list)
    execution_log: list[dict] = field(default_factory=list)
    # Trust learning result (Phase B)
    trust_learning_result: TrustLearningResult | None = None
    # Persona learning result (Phase C)
    persona_learning_result: PersonaLearningResult | None = None
    # Evolution result (Phase E) - Toss style fast feedback
    evolution_result: EvolutionResult | None = None


# ---------------------------------------------------------------------------
# New types for LLM-driven orchestration
# ---------------------------------------------------------------------------

@dataclass
class AgentPersona:
    agent_id: str
    display_name: str
    display_name_ko: str
    role: str              # "ceo" | "pm" | "developer" | ...
    tier: int              # 1-4
    domain: str | None     # upper Tier2 agent
    team: str              # silo: "strategy"|"product"|"engineering"|"research"|"qa"|"governance"
    system_prompt: str     # full system prompt
    behavioral_directives: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    decision_focus: list[str] = field(default_factory=list)
    trust_map: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    objective: str = ""
    personality: dict[str, str] = field(default_factory=dict)


@dataclass
class TopicDiscovery:
    topic_id: str
    topic_name: str
    description: str
    suggested_keywords: list[str] = field(default_factory=list)
    search_terms: dict[str, str] = field(default_factory=dict)   # {"arxiv": "...", "crossref": "...", "web": "..."}
    rationale: str = ""
    confidence: float = 0.0
    discovered_by: str = "legacy_fallback"  # "llm" | "legacy_fallback"


@dataclass
class WorkspaceSummary:
    projects: dict[str, int] = field(default_factory=dict)
    file_types: dict[str, int] = field(default_factory=dict)
    representative_snippets: list[dict] = field(default_factory=list)
    readme_excerpts: list[str] = field(default_factory=list)
    total_files: int = 0


@dataclass
class LLMResult:
    status: str        # "ok" | "disabled" | "failed"
    parsed: dict = field(default_factory=dict)
    raw_output: str = ""
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Structured Debate Types (Phase D)
# ---------------------------------------------------------------------------

@dataclass
class DebateArgument:
    """A single argument in a structured debate."""
    agent_id: str
    position: str           # "advocate" | "challenger"
    claim: str              # Main claim/point
    evidence: list[str] = field(default_factory=list)     # Supporting evidence
    confidence: float = 0.5  # 0.0 ~ 1.0


@dataclass
class AdvocatePhase:
    """Advocate phase: agents who support the topic present arguments."""
    topic_id: str
    advocates: list[str]          # Agent IDs who advocate
    arguments: list[DebateArgument] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "topic_id": self.topic_id,
            "advocates": self.advocates,
            "arguments": [
                {
                    "agent_id": a.agent_id,
                    "position": a.position,
                    "claim": a.claim,
                    "evidence": a.evidence,
                    "confidence": a.confidence,
                }
                for a in self.arguments
            ],
            "meta": self.meta,
        }


@dataclass
class ChallengerPhase:
    """Challenger phase: agents who oppose the topic present counterarguments."""
    topic_id: str
    challengers: list[str]        # Agent IDs who challenge
    rebuttals: list[DebateArgument] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "topic_id": self.topic_id,
            "challengers": self.challengers,
            "rebuttals": [
                {
                    "agent_id": r.agent_id,
                    "position": r.position,
                    "claim": r.claim,
                    "evidence": r.evidence,
                    "confidence": r.confidence,
                }
                for r in self.rebuttals
            ],
            "meta": self.meta,
        }


@dataclass
class MediationPhase:
    """Mediation phase: synthesis of advocate and challenger arguments."""
    topic_id: str
    mediator_id: str              # Agent ID acting as mediator
    proposed_score: float         # Proposed consensus score
    score_range: tuple[float, float] = (0.0, 10.0)  # Acceptable range
    resolved_points: list[str] = field(default_factory=list)
    unresolved_points: list[str] = field(default_factory=list)
    next_round_focus: list[str] = field(default_factory=list)  # Issues for next round
    synthesis: str = ""           # Summary of mediation
    confidence: float = 0.5       # Confidence in proposed score

    def to_dict(self) -> dict:
        return {
            "topic_id": self.topic_id,
            "mediator_id": self.mediator_id,
            "proposed_score": self.proposed_score,
            "score_range": list(self.score_range),
            "resolved_points": self.resolved_points,
            "unresolved_points": self.unresolved_points,
            "next_round_focus": self.next_round_focus,
            "synthesis": self.synthesis,
            "confidence": self.confidence,
        }


@dataclass
class StructuredDebateRound:
    """A complete structured debate round for a topic.

    Structure: Advocate → Challenger → Mediation
    """
    round_num: int
    topic_id: str
    topic_name: str
    advocate_phase: AdvocatePhase
    challenger_phase: ChallengerPhase
    mediation_phase: MediationPhase
    converged: bool = False        # Did this round reach consensus?
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "round_num": self.round_num,
            "topic_id": self.topic_id,
            "topic_name": self.topic_name,
            "advocate_phase": self.advocate_phase.to_dict(),
            "challenger_phase": self.challenger_phase.to_dict(),
            "mediation_phase": self.mediation_phase.to_dict(),
            "converged": self.converged,
            "meta": self.meta,
        }


@dataclass
class StructuredDebateResult:
    """Result of a complete structured debate session for multiple topics."""
    topic_debates: dict[str, list[StructuredDebateRound]] = field(default_factory=dict)
    final_scores: dict[str, float] = field(default_factory=dict)
    rounds_executed: int = 0
    all_converged: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "topic_debates": {
                tid: [r.to_dict() for r in rounds]
                for tid, rounds in self.topic_debates.items()
            },
            "final_scores": self.final_scores,
            "rounds_executed": self.rounds_executed,
            "all_converged": self.all_converged,
            "meta": self.meta,
        }


# ---------------------------------------------------------------------------
# Agent Evolution Types (Phase E) - Toss Style
# ---------------------------------------------------------------------------

@dataclass
class EvolutionSignal:
    """A single performance signal collected from an orchestration run.

    Toss style: Immediate feedback, no waiting for long-term outcomes.
    """
    agent_id: str
    signal_type: str          # "score_accuracy" | "consensus_contribution" | "argument_quality" | "convergence_speed"
    measured_value: float     # What actually happened
    baseline_value: float     # Expected/previous baseline
    delta: float              # measured - baseline
    confidence: float         # 0.0 ~ 1.0 how reliable this signal is
    context: dict[str, Any] = field(default_factory=dict)  # topic_id, round_num, etc.

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "signal_type": self.signal_type,
            "measured_value": self.measured_value,
            "baseline_value": self.baseline_value,
            "delta": self.delta,
            "confidence": self.confidence,
            "context": self.context,
        }


@dataclass
class EvolutionProposal:
    """A proposed evolution for an agent.

    Toss style: Small changes auto-apply, large changes flag for review.
    """
    agent_id: str
    proposal_type: str        # "weight_adjust" | "directive_add" | "directive_remove" | "trust_reset"
    change_magnitude: str     # "micro" (<0.05) | "small" (<0.15) | "large" (>=0.15)
    auto_apply: bool          # True if safe to auto-apply
    details: dict[str, Any] = field(default_factory=dict)  # Specific changes
    rationale: str = ""       # LLM explanation
    confidence: float = 0.5
    signals_used: list[str] = field(default_factory=list)  # Which signals informed this

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "proposal_type": self.proposal_type,
            "change_magnitude": self.change_magnitude,
            "auto_apply": self.auto_apply,
            "details": self.details,
            "rationale": self.rationale,
            "confidence": self.confidence,
            "signals_used": self.signals_used,
        }


@dataclass
class AgentSnapshot:
    """Snapshot of agent state for rollback capability.

    Toss style: Always be able to rollback.
    """
    agent_id: str
    version: int
    weights: dict[str, float] = field(default_factory=dict)
    behavioral_directives: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    trust_map: dict[str, float] = field(default_factory=dict)
    created_at: str = ""      # ISO timestamp
    reason: str = ""          # Why this snapshot was created

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "version": self.version,
            "weights": self.weights,
            "behavioral_directives": self.behavioral_directives,
            "constraints": self.constraints,
            "trust_map": self.trust_map,
            "created_at": self.created_at,
            "reason": self.reason,
        }


@dataclass
class EvolutionResult:
    """Result of an evolution cycle.

    Toss style: Fast feedback loop with automatic A/B comparison.
    """
    signals_collected: list[EvolutionSignal] = field(default_factory=list)
    proposals: list[EvolutionProposal] = field(default_factory=list)
    auto_applied: list[str] = field(default_factory=list)   # agent_ids that were auto-evolved
    flagged_for_review: list[str] = field(default_factory=list)  # agent_ids needing review
    snapshots_created: list[str] = field(default_factory=list)  # agent_ids with new snapshots
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "signals_collected": [s.to_dict() for s in self.signals_collected],
            "proposals": [p.to_dict() for p in self.proposals],
            "auto_applied": self.auto_applied,
            "flagged_for_review": self.flagged_for_review,
            "snapshots_created": self.snapshots_created,
            "meta": self.meta,
        }


# ---------------------------------------------------------------------------
# Interactive checkpoint types
# ---------------------------------------------------------------------------

@dataclass
class CheckpointData:
    """Payload sent to the checkpoint callback at a pipeline pause point."""
    stage: str                          # e.g. "topic_discovery", "deliberation"
    message: str                        # human-readable summary
    items: list[dict[str, Any]] = field(default_factory=list)   # e.g. discovered topics
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "message": self.message,
            "items": self.items,
            "metadata": self.metadata,
        }


@dataclass
class CheckpointResponse:
    """Response from the user/system to a checkpoint."""
    approved: bool = True
    feedback: str = ""
    modified_items: list[dict[str, Any]] | None = None  # user can edit topic list etc.


# Callable type: receives CheckpointData, returns CheckpointResponse.
# When None, the pipeline runs without pausing (default behavior).
CheckpointCallback = Callable[[CheckpointData], CheckpointResponse] | None


# ---------------------------------------------------------------------------
# Pipeline cancellation + progress
# ---------------------------------------------------------------------------

class PipelineCancelled(Exception):
    """Raised when a running pipeline detects its cancel_event is set."""
    pass


# (stage, message) → None
ProgressCallback = Callable[[str, str], None] | None
