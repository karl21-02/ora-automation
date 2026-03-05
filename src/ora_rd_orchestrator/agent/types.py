"""Core types for the ReAct agent system.

Defines the data structures exchanged between the agent loop, tool registry,
and Gemini function-calling layer.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """A function call requested by the LLM."""
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = ""

    def __post_init__(self) -> None:
        if not self.call_id:
            self.call_id = uuid.uuid4().hex[:12]


@dataclass
class ToolResult:
    """Result of executing a single tool call."""
    call_id: str
    tool_name: str
    success: bool
    output: Any = None        # JSON-serializable
    error: str = ""
    elapsed_seconds: float = 0.0


@dataclass
class AgentMessage:
    """A single message in the agent conversation history.

    Roles:
      - "user": user text input
      - "model": LLM response (text and/or tool_calls)
      - "tool": tool execution results (sent back as "user" role in Gemini)
    """
    role: str  # "user" | "model" | "tool"
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)

    def to_gemini_content(self) -> dict:
        """Convert to Gemini API content format.

        Gemini expects:
          - user messages: role="user", parts=[{text: ...}]
          - model messages: role="model", parts=[{text: ...}, {functionCall: ...}]
          - tool results: role="user", parts=[{functionResponse: ...}]
            (Gemini uses "user" role for function responses)
        """
        if self.role == "tool":
            parts = []
            for tr in self.tool_results:
                response_payload: dict[str, Any] = {"name": tr.tool_name}
                if tr.success:
                    response_payload["response"] = _truncate_output(tr.output)
                else:
                    response_payload["response"] = {"error": tr.error}
                parts.append({"functionResponse": response_payload})
            return {"role": "user", "parts": parts}

        if self.role == "model":
            parts: list[dict] = []
            if self.content:
                parts.append({"text": self.content})
            for tc in self.tool_calls:
                parts.append({
                    "functionCall": {
                        "name": tc.tool_name,
                        "args": tc.arguments,
                    }
                })
            return {"role": "model", "parts": parts}

        # Default: user
        return {"role": "user", "parts": [{"text": self.content or ""}]}


@dataclass
class AgentConfig:
    """Configuration for the agent loop."""
    max_iterations: int = 20
    max_tool_errors: int = 5
    model_tier: str = "flash"
    temperature: float = 0.3
    timeout_per_call: float = 90.0
    tool_timeout: float = 30.0


class AgentStopReason:
    DONE = "done"
    MAX_ITERATIONS = "max_iterations"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MAX_OUTPUT_CHARS = 8000


def _truncate_output(output: Any) -> Any:
    """Truncate tool output if it exceeds the character limit."""
    if output is None:
        return {"result": "ok"}
    if isinstance(output, str):
        if len(output) > _MAX_OUTPUT_CHARS:
            return output[:_MAX_OUTPUT_CHARS] + "... [truncated]"
        return output
    if isinstance(output, dict):
        import json
        serialized = json.dumps(output, ensure_ascii=False, default=str)
        if len(serialized) > _MAX_OUTPUT_CHARS:
            return {"_truncated": True, "preview": serialized[:_MAX_OUTPUT_CHARS]}
        return output
    if isinstance(output, list):
        import json
        serialized = json.dumps(output, ensure_ascii=False, default=str)
        if len(serialized) > _MAX_OUTPUT_CHARS:
            return {"_truncated": True, "count": len(output), "preview": serialized[:_MAX_OUTPUT_CHARS]}
        return output
    return str(output)[:_MAX_OUTPUT_CHARS]
