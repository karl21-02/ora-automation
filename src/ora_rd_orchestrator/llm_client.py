"""Common LLM subprocess execution wrapper."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time

from .types import LLMResult


def run_llm_command(
    payload: dict,
    command: str | None,
    timeout: float = 8.0,
    system_prompt: str | None = None,
    env_var: str | None = None,
) -> LLMResult:
    """Execute an external LLM command via subprocess.

    The *command* (or env var) is expected to accept JSON on stdin
    and produce JSON on stdout.

    Parameters
    ----------
    payload:
        JSON-serializable dict sent to the command's stdin.
    command:
        Shell command string. Falls back to *env_var* if ``None``.
    timeout:
        Maximum wall-clock seconds.
    system_prompt:
        If provided, injected into ``payload["system_prompt"]`` before sending.
    env_var:
        Environment variable name used as fallback for *command*.
    """
    resolved_cmd = command
    if not resolved_cmd and env_var:
        resolved_cmd = os.getenv(env_var, "").strip() or None
    if not resolved_cmd:
        return LLMResult(status="disabled", parsed={"status": "disabled", "reason": "환경 변수/옵션 미설정"})

    try:
        args = shlex.split(resolved_cmd)
        if not args:
            return LLMResult(status="disabled", parsed={"status": "disabled", "reason": "실행 명령이 비어 있음"})
    except ValueError as exc:
        return LLMResult(status="failed", parsed={"status": "failed", "reason": f"명령 파싱 실패: {exc}"})

    if system_prompt:
        payload = {**payload, "system_prompt": system_prompt}

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            args=args,
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
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
        # fallback: extract trailing JSON block from mixed output
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
