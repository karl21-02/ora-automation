"""AgentState — shared context accumulated across tool calls.

Each tool reads from and writes to this state, enabling the LLM planner
to see what's already been computed via ``summary_for_llm()``.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from ..types import (
    AgentPersona,
    OrchestrationDecision,
    TopicDiscovery,
    TopicState,
    WorkspaceSummary,
)


@dataclass
class AgentState:
    """Mutable state shared across all tool invocations in a single agent run."""

    session_id: str = ""
    user_request: str = ""

    # --- Pipeline artifacts (populated by tools) ---
    workspace_summary: WorkspaceSummary | None = None
    discoveries: list[TopicDiscovery] = field(default_factory=list)
    topic_states: dict[str, TopicState] = field(default_factory=dict)
    scores: dict[str, dict[str, Any]] = field(default_factory=dict)
    ranked: list[dict] = field(default_factory=list)
    pipeline_decisions: list[OrchestrationDecision] = field(default_factory=list)
    consensus_summary: dict = field(default_factory=dict)
    research_sources: list[dict] = field(default_factory=list)
    personas: dict[str, AgentPersona] = field(default_factory=dict)
    agent_definitions: dict | None = None

    # Report artifacts
    strategy_cards: list[dict] = field(default_factory=list)
    qa_verification: list[dict] = field(default_factory=list)
    phase_plans: list[dict] = field(default_factory=list)
    asis_analysis: dict = field(default_factory=dict)
    tobe_direction: dict = field(default_factory=dict)
    feasibility_evidence: dict = field(default_factory=dict)
    executive_summary: dict = field(default_factory=dict)
    agent_rankings: dict = field(default_factory=dict)

    # --- Configuration (set at init, read by tools) ---
    workspace_path: str = ""
    top_k: int = 6
    report_focus: str = ""
    service_scope: list[str] = field(default_factory=list)
    output_dir: str = ""
    output_name: str = "rd_research_report"
    max_files: int = 1500
    extensions: list[str] = field(default_factory=lambda: [
        "md", "txt", "py", "java", "kt", "ts", "tsx", "json",
        "yml", "yaml", "properties", "xml", "ini", "cfg", "sh",
        "gradle", "toml",
    ])
    ignore_dirs: set[str] = field(default_factory=lambda: {
        ".git", ".idea", ".venv", "venv", "node_modules", "target",
        "build", "dist", ".gradle", ".mvn", "__pycache__", ".pytest_cache",
    })
    debate_rounds: int = 2
    version_tag: str = "V10"
    persona_dir: str | None = None

    # --- Execution log ---
    tool_history: list[dict] = field(default_factory=list)
    stage_log: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = uuid.uuid4().hex[:16]

    def summary_for_llm(self) -> str:
        """Return a concise text summary of current state for the LLM planner."""
        lines: list[str] = []

        # Personas
        if self.personas:
            lines.append(f"- Personas loaded: {len(self.personas)} agents")
        else:
            lines.append("- Personas: NOT loaded yet")

        # Workspace
        if self.workspace_summary:
            ws = self.workspace_summary
            lines.append(
                f"- Workspace scanned: {ws.total_files} files, "
                f"{len(ws.projects)} projects"
            )
        else:
            lines.append("- Workspace: NOT scanned yet")

        # Topic discovery
        if self.discoveries:
            names = [d.topic_name for d in self.discoveries[:5]]
            suffix = f" +{len(self.discoveries) - 5} more" if len(self.discoveries) > 5 else ""
            lines.append(
                f"- Topics discovered ({len(self.discoveries)}): "
                + ", ".join(names) + suffix
            )
        else:
            lines.append("- Topics: NOT discovered yet")

        # Workspace analysis
        if self.topic_states:
            lines.append(f"- Workspace analysis: {len(self.topic_states)} topics with evidence")
        else:
            lines.append("- Workspace analysis: NOT done yet")

        # Scoring
        if self.scores:
            lines.append(f"- Scoring: {len(self.scores)} topics scored")
        else:
            lines.append("- Scoring: NOT done yet")

        # Ranked
        if self.ranked:
            top3 = [r.get("topic_name", r.get("topic_id", "?")) for r in self.ranked[:3]]
            lines.append(f"- Ranking: {len(self.ranked)} topics ranked (top3: {', '.join(top3)})")

        # Deliberation
        if self.pipeline_decisions:
            lines.append(f"- Deliberation: {len(self.pipeline_decisions)} decisions")
        else:
            lines.append("- Deliberation: NOT done yet")

        # Consensus
        if self.consensus_summary:
            status = self.consensus_summary.get("status", "unknown")
            lines.append(f"- Consensus: {status}")
        else:
            lines.append("- Consensus: NOT done yet")

        # Research
        if self.research_sources:
            lines.append(f"- Research sources: {len(self.research_sources)} found")
        else:
            lines.append("- Research: NOT done yet")

        # Report artifacts
        report_parts = []
        if self.strategy_cards:
            report_parts.append("strategy_cards")
        if self.asis_analysis:
            report_parts.append("asis")
        if self.tobe_direction:
            report_parts.append("tobe")
        if self.feasibility_evidence:
            report_parts.append("feasibility")
        if self.executive_summary:
            report_parts.append("executive_summary")
        if report_parts:
            lines.append(f"- Report sections ready: {', '.join(report_parts)}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize key state for the final result."""
        return {
            "session_id": self.session_id,
            "user_request": self.user_request,
            "topics_discovered": len(self.discoveries),
            "topics_analyzed": len(self.topic_states),
            "topics_scored": len(self.scores),
            "decisions": len(self.pipeline_decisions),
            "consensus": self.consensus_summary.get("status", "pending"),
            "research_sources": len(self.research_sources),
            "tool_calls": len(self.tool_history),
        }
