"""Gemini function-calling wrapper.

Uses composition (not inheritance) with the existing GeminiProvider to add
native function calling support. The existing ``GeminiProvider.call()``
method is NOT modified — this module provides a standalone ``call_with_tools()``
function that reuses the provider's auth and region logic.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from ..gemini_provider import GeminiProvider, _get_gemini_token, _urlopen
from ..llm_provider import TIER_DEFAULT_TIMEOUTS
from .types import AgentMessage, ToolCall

logger = logging.getLogger(__name__)


def call_with_tools(
    provider: GeminiProvider,
    system_prompt: str,
    contents: list[dict],
    tools: list[dict],
    tier: str = "flash",
    timeout: float = 90.0,
    temperature: float = 0.3,
) -> AgentMessage:
    """Call Gemini with native function calling support.

    Unlike ``GeminiProvider.call()`` which forces ``responseMimeType: "application/json"``,
    this function omits it so Gemini can freely return text and/or functionCall parts.

    Args:
        provider: GeminiProvider instance (used for model/location resolution).
        system_prompt: System instruction text.
        contents: Gemini-format conversation history (list of content dicts).
        tools: Gemini-format tool declarations [{"functionDeclarations": [...]}].
        tier: Model tier ("lite", "flash", "pro").
        timeout: HTTP request timeout in seconds.
        temperature: Sampling temperature.

    Returns:
        AgentMessage with role="model", containing text content and/or tool_calls.
    """
    import os
    from urllib import error, request

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "").strip()
    if not project_id:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT_ID not set")

    model = provider._resolve_model(tier)
    locations = provider._resolve_locations()
    effective_timeout = timeout or TIER_DEFAULT_TIMEOUTS.get(tier, 60.0)

    token = _get_gemini_token()

    body: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
        },
    }
    if tools:
        body["tools"] = tools

    body_bytes = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")

    last_error: Exception | None = None
    for location in locations:
        url = (
            f"https://{location}-aiplatform.googleapis.com/v1/"
            f"projects/{project_id}/locations/{location}"
            f"/publishers/google/models/{model}:generateContent"
        )
        req = request.Request(
            url=url,
            data=body_bytes,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with _urlopen(req, timeout=effective_timeout) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            payload = json.loads(raw)
            return _parse_gemini_response(payload)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            last_error = RuntimeError(
                f"Gemini FC HTTP {exc.code} at {location}: {detail[:600]}"
            )
            logger.warning("Gemini FC %s @ %s failed: HTTP %d", model, location, exc.code)
            continue
        except Exception as exc:
            last_error = exc
            logger.warning("Gemini FC %s @ %s failed: %s", model, location, exc)
            continue

    raise last_error or RuntimeError("All Gemini locations failed for function calling")


def _parse_gemini_response(payload: dict) -> AgentMessage:
    """Parse Gemini response into an AgentMessage.

    Gemini can return a mix of text parts and functionCall parts in a single
    response. We collect both.
    """
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("Gemini FC response missing candidates")

    content = candidates[0].get("content", {})
    parts = content.get("parts", [])

    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []

    if isinstance(parts, list):
        for part in parts:
            if not isinstance(part, dict):
                continue
            if "text" in part:
                text_parts.append(str(part["text"]))
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append(ToolCall(
                    tool_name=fc.get("name", ""),
                    arguments=fc.get("args", {}),
                ))

    return AgentMessage(
        role="model",
        content="\n".join(text_parts).strip(),
        tool_calls=tool_calls,
    )
