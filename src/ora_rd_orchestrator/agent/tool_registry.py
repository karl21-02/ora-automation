"""Tool registry for the ReAct agent.

Manages tool definitions, converts them to Gemini function declarations,
and executes tool handlers with timeout and error handling.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from typing import Any, Callable

from .state import AgentState
from .types import ToolResult

logger = logging.getLogger(__name__)


@dataclass
class ToolParameter:
    """A single parameter for a tool function declaration."""
    name: str
    type: str = "string"  # "string" | "number" | "integer" | "boolean" | "object" | "array"
    description: str = ""
    required: bool = False
    enum: list[str] | None = None


@dataclass
class Tool:
    """A callable tool exposed to the LLM planner."""
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    handler: Callable[..., Any] = field(default=lambda **kw: None)
    category: str = ""

    def to_gemini_declaration(self) -> dict:
        """Convert to Gemini functionDeclarations entry."""
        properties: dict[str, Any] = {}
        required_list: list[str] = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type.upper() if param.type in ("string", "number", "integer", "boolean") else "STRING",
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            if param.required:
                required_list.append(param.name)

        decl: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
        }
        if properties:
            schema: dict[str, Any] = {
                "type": "OBJECT",
                "properties": properties,
            }
            if required_list:
                schema["required"] = required_list
            decl["parameters"] = schema

        return decl


class ToolRegistry:
    """Registry of all available tools for the agent."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def to_gemini_tools(self) -> list[dict]:
        """Return Gemini-formatted tools list: [{"functionDeclarations": [...]}]."""
        declarations = [tool.to_gemini_declaration() for tool in self._tools.values()]
        return [{"functionDeclarations": declarations}]

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        state: AgentState,
        call_id: str = "",
        timeout: float = 30.0,
    ) -> ToolResult:
        """Execute a tool by name with timeout protection."""
        tool = self.get(tool_name)
        if tool is None:
            return ToolResult(
                call_id=call_id,
                tool_name=tool_name,
                success=False,
                error=f"Unknown tool: {tool_name}",
            )

        start = time.monotonic()
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(tool.handler, state=state, **arguments)
                try:
                    result = future.result(timeout=timeout)
                except FuturesTimeout:
                    elapsed = time.monotonic() - start
                    logger.warning("Tool %s timed out after %.1fs", tool_name, elapsed)
                    return ToolResult(
                        call_id=call_id,
                        tool_name=tool_name,
                        success=False,
                        error=f"Tool execution timed out after {elapsed:.1f}s",
                        elapsed_seconds=elapsed,
                    )

            elapsed = time.monotonic() - start
            logger.info("Tool %s completed in %.1fs", tool_name, elapsed)
            return ToolResult(
                call_id=call_id,
                tool_name=tool_name,
                success=True,
                output=result,
                elapsed_seconds=elapsed,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.error("Tool %s failed: %s", tool_name, exc, exc_info=True)
            return ToolResult(
                call_id=call_id,
                tool_name=tool_name,
                success=False,
                error=str(exc)[:500],
                elapsed_seconds=elapsed,
            )
