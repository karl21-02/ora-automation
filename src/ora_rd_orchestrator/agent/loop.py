"""Core ReAct agent loop.

Implements the Reason + Act pattern: the LLM reasons about the current state,
optionally calls a tool, observes the result, and repeats until done or
max iterations are reached.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from .gemini_fc import call_with_tools
from .planner_prompt import build_planner_system_prompt
from .state import AgentState
from .tool_registry import ToolRegistry
from .types import AgentConfig, AgentMessage, AgentStopReason, ToolCall, ToolResult

logger = logging.getLogger(__name__)


class AgentLoop:
    """ReAct agent loop that orchestrates LLM planning and tool execution."""

    def __init__(self, registry: ToolRegistry, config: AgentConfig | None = None) -> None:
        self.registry = registry
        self.config = config or AgentConfig()
        self._history: list[AgentMessage] = []

    def run(self, user_message: str, state: AgentState) -> dict[str, Any]:
        """Run the agent loop until completion or limits are reached.

        Returns a dict with:
          - response: final text from the LLM
          - state: serialized AgentState
          - stop_reason: "done" | "max_iterations" | "error"
          - iterations: number of loop iterations executed
        """
        from ..gemini_provider import GeminiProvider

        provider = GeminiProvider()
        if not provider.is_available():
            return {
                "response": "Gemini provider is not available. Check GOOGLE_APPLICATION_CREDENTIALS and GOOGLE_CLOUD_PROJECT_ID.",
                "state": state.to_dict(),
                "stop_reason": AgentStopReason.ERROR,
                "iterations": 0,
            }

        state.user_request = user_message
        self._history = [AgentMessage(role="user", content=user_message)]

        consecutive_errors = 0
        final_text = ""

        for iteration in range(1, self.config.max_iterations + 1):
            logger.info("Agent iteration %d/%d", iteration, self.config.max_iterations)

            # Build system prompt with current state
            system_prompt = build_planner_system_prompt(state, self.registry)
            contents = [msg.to_gemini_content() for msg in self._history]
            tools = self.registry.to_gemini_tools()

            # Call LLM with function calling
            try:
                response = call_with_tools(
                    provider=provider,
                    system_prompt=system_prompt,
                    contents=contents,
                    tools=tools,
                    tier=self.config.model_tier,
                    timeout=self.config.timeout_per_call,
                    temperature=self.config.temperature,
                )
            except Exception as exc:
                logger.error("LLM call failed at iteration %d: %s", iteration, exc)
                consecutive_errors += 1
                if consecutive_errors >= self.config.max_tool_errors:
                    return {
                        "response": f"LLM 호출이 연속 {consecutive_errors}회 실패했습니다: {exc}",
                        "state": state.to_dict(),
                        "stop_reason": AgentStopReason.ERROR,
                        "iterations": iteration,
                    }
                # Add a synthetic tool result so conversation can continue
                self._history.append(AgentMessage(
                    role="model",
                    content=f"[LLM call error: {str(exc)[:200]}]",
                ))
                continue

            # No tool calls → LLM is done, return text response
            if not response.tool_calls:
                final_text = response.content
                self._history.append(response)
                logger.info("Agent completed with text response at iteration %d", iteration)
                return {
                    "response": final_text,
                    "state": state.to_dict(),
                    "stop_reason": AgentStopReason.DONE,
                    "iterations": iteration,
                }

            # Add model response to history
            self._history.append(response)

            # Execute each tool call
            tool_results: list[ToolResult] = []
            for tc in response.tool_calls:
                logger.info("Executing tool: %s(%s)", tc.tool_name, _summarize_args(tc.arguments))

                result = self.registry.execute(
                    tool_name=tc.tool_name,
                    arguments=tc.arguments,
                    state=state,
                    call_id=tc.call_id,
                    timeout=self.config.tool_timeout,
                )
                tool_results.append(result)

                # Track in state
                state.tool_history.append({
                    "iteration": iteration,
                    "tool": tc.tool_name,
                    "arguments": tc.arguments,
                    "success": result.success,
                    "elapsed": result.elapsed_seconds,
                    "error": result.error if not result.success else "",
                })

                if result.success:
                    consecutive_errors = 0
                else:
                    consecutive_errors += 1
                    logger.warning(
                        "Tool %s failed (consecutive=%d): %s",
                        tc.tool_name, consecutive_errors, result.error,
                    )

            # Add tool results to history
            self._history.append(AgentMessage(
                role="tool",
                tool_results=tool_results,
            ))

            # Check consecutive error limit
            if consecutive_errors >= self.config.max_tool_errors:
                return {
                    "response": f"연속 {consecutive_errors}회 도구 실행 에러로 중단합니다.",
                    "state": state.to_dict(),
                    "stop_reason": AgentStopReason.ERROR,
                    "iterations": iteration,
                }

            # If the model also produced text alongside tool calls, note it
            if response.content:
                logger.info("Model text (with tools): %s", response.content[:200])

        # Max iterations reached
        return {
            "response": final_text or "최대 반복 횟수에 도달했습니다.",
            "state": state.to_dict(),
            "stop_reason": AgentStopReason.MAX_ITERATIONS,
            "iterations": self.config.max_iterations,
        }


def _summarize_args(args: dict[str, Any]) -> str:
    """Create a short summary of arguments for logging."""
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 50:
            s = s[:50] + "..."
        parts.append(f"{k}={s}")
    return ", ".join(parts)
