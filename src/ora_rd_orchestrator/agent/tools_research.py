"""Research tools for the ReAct agent.

Wraps existing research query and source-building functions
with the AgentState interface.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .state import AgentState
from .tool_registry import Tool, ToolParameter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool handler
# ---------------------------------------------------------------------------

def _handle_search_research_sources(
    state: AgentState, top_k: int = 0, **kwargs: Any
) -> dict:
    """Search academic sources (ArXiv, Crossref, OpenAlex, etc.)."""
    from ..research import build_sources_file
    from ..topic_discovery import topics_to_keywords

    if not state.ranked:
        return {"error": "Ranking not available. Call score_all_topics first."}

    effective_top_k = top_k if top_k > 0 else state.top_k
    selected = state.ranked[:effective_top_k]
    topic_keywords = topics_to_keywords(state.discoveries) if state.discoveries else None

    output_dir = Path(state.output_dir) if state.output_dir else Path(".")
    output_dir.mkdir(parents=True, exist_ok=True)

    sources, warnings = build_sources_file(
        output_dir=output_dir,
        version_tag=state.version_tag,
        report_focus=state.report_focus,
        top_topics=selected,
        topic_keywords=topic_keywords,
    )
    state.research_sources = sources

    return {
        "sources_found": len(sources),
        "warnings": len(warnings),
        "providers": list({s.get("provider", "unknown") for s in sources}),
    }


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_research_tools() -> list[Tool]:
    """Return research tools for registration."""
    return [
        Tool(
            name="search_research_sources",
            description="ArXiv, Crossref, OpenAlex 등에서 선정된 토픽에 관한 학술 논문을 검색합니다.",
            parameters=[
                ToolParameter(
                    name="top_k",
                    type="integer",
                    description="검색 대상 상위 토픽 수 (기본값: state의 top_k 사용)",
                ),
            ],
            handler=_handle_search_research_sources,
            category="research",
        ),
    ]
