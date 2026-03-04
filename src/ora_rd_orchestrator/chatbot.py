from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from pathlib import Path


CHAT_PLANNER_CMD_ENV = "ORA_RD_CHAT_PLANNER_CMD"
CHAT_PLANNER_TIMEOUT_DEFAULT = 12.0

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


def _extract_json(text: str) -> dict:
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


def _run_planner(planner_cmd: str, payload: dict, timeout: float) -> dict:
    args = shlex.split(planner_cmd)
    proc = subprocess.run(
        args=args,
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=max(1.0, timeout),
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"planner failed(exit={proc.returncode}): {proc.stderr.decode('utf-8', errors='ignore')}"
        )
    parsed = _extract_json(proc.stdout.decode("utf-8", errors="ignore"))
    if not parsed:
        raise RuntimeError("planner returned invalid JSON")
    return parsed


def _coerce_plan(parsed: dict) -> tuple[str, dict[str, str], str]:
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


def _build_make_command(target: str, env: dict[str, str]) -> list[str]:
    cmd = ["make", target]
    for key in sorted(env.keys()):
        cmd.append(f"{key}={env[key]}")
    return cmd


def _default_payload(message: str) -> dict:
    return {
        "instruction": (
            "You are an orchestration planner for ora-automation. "
            "Return JSON only. Decide one make target and env overrides."
        ),
        "allowed_targets": sorted(ALLOWED_TARGETS),
        "allowed_env_keys": sorted(ALLOWED_ENV_KEYS),
        "policy": [
            "Prefer run-cycle for R&D research requests.",
            "Prefer e2e-service or e2e-service-all for QA requests.",
            "Set ORCHESTRATION_PROFILE=strict only when user asks deep/strict deliberation.",
            "Keep env minimal.",
        ],
        "required_output_schema": {
            "target": "one of allowed_targets",
            "env": {"KEY": "VALUE"},
            "reply": "short explanation for user",
        },
        "user_message": message,
    }


def _execute_make(project_root: Path, target: str, env_overrides: dict[str, str], dry_run: bool) -> int:
    cmd = _build_make_command(target, env_overrides)
    printable = " ".join(shlex.quote(part) for part in cmd)
    print(f"[chatbot] plan -> {printable}")
    if dry_run:
        print("[chatbot] dry-run enabled; command not executed.")
        return 0
    proc = subprocess.run(cmd, cwd=str(project_root), check=False)
    return int(proc.returncode)


def _chat_loop(project_root: Path, planner_cmd: str, timeout: float, dry_run: bool) -> int:
    print("ora-automation chatbot ready. type 'exit' to quit.")
    while True:
        try:
            message = input("you> ").strip()
        except EOFError:
            print("")
            return 0
        if not message:
            continue
        if message.lower() in {"exit", "quit"}:
            return 0
        payload = _default_payload(message)
        try:
            planned = _run_planner(planner_cmd, payload=payload, timeout=timeout)
            target, env, reply = _coerce_plan(planned)
        except Exception as exc:
            print(f"[chatbot] planning error: {exc}")
            continue
        if reply:
            print(f"bot> {reply}")
        code = _execute_make(project_root, target=target, env_overrides=env, dry_run=dry_run)
        print(f"[chatbot] exit={code}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ora-automation-chatbot",
        description="Natural-language chatbot runner for ora-automation orchestrations.",
    )
    parser.add_argument(
        "--workspace",
        default=".",
        help="Ora workspace root (default: .)",
    )
    parser.add_argument(
        "--planner-cmd",
        default=None,
        help=f"LLM planner command (JSON stdin/stdout). Fallback env: {CHAT_PLANNER_CMD_ENV}",
    )
    parser.add_argument(
        "--message",
        default="",
        help="Single-shot user message. Empty -> interactive mode.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=CHAT_PLANNER_TIMEOUT_DEFAULT,
        help=f"Planner timeout seconds (default: {CHAT_PLANNER_TIMEOUT_DEFAULT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show command only, do not execute make.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).expanduser().resolve()
    project_root = workspace / "ora-automation"
    if not project_root.exists():
        # support launching from ora-automation itself
        if workspace.name == "ora-automation":
            project_root = workspace
        else:
            raise SystemExit(f"[error] ora-automation not found under workspace: {workspace}")

    planner_cmd = (args.planner_cmd or os.getenv(CHAT_PLANNER_CMD_ENV, "")).strip()
    if not planner_cmd:
        raise SystemExit(
            f"[error] planner command is required. Set --planner-cmd or {CHAT_PLANNER_CMD_ENV}."
        )

    timeout = max(1.0, float(args.timeout))
    if args.message.strip():
        payload = _default_payload(args.message.strip())
        planned = _run_planner(planner_cmd, payload=payload, timeout=timeout)
        target, env, reply = _coerce_plan(planned)
        if reply:
            print(f"bot> {reply}")
        return _execute_make(project_root, target=target, env_overrides=env, dry_run=args.dry_run)

    return _chat_loop(project_root, planner_cmd=planner_cmd, timeout=timeout, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
