"""LLM execution layer: provider-only (Gemini SDK).

Resolution order for ``run_llm_command()``:

1. Provider (Gemini) available -> ``provider.call()`` with auto tier routing
2. Provider fails -> return failure result as-is (no subprocess fallback)
3. Nothing available -> ``LLMResult(status="disabled")``
"""
from __future__ import annotations

import json
import logging
import time

from .llm_provider import LLMProvider, TIER_DEFAULT_TIMEOUTS, resolve_tier
from .types import LLMResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------

_cached_provider: LLMProvider | None = None
_provider_checked: bool = False


def _get_provider() -> LLMProvider | None:
    """Return the first available LLM provider (cached singleton)."""
    global _cached_provider, _provider_checked
    if _provider_checked:
        return _cached_provider
    from .gemini_provider import GeminiProvider

    provider = GeminiProvider()
    _cached_provider = provider if provider.is_available() else None
    _provider_checked = True
    return _cached_provider


# ---------------------------------------------------------------------------
# Provider path
# ---------------------------------------------------------------------------

def _run_via_provider(
    provider: LLMProvider,
    payload: dict,
    system_prompt: str | None,
    timeout: float,
) -> LLMResult:
    """Run an LLM call through a provider, returning an LLMResult."""
    tier = resolve_tier(payload)
    effective_timeout = max(30.0, timeout, TIER_DEFAULT_TIMEOUTS.get(tier, 60.0))

    prompt = system_prompt or payload.get("system_prompt", "")
    user_content = json.dumps(payload, ensure_ascii=False)

    t0 = time.monotonic()
    try:
        raw_text = provider.call(
            system_prompt=prompt,
            user_content=user_content,
            tier=tier,
            timeout=effective_timeout,
        )
    except Exception as exc:
        elapsed = time.monotonic() - t0
        logger.warning(
            "Provider %s failed (tier=%s, %.1fs): %s",
            provider.provider_name(), tier, elapsed, exc,
        )
        return LLMResult(
            status="failed",
            parsed={"status": "failed", "reason": f"Provider 호출 실패: {exc}"},
            elapsed_seconds=elapsed,
        )

    elapsed = time.monotonic() - t0

    if not raw_text:
        return LLMResult(
            status="failed",
            parsed={"status": "failed", "reason": "빈 응답"},
            raw_output="",
            elapsed_seconds=elapsed,
        )

    # Parse JSON from the response
    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        # Try extracting JSON block from mixed text
        start = raw_text.find("{")
        end = raw_text.rfind("}")
        if start >= 0 and end > start:
            try:
                result = json.loads(raw_text[start : end + 1])
            except json.JSONDecodeError:
                return LLMResult(
                    status="failed",
                    parsed={"status": "failed", "reason": "JSON 파싱 실패", "raw_output": raw_text[:400]},
                    raw_output=raw_text,
                    elapsed_seconds=elapsed,
                )
        else:
            return LLMResult(
                status="failed",
                parsed={"status": "failed", "reason": "JSON 파싱 실패", "raw_output": raw_text[:400]},
                raw_output=raw_text,
                elapsed_seconds=elapsed,
            )

    if not isinstance(result, dict):
        return LLMResult(
            status="failed",
            parsed={"status": "failed", "reason": "응답 형식이 dict가 아님"},
            raw_output=raw_text,
            elapsed_seconds=elapsed,
        )

    logger.debug(
        "Provider %s OK (tier=%s, %.1fs, %d chars)",
        provider.provider_name(), tier, elapsed, len(raw_text),
    )
    return LLMResult(status="ok", parsed=result, raw_output=raw_text, elapsed_seconds=elapsed)


# ---------------------------------------------------------------------------
# Public API (signature unchanged for caller compatibility)
# ---------------------------------------------------------------------------

def run_llm_command(
    payload: dict,
    command: str | None,
    timeout: float = 8.0,
    system_prompt: str | None = None,
    env_var: str | None = None,
) -> LLMResult:
    """Execute an LLM call via provider (Gemini SDK).

    Parameters
    ----------
    payload:
        JSON-serializable dict. Must contain ``"version"`` for tier routing.
    command:
        Legacy parameter, kept for caller compatibility. Ignored.
    timeout:
        Maximum wall-clock seconds.
    system_prompt:
        If provided, used as the LLM system prompt.
    env_var:
        Legacy parameter, kept for caller compatibility. Ignored.
    """
    provider = _get_provider()
    if provider is not None:
        return _run_via_provider(provider, payload, system_prompt, timeout)

    return LLMResult(status="disabled", parsed={"status": "disabled", "reason": "LLM provider 미설정"})
