from __future__ import annotations

import json
import shlex
import subprocess
from typing import Any

from .config import settings


class PlannerError(RuntimeError):
    pass


def _parse_json_from_stdout(stdout: str) -> dict[str, Any]:
    raw = stdout.strip()
    if not raw:
        raise PlannerError("planner returned empty stdout")
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
    raise PlannerError("planner stdout is not valid JSON object")


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


def run_llm_planner(
    prompt: str,
    context: dict[str, Any] | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    cmd = settings.llm_planner_cmd.strip()
    if not cmd:
        raise PlannerError("ORA_AUTOMATION_LLM_PLANNER_CMD is not configured")

    payload = {
        "prompt": prompt,
        "context": context or {},
        "allowed_targets": list(settings.allowed_targets),
        "allowed_agent_roles": list(settings.agent_roles),
        "required_output_fields": [
            "target",
            "agent_role",
            "env",
            "max_attempts",
            "pipeline_stages",
            "execution_command",
            "rollback_command",
            "decision",
        ],
    }
    timeout = float(timeout_seconds or settings.llm_planner_timeout_seconds)
    proc = subprocess.run(
        shlex.split(cmd),
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(settings.automation_root),
        timeout=max(1.0, timeout),
        check=False,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or b"").decode("utf-8", errors="ignore").strip()
        raise PlannerError(f"planner command failed (exit={proc.returncode}): {stderr[:800]}")

    stdout = (proc.stdout or b"").decode("utf-8", errors="ignore")
    raw = _parse_json_from_stdout(stdout)
    plan = _normalize_plan(raw, prompt=prompt)
    if not plan.get("planner_metadata"):
        plan["planner_metadata"] = {}
    plan["planner_metadata"]["planner_command"] = cmd
    return plan

