from __future__ import annotations

import json
import logging
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)


class PlannerError(RuntimeError):
    pass


def _parse_json_response(text: str) -> dict[str, Any]:
    raw = text.strip()
    if not raw:
        raise PlannerError("planner returned empty response")
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    for line in reversed(lines):
        if not (line.startswith("{") and line.endswith("}")):
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    raise PlannerError("planner response is not valid JSON object")


def _normalize_env(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    env: dict[str, str] = {}
    for k, v in raw.items():
        key = str(k).strip()
        if not key:
            continue
        env[key] = str(v).strip()
    return env


def _normalize_pipeline_stages(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return ["analysis", "deliberation", "execution"]
    stages = [str(item).strip().lower() for item in raw if str(item).strip()]
    deduped: list[str] = []
    for stage in stages:
        if stage not in deduped:
            deduped.append(stage)
    if not deduped:
        deduped = ["analysis", "deliberation", "execution"]
    if "execution" not in deduped:
        deduped.append("execution")
    return deduped


def _normalize_decision(raw: Any, agent_role: str, target: str, prompt: str) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return {
            "owner": agent_role.upper(),
            "rationale": f"Planner output did not include structured decision for target={target}",
            "risk": "decision payload shape mismatch",
            "next_action": f"execute {target}",
            "payload": {"raw_decision": str(raw), "prompt": prompt},
        }

    owner = str(raw.get("owner", "")).strip() or agent_role.upper()
    rationale = str(raw.get("rationale", "")).strip() or f"execute {target} for prompt"
    risk = str(raw.get("risk", "")).strip() or "unspecified risk"
    next_action = str(raw.get("next_action", "")).strip() or f"execute {target}"
    due = raw.get("due")
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        payload = {}

    normalized: dict[str, Any] = {
        "owner": owner,
        "rationale": rationale,
        "risk": risk,
        "next_action": next_action,
        "payload": payload,
    }
    if due:
        normalized["due"] = due
    return normalized


def _normalize_plan(raw: dict[str, Any], prompt: str) -> dict[str, Any]:
    target = str(raw.get("target", "")).strip()
    if not target:
        raise PlannerError("planner output missing target")
    if target not in settings.allowed_targets:
        raise PlannerError(f"planner output target not allowed: {target}")

    requested_role = str(raw.get("agent_role", "")).strip().lower()
    if requested_role not in settings.agent_roles:
        requested_role = ""

    max_attempts_raw = raw.get("max_attempts")
    max_attempts = None
    if max_attempts_raw is not None:
        try:
            max_attempts = max(1, min(int(max_attempts_raw), 20))
        except Exception:
            max_attempts = None

    execution_command = str(raw.get("execution_command", "")).strip() or None
    rollback_command = str(raw.get("rollback_command", "")).strip() or None
    plan = {
        "target": target,
        "agent_role": requested_role or None,
        "env": _normalize_env(raw.get("env", {})),
        "max_attempts": max_attempts,
        "pipeline_stages": _normalize_pipeline_stages(raw.get("pipeline_stages")),
        "execution_command": execution_command,
        "rollback_command": rollback_command,
        "decision": _normalize_decision(raw.get("decision"), requested_role or "engineer", target, prompt),
        "planner_metadata": raw.get("planner_metadata", {}) if isinstance(raw.get("planner_metadata"), dict) else {},
    }
    return plan


def _get_gemini_provider():
    """Get a GeminiProvider instance, raising PlannerError if unavailable."""
    from ora_rd_orchestrator.gemini_provider import GeminiProvider

    provider = GeminiProvider()
    if not provider.is_available():
        raise PlannerError(
            "Gemini provider is not available. "
            "Check GOOGLE_APPLICATION_CREDENTIALS and GOOGLE_CLOUD_PROJECT_ID."
        )
    return provider


def run_llm_planner(
    prompt: str,
    context: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    provider = _get_gemini_provider()

    system_prompt = (
        "You are an orchestration planner. Given a user prompt, produce a JSON object "
        "that describes how to execute the requested task.\n\n"
        f"Allowed targets: {json.dumps(list(settings.allowed_targets))}\n"
        f"Allowed agent roles: {json.dumps(list(settings.agent_roles))}\n\n"
        "Required output fields (JSON object):\n"
        "- target: one of the allowed targets\n"
        "- agent_role: one of the allowed agent roles (or empty string)\n"
        "- env: dict of environment variable overrides\n"
        "- max_attempts: integer 1-20 or null\n"
        "- pipeline_stages: list of stages (analysis, deliberation, execution)\n"
        "- execution_command: shell command string or null\n"
        "- rollback_command: shell command string or null\n"
        "- decision: object with owner, rationale, risk, next_action, payload (or null)\n\n"
        "Respond with ONLY a valid JSON object, no markdown fences or extra text."
    )

    user_content = json.dumps(
        {"prompt": prompt, "context": context or {}},
        ensure_ascii=False,
    )

    timeout = float(timeout_seconds or settings.llm_planner_timeout_seconds)

    try:
        raw_text = provider.call(
            system_prompt=system_prompt,
            user_content=user_content,
            tier="flash",
            timeout=max(10.0, timeout),
        )
    except Exception as exc:
        raise PlannerError(f"Gemini provider call failed: {exc}") from exc

    if not raw_text:
        raise PlannerError("planner returned empty response")

    raw = _parse_json_response(raw_text)
    plan = _normalize_plan(raw, prompt=prompt)
    if not plan.get("planner_metadata"):
        plan["planner_metadata"] = {}
    plan["planner_metadata"]["planner_provider"] = "gemini"
    return plan
