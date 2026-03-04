"""Data types for the R&D orchestrator."""
from __future__ import annotations

import math
from dataclasses import dataclass, field


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

    def normalized_score(self, value: float) -> float:
        return max(0.0, min(10.0, round(value, 2)))

    def compute_features(self) -> dict[str, float]:
        """Legacy feature computation formula. Kept for backward compat.

        In LLM-driven mode, scoring.py replaces this with LLM calls.
        """
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

        return {
            "impact": impact,
            "feasibility": feasibility,
            "novelty": novelty,
            "research_signal": research_signal,
            "risk_penalty": risk_penalty,
            "weighted_hits": round(weighted_hits, 2),
        }

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
