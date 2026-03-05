"""LLM execution layer: provider-first with subprocess fallback.

Resolution order for ``run_llm_command()``:

1. ``ORA_RD_LLM_PREFER_SUBPROCESS=1`` **and** cmd present -> subprocess
2. Provider (Gemini) available -> ``provider.call()`` with auto tier routing
3. Provider fails **and** cmd present -> subprocess fallback
4. Nothing available -> ``LLMResult(status="disabled")``
"""
from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
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


def _prefer_subprocess() -> bool:
    return os.getenv("ORA_RD_LLM_PREFER_SUBPROCESS", "").strip() in ("1", "true", "yes")


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
# Subprocess path (original logic)
# ---------------------------------------------------------------------------

def _run_via_subprocess(
    payload: dict,
    command: str,
    system_prompt: str | None,
    timeout: float,
) -> LLMResult:
    """Execute an external LLM command via subprocess."""
    try:
        args = shlex.split(command)
        if not args:
            return LLMResult(status="disabled", parsed={"status": "disabled", "reason": "실행 명령이 비어 있음"})
    except ValueError as exc:
        return LLMResult(status="failed", parsed={"status": "failed", "reason": f"명령 파싱 실패: {exc}"})

    send_payload = payload
    if system_prompt:
        send_payload = {**payload, "system_prompt": system_prompt}

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            args=args,
            input=json.dumps(send_payload, ensure_ascii=False).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(1.0, timeout),
            check=False,
        )
    except Exception as exc:
        elapsed = time.monotonic() - t0
        return LLMResult(status="failed", parsed={"status": "failed", "reason": f"실행 실패: {exc}"}, elapsed_seconds=elapsed)

    elapsed = time.monotonic() - t0
    stderr = proc.stderr.decode("utf-8", errors="ignore").strip()
    raw_output = proc.stdout.decode("utf-8", errors="ignore").strip()

    if proc.returncode != 0:
        return LLMResult(
            status="failed",
            parsed={"status": "failed", "reason": f"명령 종료코드 {proc.returncode}", "stderr": stderr},
            raw_output=raw_output,
            elapsed_seconds=elapsed,
        )

    if not raw_output:
        return LLMResult(
            status="failed",
            parsed={"status": "failed", "reason": "빈 응답", "stderr": stderr},
            elapsed_seconds=elapsed,
        )

    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError:
        start = raw_output.find("{")
        end = raw_output.rfind("}")
        if start < 0 or end <= start:
            return LLMResult(
                status="failed",
                parsed={"status": "failed", "reason": "JSON 파싱 실패", "stderr": stderr, "raw_output": raw_output[:400]},
                raw_output=raw_output,
                elapsed_seconds=elapsed,
            )
        try:
            result = json.loads(raw_output[start : end + 1])
        except json.JSONDecodeError:
            return LLMResult(
                status="failed",
                parsed={"status": "failed", "reason": "JSON 파싱 실패", "stderr": stderr, "raw_output": raw_output[:400]},
                raw_output=raw_output,
                elapsed_seconds=elapsed,
            )

    if not isinstance(result, dict):
        return LLMResult(
            status="failed",
            parsed={"status": "failed", "reason": "응답 형식이 dict가 아님"},
            raw_output=raw_output,
            elapsed_seconds=elapsed,
        )

    return LLMResult(status="ok", parsed=result, raw_output=raw_output, elapsed_seconds=elapsed)


# ---------------------------------------------------------------------------
# Public API (signature unchanged)
# ---------------------------------------------------------------------------

def run_llm_command(
    payload: dict,
    command: str | None,
    timeout: float = 8.0,
    system_prompt: str | None = None,
    env_var: str | None = None,
) -> LLMResult:
    """Execute an LLM call with provider-first, subprocess-fallback routing.

    Parameters
    ----------
    payload:
        JSON-serializable dict. Must contain ``"version"`` for tier routing.
    command:
        Shell command string. Falls back to *env_var* if ``None``.
    timeout:
        Maximum wall-clock seconds.
    system_prompt:
        If provided, used as the LLM system prompt.
    env_var:
        Environment variable name used as fallback for *command*.
    """
    # Resolve subprocess command
    resolved_cmd = command
    if not resolved_cmd and env_var:
        resolved_cmd = os.getenv(env_var, "").strip() or None

    # 1. Prefer subprocess if explicitly requested and cmd available
    if _prefer_subprocess() and resolved_cmd:
        if system_prompt:
            payload = {**payload, "system_prompt": system_prompt}
        return _run_via_subprocess(payload, resolved_cmd, system_prompt, timeout)

    # 2. Try provider
    provider = _get_provider()
    if provider is not None:
        result = _run_via_provider(provider, payload, system_prompt, timeout)
        if result.status == "ok":
            return result
        # 3. Provider failed — fall back to subprocess if available
        if resolved_cmd:
            logger.info(
                "Provider %s failed, falling back to subprocess: %s",
                provider.provider_name(), resolved_cmd,
            )
            return _run_via_subprocess(payload, resolved_cmd, system_prompt, timeout)
        return result

    # 4. No provider — use subprocess if available
    if resolved_cmd:
        return _run_via_subprocess(payload, resolved_cmd, system_prompt, timeout)

    # 5. Nothing available
    return LLMResult(status="disabled", parsed={"status": "disabled", "reason": "LLM provider 미설정, subprocess 명령어 없음"})
