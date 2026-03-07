"""Shared constants and helpers for orchestration plan parsing.

Extracted from the legacy ``ora_rd_orchestrator.chatbot`` module so that
``chat_router`` and ``dialog_engine`` no longer depend on it.
"""
from __future__ import annotations

import json


ALLOWED_TARGETS = {
    "run",
    "run-direct",
    "run-cycle",
    "run-loop",
    "run-cycle-deep",
    "run-single",
    "e2e-service",
    "e2e-service-all",
    "verify-sources",
}

ALLOWED_ENV_KEYS = {
    "TOP",
    "RUN_CYCLES",
    "VERIFY_ROUNDS",
    "VERIFY_TIMEOUT",
    "VERIFY_RETRY_DELAY",
    "DEBATE_ROUNDS",
    "ORCHESTRATION_PROFILE",
    "PIPELINE_STAGES",
    "PIPELINE_SERVICES",
    "PIPELINE_FEATURES",
    "LLM_DELIBERATION_CMD",
    "LLM_CONSENSUS_CMD",
    "PIPELINE_EXECUTION_COMMAND",
    "PIPELINE_ROLLBACK_COMMAND",
    "PIPELINE_RETRY_MAX",
    "PIPELINE_FAIL_DEFAULT",
    "FOCUS",
    "VERSION_TAG",
    "RUN_NAME",
    "SERVICE",
    "E2E_SERVICE",
    "E2E_TOOL",
    "E2E_SERVICE_MODE",
    "E2E_FAIL_FAST",
    "E2E_FORCE_CYPRESS",
    "E2E_PYTEST_ARGS",
}


def extract_json(text: str) -> dict:
    """Extract the first JSON object from *text*."""
    text = text.strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        payload = json.loads(text[start : end + 1])
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        return {}
    return {}


def coerce_plan(parsed: dict) -> tuple[str, dict[str, str], str]:
    """Validate and coerce a parsed plan dict into (target, env, reply)."""
    target = str(parsed.get("target", parsed.get("action", ""))).strip()
    if target not in ALLOWED_TARGETS:
        raise RuntimeError(f"unsupported target: {target}")

    env_raw = parsed.get("env", {})
    env: dict[str, str] = {}
    if isinstance(env_raw, dict):
        for key, value in env_raw.items():
            k = str(key).strip()
            if k in ALLOWED_ENV_KEYS:
                env[k] = str(value).strip()
    if target == "e2e-service" and "SERVICE" not in env and "E2E_SERVICE" not in env:
        env["SERVICE"] = "ai"
    reply = str(parsed.get("reply", "")).strip()
    return target, env, reply
