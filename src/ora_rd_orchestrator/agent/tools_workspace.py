"""Workspace-related tools for the ReAct agent.

Wraps existing workspace, persona, and topic discovery functions
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
# Tool handlers
# ---------------------------------------------------------------------------

def _handle_load_personas(state: AgentState, **kwargs: Any) -> dict:
    """Load all agent personas from YAML files into state."""
    from ..personas import PersonaRegistry, default_persona_dir

    persona_dir = state.persona_dir or str(default_persona_dir())
    registry = PersonaRegistry(Path(persona_dir))
    personas = registry.load_all()
    agent_definitions = registry.to_agent_definitions()

    state.personas = personas
    state.agent_definitions = agent_definitions

    return {
        "loaded": len(personas),
        "agents": sorted(personas.keys()),
    }


def _handle_collect_workspace_summary(
    state: AgentState, max_files: int = 500, **kwargs: Any
) -> dict:
    """Scan workspace and build summary for topic discovery."""
    from ..workspace import collect_workspace_summary

    ws = collect_workspace_summary(
        workspace=Path(state.workspace_path),
        extensions=state.extensions,
        ignore_dirs=state.ignore_dirs,
        max_files=max_files,
    )
    state.workspace_summary = ws

    return {
        "total_files": ws.total_files,
        "projects": len(ws.projects),
        "file_types": len(ws.file_types),
        "snippets": len(ws.representative_snippets),
    }


def _handle_discover_topics(
    state: AgentState, domain: str = "voice AI", **kwargs: Any
) -> dict:
    """Discover R&D topics via LLM or legacy fallback."""
    from ..topic_discovery import discover_topics

    discoveries = discover_topics(
        workspace_summary=state.workspace_summary,
        domain=domain,
    )
    state.discoveries = discoveries

    return {
        "count": len(discoveries),
        "topics": [
            {"topic_id": d.topic_id, "topic_name": d.topic_name, "confidence": d.confidence}
            for d in discoveries
        ],
    }


def _handle_analyze_workspace(state: AgentState, **kwargs: Any) -> dict:
    """Scan workspace files and build topic states with evidence."""
    from ..workspace import analyze_workspace

    topic_states = analyze_workspace(
        workspace=Path(state.workspace_path),
        extensions=state.extensions,
        ignore_dirs=state.ignore_dirs,
        max_files=state.max_files,
        history_files=[],
        topic_discoveries=state.discoveries if state.discoveries else None,
    )
    state.topic_states = topic_states

    return {
        "topics_analyzed": len(topic_states),
        "summary": {
            tid: {
                "topic_name": ts.topic_name,
                "keyword_hits": ts.keyword_hits,
                "code_hits": ts.code_hits,
                "evidence_count": len(ts.evidence),
            }
            for tid, ts in list(topic_states.items())[:10]
        },
    }


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_workspace_tools() -> list[Tool]:
    """Return workspace-related tools for registration."""
    return [
        Tool(
            name="load_personas",
            description="에이전트 페르소나를 YAML 파일에서 로드합니다. 분석 시작 전에 반드시 실행해야 합니다.",
            parameters=[],
            handler=_handle_load_personas,
            category="workspace",
        ),
        Tool(
            name="collect_workspace_summary",
            description="워크스페이스 파일을 스캔하여 프로젝트 구조와 코드 요약을 생성합니다. 토픽 발견 전에 실행합니다.",
            parameters=[
                ToolParameter(
                    name="max_files",
                    type="integer",
                    description="스캔할 최대 파일 수 (기본값: 500)",
                ),
            ],
            handler=_handle_collect_workspace_summary,
            category="workspace",
        ),
        Tool(
            name="discover_topics",
            description="LLM 또는 레거시 방식으로 R&D 토픽을 발견합니다. workspace_summary가 필요합니다.",
            parameters=[
                ToolParameter(
                    name="domain",
                    type="string",
                    description="분석 도메인 (예: 'voice AI', 'fintech'). 기본값: 'voice AI'",
                ),
            ],
            handler=_handle_discover_topics,
            category="workspace",
        ),
        Tool(
            name="analyze_workspace",
            description="발견된 토픽을 기반으로 워크스페이스를 분석하여 토픽별 증거를 수집합니다. discover_topics 이후 실행합니다.",
            parameters=[],
            handler=_handle_analyze_workspace,
            category="workspace",
        ),
    ]
