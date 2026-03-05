"""Report generation tool for the ReAct agent.

Wraps the full report generation pipeline (markdown + JSON output)
with the AgentState interface.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .state import AgentState
from .tool_registry import Tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------

def _handle_generate_full_report(state: AgentState, **kwargs: Any) -> dict:
    """Generate the final markdown + JSON report from accumulated state."""
    from ..config import FLAT_MODE_AGENTS, ORCHESTRATION_STAGES_DEFAULT
    from ..report_builder import (
        as_markdown,
        build_agent_rankings,
        build_research_queries,
        build_synergy_graph,
        to_json,
    )
    from ..topic_discovery import topics_to_keywords

    if not state.ranked:
        return {"error": "Ranking not available. Run scoring first."}

    selected = state.ranked[:state.top_k]
    topic_keywords = topics_to_keywords(state.discoveries) if state.discoveries else None

    # Build prerequisites
    agent_rankings = state.agent_rankings or build_agent_rankings(
        state.scores, top_k=state.top_k, agent_filter=FLAT_MODE_AGENTS,
    )
    queries = build_research_queries(selected, topic_keywords=topic_keywords, top_k=state.top_k)
    synergy_lines = build_synergy_graph(state.topic_states, selected)
    phases = state.phase_plans or []

    # Decisions as per-topic records
    agent_decisions: dict[str, list[dict]] = {}
    for d in state.pipeline_decisions:
        record = {
            "agent": d.owner,
            "decision": "review",
            "reason": d.rationale,
            "risk": d.risk,
            "next_action": d.next_action,
            "fail_label": d.fail_label,
            "due": d.due,
            "service": d.service,
        }
        agent_decisions.setdefault(d.topic_id, []).append(record)

    # Output paths
    output_dir = Path(state.output_dir) if state.output_dir else Path(".")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_name = state.output_name or "rd_research_report"

    # Generate markdown
    md_content = as_markdown(
        workspace=Path(state.workspace_path),
        top_topics=selected,
        states=state.topic_states,
        scores=state.scores,
        ranked=state.ranked,
        agent_rankings=agent_rankings,
        phases=phases,
        synergy_lines=synergy_lines,
        queries=queries,
        report_focus=state.report_focus,
        version_tag=state.version_tag,
        agent_definitions=state.agent_definitions,
        research_sources=state.research_sources,
        agent_decisions=agent_decisions,
        consensus_summary=state.consensus_summary,
        pipeline_decisions=[d.to_dict() for d in state.pipeline_decisions],
        pipeline_stage_log=state.stage_log,
        service_scope=state.service_scope,
        strategy_cards_prebuilt=state.strategy_cards or None,
        qa_verification=state.qa_verification or None,
        executive_summary=state.executive_summary or None,
        asis_analysis=state.asis_analysis or None,
        tobe_direction=state.tobe_direction or None,
        feasibility_evidence=state.feasibility_evidence or None,
    )

    md_path = output_dir / f"{output_name}.md"
    md_path.write_text(md_content, encoding="utf-8")

    # Generate JSON
    json_data = to_json(
        states=state.topic_states,
        scores=state.scores,
        scores_initial=None,
        ranked=state.ranked,
        phases=phases,
        report_focus=state.report_focus,
        version_tag=state.version_tag,
        research_sources=state.research_sources,
        topic_keywords=topic_keywords,
        selected_agent_decisions=agent_decisions,
        consensus_summary=state.consensus_summary,
        pipeline_decisions=[d.to_dict() for d in state.pipeline_decisions],
        pipeline_stage_log=state.stage_log,
        service_scope=state.service_scope,
        strategy_cards_prebuilt=state.strategy_cards or None,
        qa_verification=state.qa_verification or None,
        executive_summary=state.executive_summary or None,
        asis_analysis=state.asis_analysis or None,
        tobe_direction=state.tobe_direction or None,
        feasibility_evidence=state.feasibility_evidence or None,
        precomputed_agent_rankings=agent_rankings,
        precomputed_research_queries=queries,
    )

    json_path = output_dir / f"{output_name}.json"
    json_path.write_text(
        json.dumps(json_data, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    return {
        "markdown_path": str(md_path),
        "json_path": str(json_path),
        "topics_in_report": len(selected),
        "markdown_length": len(md_content),
    }


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_report_tools() -> list[Tool]:
    """Return report generation tools for registration."""
    return [
        Tool(
            name="generate_full_report",
            description="최종 마크다운 및 JSON 보고서를 생성합니다. 스코어링과 합의가 완료된 후 실행합니다.",
            parameters=[],
            handler=_handle_generate_full_report,
            category="report",
        ),
    ]
