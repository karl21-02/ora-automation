"""ReAct autonomous agent system for Ora R&D Orchestrator.

Public API:
    run_agent_loop()        — run the full ReAct agent loop
    build_default_registry() — create a ToolRegistry with all default tools
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .loop import AgentLoop
from .state import AgentState
from .tool_registry import Tool, ToolRegistry
from .tools_report import register_report_tools
from .tools_research import register_research_tools
from .tools_scoring import register_scoring_tools
from .tools_workspace import register_workspace_tools
from .types import AgentConfig


def build_default_registry() -> ToolRegistry:
    """Create a ToolRegistry populated with all default tools."""
    registry = ToolRegistry()
    for tool in register_workspace_tools():
        registry.register(tool)
    for tool in register_scoring_tools():
        registry.register(tool)
    for tool in register_research_tools():
        registry.register(tool)
    for tool in register_report_tools():
        registry.register(tool)
    return registry


def run_agent_loop(
    user_message: str,
    workspace_path: str = ".",
    top_k: int = 6,
    report_focus: str = "",
    service_scope: list[str] | None = None,
    output_dir: str = ".",
    output_name: str = "rd_research_report",
    max_iterations: int = 20,
    model_tier: str = "flash",
    persona_dir: str | None = None,
) -> dict[str, Any]:
    """High-level entry point: run the ReAct agent loop.

    Args:
        user_message: Natural language request from the user.
        workspace_path: Path to the workspace to analyze.
        top_k: Number of top topics to select.
        report_focus: Optional focus label for the report.
        service_scope: Optional service scope filter.
        output_dir: Directory for report output.
        output_name: Base filename for reports.
        max_iterations: Maximum agent loop iterations.
        model_tier: Gemini model tier ("lite", "flash", "pro").
        persona_dir: Optional custom persona YAML directory.

    Returns:
        Dict with keys: response, state, stop_reason, iterations.
    """
    registry = build_default_registry()
    config = AgentConfig(
        max_iterations=max_iterations,
        model_tier=model_tier,
    )

    state = AgentState(
        workspace_path=str(Path(workspace_path).expanduser().resolve()),
        top_k=top_k,
        report_focus=report_focus,
        service_scope=service_scope or [],
        output_dir=str(Path(output_dir).expanduser().resolve()),
        output_name=output_name,
        persona_dir=persona_dir,
    )

    loop = AgentLoop(registry=registry, config=config)
    return loop.run(user_message=user_message, state=state)


__all__ = [
    "build_default_registry",
    "run_agent_loop",
    "AgentConfig",
    "AgentLoop",
    "AgentState",
    "Tool",
    "ToolRegistry",
]
