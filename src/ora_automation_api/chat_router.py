from __future__ import annotations

import json
import logging
import os
import re
import ssl
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import update
from sqlalchemy.orm import Session

from .plan_utils import (
    ALLOWED_ENV_KEYS,
    ALLOWED_TARGETS,
    coerce_plan as _coerce_plan,
    extract_json as _extract_json,
)
from ora_rd_orchestrator.gemini_provider import _get_ssl_context

from .config import settings
from .database import SessionLocal, get_db
from .dialog_engine import (
    DialogContext,
    DialogState,
    IntentType,
    OrgRecommendationResult,
    coerce_proposed_plans,
    merge_slots,
    recommend_org,
    run_stage1,
    run_stage2_stream,
    run_stage2_sync,
)
from .models import ChatConversation, ChatMessageRow, Organization, OrganizationChapter, OrganizationSilo
from .scheduling_handler import ScheduleValidationError, create_scheduled_job_from_slots
from .schemas import (
    ChatChoice,
    ChatMessageRead,
    ChatPlan,
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationDetail,
    ConversationList,
    ConversationRead,
    ConversationUpdate,
    OrgRecommendOption,
    ProjectInfo,
    ReportListItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])


class StaleDialogError(Exception):
    """Raised when dialog_context optimistic lock fails (concurrent update)."""
    pass


@contextmanager
def _session_scope() -> Generator[Session, None, None]:
    """Open a SessionLocal, commit on success, always close."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# Pre-compiled regex patterns
_RE_JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_RE_JSON_BLOCK_STRIP = re.compile(r"```json\s*\{.*?\}\s*```", re.DOTALL)

# ── Gemini direct call (mirrors scripts/llm_round_openai.py pattern) ─────

_SYSTEM_PROMPT = """\
You are {assistant_name}, a friendly R&D orchestration assistant for the ora-automation platform.

Your job:
1. Chat naturally with the user to understand what they want to do.
2. When you have enough information to execute an orchestration, include a JSON plan block.
3. If the user's intent is still unclear, ask clarifying questions. Do NOT generate a plan until you are confident.

IMPORTANT — Clarification-first policy:
- ALWAYS ask what the user wants to research/test/analyze BEFORE showing a project picker or generating a plan.
- For research: ask what topic, strategy, or area they want to focus on. Example: "어떤 주제에 대해 리서치하고 싶으세요? (예: 인증 시스템 개선, API 성능 최적화, 신규 기능 전략 등)"
- For QA/testing: ask which service or test scope they want. Example: "어떤 서비스를 테스트할까요? 전체 E2E인가요, 특정 서비스인가요?"
- Only after the user provides a clear topic/direction, THEN ask which projects OR show the project picker.
- Never jump straight to plan generation or project selection from a vague request like "리서치하고 싶어" or "테스트 해줘".

Available Ora projects:
{project_list}

Available make targets (allowed_targets):
{allowed_targets}

Available env keys you can set:
{allowed_env_keys}

Rules:
- Prefer run-cycle for R&D research requests.
- Prefer e2e-service or e2e-service-all for QA/testing requests.
- Set ORCHESTRATION_PROFILE=strict only when user explicitly asks for deep/strict deliberation.
- Keep env minimal — only set keys the user mentioned or that are clearly needed.
- For e2e-service, always set SERVICE (default "ai") unless user specifies otherwise.
- For run-cycle, ALWAYS set FOCUS to the user's research topic/direction. Never leave FOCUS empty.

CRITICAL — Project picker rule:
- Whenever the user asks which projects are available, or you need to ask which project(s) to target, you MUST include the project_select JSON block below. NEVER list project names as plain text.
- This includes responses to questions like "어떤 프로젝트가 있어?", "프로젝트 목록 보여줘", or when you want to ask the user to pick projects.

When you have confirmed the topic and need the user to select projects, show the project picker:
```json
{{"project_select": true, "message": "어떤 프로젝트를 검사할까요?"}}
```
This tells the system to show the user a project picker UI with checkboxes.
Do NOT include plan_ready. After the user selects projects, they will tell you which ones they chose.
Do NOT list project names in your text reply. The system will render the picker UI automatically.

When you are ready to propose a plan for a SINGLE project, include EXACTLY this JSON block at the END of your message:
```json
{{"target": "<target>", "env": {{"KEY": "VALUE"}}, "plan_ready": true}}
```

When the user has selected MULTIPLE projects (e.g. "다음 프로젝트 선택: A, B, C"), return a plans array with the confirmed topic in FOCUS:
```json
{{"plans": [
  {{"target": "run-cycle", "env": {{"FOCUS": "<confirmed topic>"}}, "label": "ProjectA"}},
  {{"target": "run-cycle", "env": {{"FOCUS": "<confirmed topic>"}}, "label": "ProjectB"}}
], "plan_ready": true}}
```
For single project, use the existing single-plan format. For multiple projects, use the plans array.

When asking the user to choose between options, include a choices block:
```json
{{"choices": [
  {{"label": "All projects", "description": "Analyze all projects in parallel", "value": "Analyze all projects"}},
  {{"label": "AI server only", "description": "Focus on OraAiServer", "value": "Analyze OraAiServer only"}}
]}}
```
Do NOT include plan_ready in a choices block. Choices are for user input, not execution.

If you are NOT ready (still chatting) and not presenting choices, do NOT include any JSON block. Just reply naturally in the user's language.\
"""


from ora_rd_orchestrator.gemini_provider import (
    _resolve_ca_bundle,
    _urlopen,
    _get_gemini_token,
)


def _call_gemini(system_prompt: str, contents: list[dict]) -> str:
    """Call Gemini Vertex AI directly and return text response."""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "").strip()
    if not project_id:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT_ID not set")

    primary_location = os.getenv("GOOGLE_CLOUD_LOCATION", "").strip() or "us-central1"
    fallback_raw = os.getenv("GOOGLE_CLOUD_FALLBACK_LOCATIONS", "").strip()
    fallback_locations = [x.strip() for x in fallback_raw.split(",") if x.strip()]
    locations = [primary_location] + [x for x in fallback_locations if x != primary_location]

    model = os.getenv("GEMINI_MODEL", "").strip() or "gemini-2.5-flash"
    timeout = float(os.getenv("ORA_RD_LLM_HTTP_TIMEOUT", "90").strip() or 90)
    temperature = float(os.getenv("ORA_RD_LLM_TEMPERATURE", "0.4").strip() or 0.4)

    token = _get_gemini_token()

    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
        },
    }
    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")

    last_error: Exception | None = None
    for location in locations:
        url = (
            f"https://{location}-aiplatform.googleapis.com/v1/"
            f"projects/{project_id}/locations/{location}/publishers/google/models/{model}:generateContent"
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
            with _urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="ignore")
            payload = json.loads(raw)
            candidates = payload.get("candidates", [])
            if not isinstance(candidates, list) or not candidates:
                raise RuntimeError(f"Gemini response missing candidates")
            parts = candidates[0].get("content", {}).get("parts", [])
            texts: list[str] = []
            if isinstance(parts, list):
                for part in parts:
                    if isinstance(part, dict) and part.get("text"):
                        texts.append(str(part["text"]))
            return "\n".join(texts).strip()
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            last_error = RuntimeError(f"Gemini HTTP {exc.code} at {location}: {detail[:600]}")
            continue
        except Exception as exc:
            last_error = exc
            continue

    raise last_error or RuntimeError("All Gemini locations failed")


_project_cache: list[ProjectInfo] | None = None
_project_cache_time: float = 0.0
_PROJECT_CACHE_TTL = 60.0  # seconds
_cache_lock = threading.Lock()


def _scan_projects_from_db(db: Session | None = None) -> list[ProjectInfo]:
    """Load projects from unified projects table."""
    from .models import Project

    close_session = False
    if db is None:
        db = SessionLocal()
        close_session = True

    try:
        projects_db = db.query(Project).filter(Project.enabled == True).order_by(Project.name).all()
        projects: list[ProjectInfo] = []
        for p in projects_db:
            local_path = Path(p.local_path) if p.local_path else None
            projects.append(ProjectInfo(
                id=p.id,
                name=p.name,
                path=p.local_path or "",
                has_makefile=local_path.joinpath("Makefile").is_file() if local_path and local_path.exists() else False,
                has_dockerfile=(
                    local_path.joinpath("Dockerfile").is_file() or local_path.joinpath("docker-compose.yml").is_file()
                ) if local_path and local_path.exists() else False,
                description=p.description or "",
                source_type=p.source_type,
                language=p.language,
            ))
        return projects
    finally:
        if close_session:
            db.close()


def _scan_projects_from_filesystem() -> list[ProjectInfo]:
    """Fallback: scan projects from filesystem."""
    root = settings.projects_root
    if not root.is_dir():
        return []
    projects: list[ProjectInfo] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        if name.startswith(".") or name == "__pycache__" or name == "node_modules":
            continue
        projects.append(ProjectInfo(
            name=name,
            path=str(entry),
            has_makefile=(entry / "Makefile").is_file(),
            has_dockerfile=(entry / "Dockerfile").is_file() or (entry / "docker-compose.yml").is_file(),
        ))
    return projects


def _scan_projects() -> list[ProjectInfo]:
    """Get projects - prefer DB, fallback to filesystem."""
    global _project_cache, _project_cache_time
    now = time.monotonic()
    with _cache_lock:
        if _project_cache is not None and now - _project_cache_time < _PROJECT_CACHE_TTL:
            return _project_cache

    # Try loading from database first
    try:
        projects = _scan_projects_from_db()
        if projects:
            with _cache_lock:
                _project_cache = projects
                _project_cache_time = time.monotonic()
            return projects
    except Exception as exc:
        logger.debug("Failed to load projects from DB, falling back to filesystem: %s", exc)

    # Fallback to filesystem scan
    projects = _scan_projects_from_filesystem()
    with _cache_lock:
        _project_cache = projects
        _project_cache_time = time.monotonic()
    return projects


_system_prompt_cache: str | None = None
_system_prompt_cache_time: float = 0.0


def _build_system_prompt() -> str:
    global _system_prompt_cache, _system_prompt_cache_time
    now = time.monotonic()
    with _cache_lock:
        if _system_prompt_cache is not None and now - _system_prompt_cache_time < _PROJECT_CACHE_TTL:
            return _system_prompt_cache

    projects = _scan_projects()
    if projects:
        project_list = ", ".join(p.name for p in projects)
    else:
        project_list = "(none detected)"
    result = _SYSTEM_PROMPT.format(
        assistant_name=settings.assistant_name,
        project_list=project_list,
        allowed_targets=", ".join(sorted(ALLOWED_TARGETS)),
        allowed_env_keys=", ".join(sorted(ALLOWED_ENV_KEYS)),
    )
    with _cache_lock:
        _system_prompt_cache = result
        _system_prompt_cache_time = time.monotonic()
    return result


def _stream_gemini(system_prompt: str, contents: list[dict]) -> Generator[str, None, None]:
    """Call Gemini Vertex AI streaming endpoint and yield text chunks."""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "").strip()
    if not project_id:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT_ID not set")

    primary_location = os.getenv("GOOGLE_CLOUD_LOCATION", "").strip() or "us-central1"
    fallback_raw = os.getenv("GOOGLE_CLOUD_FALLBACK_LOCATIONS", "").strip()
    fallback_locations = [x.strip() for x in fallback_raw.split(",") if x.strip()]
    locations = [primary_location] + [x for x in fallback_locations if x != primary_location]

    model = os.getenv("GEMINI_MODEL", "").strip() or "gemini-2.5-flash"
    timeout = float(os.getenv("ORA_RD_LLM_HTTP_TIMEOUT", "90").strip() or 90)
    temperature = float(os.getenv("ORA_RD_LLM_TEMPERATURE", "0.4").strip() or 0.4)

    token = _get_gemini_token()

    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
        },
    }
    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")

    last_error: Exception | None = None
    for location in locations:
        url = (
            f"https://{location}-aiplatform.googleapis.com/v1/"
            f"projects/{project_id}/locations/{location}/publishers/google/models/{model}:streamGenerateContent?alt=sse"
        )
        req_obj = request.Request(
            url=url,
            data=body_bytes,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            ssl_ctx = _get_ssl_context()
            if ssl_ctx:
                resp = request.urlopen(req_obj, timeout=timeout, context=ssl_ctx)
            else:
                resp = request.urlopen(req_obj, timeout=timeout)

            # Read SSE stream line by line
            buffer = b""
            for raw_line in resp:
                buffer += raw_line
                if raw_line == b"\n" or raw_line == b"\r\n":
                    # Process buffered event
                    text_line = buffer.decode("utf-8", errors="ignore").strip()
                    buffer = b""
                    if not text_line.startswith("data: "):
                        continue
                    data_str = text_line[6:]
                    if not data_str or data_str == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    candidates = chunk.get("candidates", [])
                    if not candidates:
                        continue
                    parts = candidates[0].get("content", {}).get("parts", [])
                    for part in parts:
                        if isinstance(part, dict) and part.get("text"):
                            yield part["text"]
            # Process remaining buffer
            if buffer:
                text_line = buffer.decode("utf-8", errors="ignore").strip()
                if text_line.startswith("data: "):
                    data_str = text_line[6:]
                    if data_str and data_str != "[DONE]":
                        try:
                            chunk = json.loads(data_str)
                            candidates = chunk.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                for part in parts:
                                    if isinstance(part, dict) and part.get("text"):
                                        yield part["text"]
                        except json.JSONDecodeError:
                            pass
            resp.close()
            return  # success, stop trying other locations
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            last_error = RuntimeError(f"Gemini HTTP {exc.code} at {location}: {detail[:600]}")
            continue
        except Exception as exc:
            last_error = exc
            continue

    raise last_error or RuntimeError("All Gemini locations failed")


def _extract_plan_from_reply(
    text: str,
) -> tuple[str, ChatPlan | None, list[ChatPlan] | None, list[ChatChoice] | None, list[ProjectInfo] | None]:
    """Extract plan/plans/choices/project_select JSON from reply text.

    Returns (clean_reply, single_plan, multi_plans, choices, project_select).
    """
    match = _RE_JSON_BLOCK.search(text)

    parsed: dict | None = None
    if match:
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    if not parsed:
        extracted = _extract_json(text)
        if extracted:
            parsed = extracted

    if not parsed:
        return text, None, None, None, None

    # Remove the JSON block from the displayed reply
    clean_reply = _RE_JSON_BLOCK_STRIP.sub("", text).strip()

    # ── Project select (no plan_ready) ──
    if parsed.get("project_select") and not parsed.get("plan_ready"):
        projects = _scan_projects()
        if not clean_reply:
            clean_reply = parsed.get("message", "어떤 프로젝트를 검사할까요?")
        return clean_reply, None, None, None, projects if projects else None

    # ── Choices (no plan_ready) ──
    if "choices" in parsed and not parsed.get("plan_ready"):
        raw_choices = parsed["choices"]
        if isinstance(raw_choices, list):
            choices = []
            for c in raw_choices:
                if isinstance(c, dict) and c.get("label") and c.get("value"):
                    choices.append(ChatChoice(
                        label=str(c["label"]),
                        description=str(c.get("description", "")),
                        value=str(c["value"]),
                    ))
            if choices:
                return clean_reply or "Please choose an option:", None, None, choices, None
        return text, None, None, None, None

    # Needs plan_ready for execution
    if not parsed.get("plan_ready"):
        return text, None, None, None, None

    # ── Multi plans ──
    if "plans" in parsed and isinstance(parsed["plans"], list):
        plans: list[ChatPlan] = []
        for p in parsed["plans"]:
            if not isinstance(p, dict):
                continue
            try:
                target, env, _ = _coerce_plan(p)
                plans.append(ChatPlan(
                    target=target,
                    env=env,
                    label=str(p.get("label", "")),
                ))
            except RuntimeError:
                continue
        if plans:
            if not clean_reply:
                labels = ", ".join(p.label or p.target for p in plans)
                clean_reply = f"Ready to execute **{len(plans)} plans**: {labels}"
            return clean_reply, None, plans, None, None

    # ── Single plan (backward compat) ──
    try:
        target, env, _ = _coerce_plan(parsed)
    except RuntimeError:
        return text, None, None, None, None

    if not clean_reply:
        clean_reply = f"Ready to execute **{target}**."

    return clean_reply, ChatPlan(target=target, env=env), None, None, None


def _apply_action_gate(
    history: list,
    reply: str,
    plan: ChatPlan | None,
    plans: list[ChatPlan] | None,
    choices: list[ChatChoice] | None,
    project_select: list[ProjectInfo] | None,
) -> tuple[str, ChatPlan | None, list[ChatPlan] | None, list[ChatChoice] | None, list[ProjectInfo] | None]:
    """Strip premature action JSON when the conversation has no prior turns.

    Gemini sometimes ignores the clarification-first system prompt and emits
    plan / project_select on the very first user message.  This gate blocks
    those actions unless the plan already contains a non-empty FOCUS (meaning
    the user was specific enough).  Choices are never blocked — they *are* the
    clarification mechanism.
    """
    # Fast path: nothing to gate
    if plan is None and plans is None and project_select is None:
        return reply, plan, plans, choices, project_select

    user_turns = sum(1 for msg in history if msg.role == "user")

    # After at least one round-trip, allow everything
    if user_turns >= 1:
        return reply, plan, plans, choices, project_select

    # First turn (user_turns == 0): block unless FOCUS is present
    def _has_focus(p: ChatPlan) -> bool:
        return bool(p.env.get("FOCUS", "").strip())

    if plan is not None and _has_focus(plan):
        return reply, plan, plans, choices, project_select

    if plans is not None and all(_has_focus(p) for p in plans):
        return reply, plan, plans, choices, project_select

    # Gate: strip action payloads, keep choices and text reply
    logger.info("action_gate: blocked premature action on first turn (user_turns=0)")
    return reply, None, None, choices, None


def _inject_project_select(
    reply: str,
    plan: ChatPlan | None,
    plans: list[ChatPlan] | None,
    choices: list[ChatChoice] | None,
    project_select: list[ProjectInfo] | None,
) -> tuple[str, ChatPlan | None, list[ChatPlan] | None, list[ChatChoice] | None, list[ProjectInfo] | None]:
    """Force project_select when Gemini lists project names as plain text.

    Gemini sometimes ignores the instruction to emit ``project_select`` JSON
    and instead dumps project names inline.  Detect this by checking whether
    the reply text mentions several known project names — if so, replace
    the text listing with a proper project picker payload.
    """
    # Skip if an action is already attached
    if plan or plans or choices or project_select:
        return reply, plan, plans, choices, project_select

    projects = _scan_projects()
    if not projects:
        return reply, plan, plans, choices, project_select

    names = [p.name for p in projects]
    matched = [n for n in names if n in reply]
    # Threshold: if 4+ project names appear in the reply, it's a listing
    if len(matched) < 4:
        return reply, plan, plans, choices, project_select

    # Strip the project list from the reply text
    logger.info("inject_project_select: detected %d project names in text, injecting picker", len(matched))
    # Remove lines that are just project name listings (comma-separated or bullet)
    clean_lines: list[str] = []
    for line in reply.split("\n"):
        # Skip lines where most content is project names
        line_matched = sum(1 for n in names if n in line)
        if line_matched >= 3:
            continue
        clean_lines.append(line)
    clean_reply = "\n".join(clean_lines).strip()
    if not clean_reply:
        clean_reply = "어떤 프로젝트를 대상으로 진행할까요?"

    return clean_reply, None, None, None, projects


# ── Endpoints ────────────────────────────────────────────────────────


def _build_org_context_for_dialog(db: Session, org_id: str | None) -> str:
    """Build a lightweight org context string for dialog engine prompts."""
    if not org_id:
        return ""
    org = db.get(Organization, org_id)
    if not org:
        return ""

    lines = [f"## Organization: {org.name}"]
    if org.description:
        lines.append(f"Description: {org.description}")

    params = org.pipeline_params or {}
    if params:
        lines.append(f"Pipeline config: {json.dumps(params, ensure_ascii=False)}")

    chapters = (
        db.query(OrganizationChapter)
        .filter(OrganizationChapter.org_id == org_id)
        .order_by(OrganizationChapter.sort_order)
        .all()
    )
    if chapters:
        lines.append("Organization chapters:")
        for ch in chapters:
            directives = ch.shared_directives or []
            constraints = ch.shared_constraints or []
            ch_line = f"  - {ch.name}"
            if directives:
                ch_line += f" (directives: {'; '.join(directives)})"
            if constraints:
                ch_line += f" (constraints: {'; '.join(constraints)})"
            lines.append(ch_line)

    return "\n".join(lines)


_ACTIONABLE_INTENTS = frozenset({IntentType.RESEARCH, IntentType.TESTING, IntentType.SCHEDULING})


def _build_org_summaries_for_recommend(db: Session) -> list[dict]:
    """Build LLM-consumable org summary dicts for recommendation."""
    orgs = db.query(Organization).order_by(Organization.name).all()
    summaries: list[dict] = []
    for org in orgs:
        summary: dict[str, Any] = {
            "org_id": org.id,
            "org_name": org.name,
            "description": org.description or "",
        }
        chapters = (
            db.query(OrganizationChapter)
            .filter(OrganizationChapter.org_id == org.id)
            .order_by(OrganizationChapter.sort_order)
            .all()
        )
        if chapters:
            summary["chapters"] = [
                {"name": ch.name, "description": ch.description or ""}
                for ch in chapters
            ]
        silos = (
            db.query(OrganizationSilo)
            .filter(OrganizationSilo.org_id == org.id)
            .order_by(OrganizationSilo.sort_order)
            .all()
        )
        if silos:
            summary["silos"] = [
                {"name": s.name, "description": s.description or ""}
                for s in silos
            ]
        summaries.append(summary)
    return summaries


def _maybe_recommend_org(
    db: Session,
    conv: ChatConversation,
    user_message: str,
    classification: "IntentClassification",
    dialog_ctx: DialogContext,
) -> list[OrgRecommendOption] | None:
    """Check if org recommendation is needed and return options if so.

    Returns None when recommendation should be skipped.
    """
    # Skip: already has org_id
    if conv.org_id:
        return None

    # Skip: already recommended this conversation
    if dialog_ctx.accumulated_slots.get("org_recommend_done"):
        return None

    # Skip: non-actionable intent
    if classification.intent not in _ACTIONABLE_INTENTS:
        return None

    org_summaries = _build_org_summaries_for_recommend(db)

    # Skip: no orgs exist
    if not org_summaries:
        return None

    # Auto-apply: only 1 org → just bind it
    if len(org_summaries) == 1:
        conv.org_id = org_summaries[0]["org_id"]
        return None

    # 2+ orgs: ask Gemini
    intent_summary = f"{classification.intent.value} (confidence: {classification.confidence:.2f})"
    result = recommend_org(user_message, intent_summary, org_summaries)

    options: list[OrgRecommendOption] = []
    recommended_id = result.recommended_org_id

    # Build from rankings if available, otherwise from org_summaries
    if result.rankings:
        for r in result.rankings:
            options.append(OrgRecommendOption(
                org_id=r.get("org_id", ""),
                org_name=r.get("org_name", ""),
                description="",
                score=float(r.get("score", 0.0)),
                reason=r.get("reason", ""),
                is_recommended=(r.get("org_id") == recommended_id),
            ))
    else:
        for s in org_summaries:
            options.append(OrgRecommendOption(
                org_id=s["org_id"],
                org_name=s["org_name"],
                description=s.get("description", ""),
                score=0.0,
                reason="",
                is_recommended=(s["org_id"] == recommended_id),
            ))

    return options if options else None


def _resolve_org_name(db: Session, org_id: str | None) -> str | None:
    if not org_id:
        return None
    org = db.get(Organization, org_id)
    return org.name if org else None


def _ensure_conversation(db: Session, conversation_id: str | None, org_id: str | None = None) -> ChatConversation:
    """Get or create a conversation row."""
    if conversation_id:
        conv = db.get(ChatConversation, conversation_id)
        if conv:
            if org_id and not conv.org_id:
                conv.org_id = org_id
            return conv
    conv = ChatConversation(id=conversation_id or str(uuid.uuid4()), title="", org_id=org_id)
    db.add(conv)
    db.flush()
    return conv


def _persist_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: str,
    plan: ChatPlan | None = None,
    plans: list[ChatPlan] | None = None,
    choices: list[ChatChoice] | None = None,
    project_select: list[ProjectInfo] | None = None,
    run_id: str | None = None,
) -> None:
    plan_dict: dict | None = None
    if plan:
        plan_dict = {"target": plan.target, "env": plan.env, "label": plan.label}
    elif plans:
        plan_dict = {"plans": [{"target": p.target, "env": p.env, "label": p.label} for p in plans]}
    elif choices:
        plan_dict = {"choices": [{"label": c.label, "description": c.description, "value": c.value} for c in choices]}
    elif project_select:
        plan_dict = {"project_select": [p.model_dump() for p in project_select]}
    db.add(ChatMessageRow(
        conversation_id=conversation_id,
        role=role,
        content=content,
        plan=plan_dict,
        run_id=run_id,
    ))


def _use_upce() -> bool:
    """Check whether the UPCE 2-stage pipeline is enabled."""
    return os.getenv("ORA_CHAT_USE_UPCE", "0").strip() in ("1", "true", "yes")


def _get_dialog_context(conv: ChatConversation) -> tuple[DialogContext, int]:
    """Load DialogContext and version from conversation row."""
    version = conv.dialog_context_version or 0
    if conv.dialog_context and isinstance(conv.dialog_context, dict):
        try:
            return DialogContext.model_validate(conv.dialog_context), version
        except (ValueError, TypeError, KeyError) as exc:
            logger.warning(
                "Failed to parse dialog_context for conversation %s (version %d), "
                "resetting to IDLE: %s",
                conv.id, version, exc,
            )
    return DialogContext(), version


def _save_dialog_context(
    db: Session, conv: ChatConversation, ctx: DialogContext, expected_version: int,
) -> None:
    """Persist DialogContext with optimistic lock on version."""
    result = db.execute(
        update(ChatConversation)
        .where(
            ChatConversation.id == conv.id,
            ChatConversation.dialog_context_version == expected_version,
        )
        .values(
            dialog_context=ctx.model_dump(mode="json"),
            dialog_context_version=expected_version + 1,
        )
    )
    if result.rowcount == 0:
        raise StaleDialogError(
            f"dialog_context version conflict for conversation {conv.id} "
            f"(expected {expected_version})"
        )


# ── UPCE chat (non-streaming) ────────────────────────────────────────


def _chat_upce(req: ChatRequest, db: Session) -> ChatResponse:
    """2-stage UPCE pipeline for non-streaming chat."""
    conv = _ensure_conversation(db, req.conversation_id, org_id=req.org_id)
    if not conv.title and req.message:
        conv.title = req.message[:100]

    # ── Org selection message detection ──
    if req.message.startswith("ora:org_select:"):
        selected_org_id = req.message[len("ora:org_select:"):].strip()
        dialog_ctx, ctx_version = _get_dialog_context(conv)
        if selected_org_id:
            conv.org_id = selected_org_id
            org_name = _resolve_org_name(db, selected_org_id) or selected_org_id
            reply = f"**{org_name}** 조직이 선택되었습니다. 이어서 진행할게요."
        else:
            reply = "미분류로 진행합니다."
        dialog_ctx.accumulated_slots["org_recommend_done"] = True
        _persist_message(db, conv.id, "user", req.message)
        _persist_message(db, conv.id, "assistant", reply)
        try:
            _save_dialog_context(db, conv, dialog_ctx, ctx_version)
        except StaleDialogError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Dialog context was modified concurrently. Please retry.")
        db.commit()
        return ChatResponse(reply=reply, dialog_state=dialog_ctx.state.value)

    dialog_ctx, ctx_version = _get_dialog_context(conv)
    projects = _scan_projects()
    history = [{"role": m.role, "content": m.content} for m in req.history]
    org_context = _build_org_context_for_dialog(db, conv.org_id)

    # Stage 1: Understanding
    classification = run_stage1(req.message, history, dialog_ctx, projects, org_context=org_context)
    dialog_ctx = merge_slots(dialog_ctx, classification)

    # ── Org recommendation intercept (before short circuits) ──
    org_options = _maybe_recommend_org(db, conv, req.message, classification, dialog_ctx)
    if org_options is not None:
        recommended = next((o for o in org_options if o.is_recommended), None)
        reason = recommended.reason if recommended else ""
        reply = f"이 작업에 적합한 조직을 추천드릴게요.\n{reason}" if reason else "이 작업에 적합한 조직을 추천드릴게요."
        _persist_message(db, conv.id, "user", req.message)
        _persist_message(db, conv.id, "assistant", reply)
        try:
            _save_dialog_context(db, conv, dialog_ctx, ctx_version)
        except StaleDialogError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Dialog context was modified concurrently. Please retry.")
        db.commit()
        return ChatResponse(
            reply=reply,
            org_recommend=org_options,
            dialog_state=classification.next_state.value,
            intent_summary=f"{classification.intent.value} (confidence: {classification.confidence:.2f})",
        )

    # Short circuit: confirmation → no Stage 2 text needed
    if classification.is_confirmation and dialog_ctx.proposed_plans:
        # ── Scheduling intent: create ScheduledJob instead of execution plan ──
        if dialog_ctx.intent == IntentType.SCHEDULING:
            try:
                job = create_scheduled_job_from_slots(db, dialog_ctx.accumulated_slots)
                hr = dialog_ctx.accumulated_slots.get("human_readable", "")
                reply = f"스케줄이 등록되었습니다: **{job.name}** ({hr})"
                _persist_message(db, conv.id, "user", req.message)
                _persist_message(db, conv.id, "assistant", reply)
                dialog_ctx = DialogContext()  # reset to IDLE
                try:
                    _save_dialog_context(db, conv, dialog_ctx, ctx_version)
                except StaleDialogError:
                    db.rollback()
                    raise HTTPException(status_code=409, detail="Dialog context was modified concurrently. Please retry.")
                db.commit()
                return ChatResponse(
                    reply=reply,
                    dialog_state=DialogState.IDLE.value,
                    confirmation_required=False,
                )
            except ScheduleValidationError as exc:
                reply = f"스케줄 등록에 실패했습니다: {exc}\n다시 정보를 알려주세요."
                dialog_ctx.state = DialogState.SLOT_FILLING
                _persist_message(db, conv.id, "user", req.message)
                _persist_message(db, conv.id, "assistant", reply)
                try:
                    _save_dialog_context(db, conv, dialog_ctx, ctx_version)
                except StaleDialogError:
                    db.rollback()
                    raise HTTPException(status_code=409, detail="Dialog context was modified concurrently. Please retry.")
                db.commit()
                return ChatResponse(
                    reply=reply,
                    dialog_state=DialogState.SLOT_FILLING.value,
                    confirmation_required=False,
                )

        plan, plans = coerce_proposed_plans(dialog_ctx.proposed_plans)
        reply = "실행을 시작합니다."
        _persist_message(db, conv.id, "user", req.message)
        _persist_message(db, conv.id, "assistant", reply, plan=plan, plans=plans)
        dialog_ctx.state = DialogState.EXECUTING
        try:
            _save_dialog_context(db, conv, dialog_ctx, ctx_version)
        except StaleDialogError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Dialog context was modified concurrently. Please retry.")
        db.commit()
        return ChatResponse(
            reply=reply, plan=plan, plans=plans,
            dialog_state=DialogState.EXECUTING.value,
            confirmation_required=False,
        )

    # Short circuit: rejection → reset
    if classification.is_rejection:
        reply = "취소했습니다. 다른 작업이 있으면 말씀해주세요."
        dialog_ctx = DialogContext()
        _persist_message(db, conv.id, "user", req.message)
        _persist_message(db, conv.id, "assistant", reply)
        try:
            _save_dialog_context(db, conv, dialog_ctx, ctx_version)
        except StaleDialogError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Dialog context was modified concurrently. Please retry.")
        db.commit()
        return ChatResponse(
            reply=reply, dialog_state=DialogState.IDLE.value,
        )

    # Stage 2: Response generation (sync)
    try:
        reply = run_stage2_sync(
            classification, history, req.message,
            dialog_ctx, projects, settings.assistant_name,
            org_context=org_context,
        )
    except Exception as exc:
        logger.error("Stage 2 sync failed: %s", exc)
        reply = "죄송합니다, 응답 생성 중 오류가 발생했습니다. 다시 시도해주세요."

    # Build response payloads from classification
    plan: ChatPlan | None = None
    plans: list[ChatPlan] | None = None
    project_select: list[ProjectInfo] | None = None

    if classification.proposed_plans:
        plan, plans = coerce_proposed_plans(classification.proposed_plans)

    if classification.needs_project_select:
        project_select = projects if projects else None

    confirmation_required = classification.next_state == DialogState.CONFIRMING

    _persist_message(
        db, conv.id, "user", req.message,
    )
    _persist_message(
        db, conv.id, "assistant", reply,
        plan=plan, plans=plans, project_select=project_select,
    )
    try:
        _save_dialog_context(db, conv, dialog_ctx, ctx_version)
    except StaleDialogError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Dialog context was modified concurrently. Please retry.")
    db.commit()

    return ChatResponse(
        reply=reply,
        plan=plan,
        plans=plans,
        project_select=project_select,
        dialog_state=classification.next_state.value,
        confirmation_required=confirmation_required,
        intent_summary=f"{classification.intent.value} (confidence: {classification.confidence:.2f})",
    )


# ── UPCE chat_stream (SSE streaming) ─────────────────────────────────


def _chat_stream_upce(req: ChatRequest, db: Session) -> StreamingResponse:
    """2-stage UPCE pipeline with SSE streaming."""
    conv = _ensure_conversation(db, req.conversation_id, org_id=req.org_id)
    if not conv.title and req.message:
        conv.title = req.message[:100]

    # ── Org selection message detection (streaming path) ──
    if req.message.startswith("ora:org_select:"):
        selected_org_id = req.message[len("ora:org_select:"):].strip()
        dialog_ctx, ctx_version = _get_dialog_context(conv)
        if selected_org_id:
            conv.org_id = selected_org_id
            org_name = _resolve_org_name(db, selected_org_id) or selected_org_id
            reply = f"**{org_name}** 조직이 선택되었습니다. 이어서 진행할게요."
        else:
            reply = "미분류로 진행합니다."
        dialog_ctx.accumulated_slots["org_recommend_done"] = True
        _persist_message(db, conv.id, "user", req.message)
        _persist_message(db, conv.id, "assistant", reply)
        try:
            _save_dialog_context(db, conv, dialog_ctx, ctx_version)
        except StaleDialogError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Dialog context was modified concurrently. Please retry.")
        db.commit()

        def org_select_gen() -> Generator[str, None, None]:
            token_data = json.dumps({"type": "token", "content": reply}, ensure_ascii=False)
            yield f"data: {token_data}\n\n"
            done_payload = {
                "type": "done",
                "full_reply": reply,
                "dialog_state": dialog_ctx.state.value,
            }
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            org_select_gen(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    dialog_ctx, ctx_version = _get_dialog_context(conv)
    projects = _scan_projects()
    history = [{"role": m.role, "content": m.content} for m in req.history]
    org_context = _build_org_context_for_dialog(db, conv.org_id)

    # Persist user message
    _persist_message(db, conv.id, "user", req.message)
    db.commit()
    conv_id = conv.id

    # Run Stage 1 before entering the generator (non-streaming, ~1-2s)
    try:
        classification = run_stage1(req.message, history, dialog_ctx, projects, org_context=org_context)
    except Exception as exc:
        logger.error("Stage 1 failed: %s", exc)
        # Fall back to a simple error response
        def error_gen() -> Generator[str, None, None]:
            err = json.dumps({"type": "error", "content": f"분류 실패: {exc}"}, ensure_ascii=False)
            yield f"data: {err}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(error_gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    updated_ctx = merge_slots(dialog_ctx, classification)

    # ── Org recommendation intercept (streaming path) ──
    org_options = _maybe_recommend_org(db, conv, req.message, classification, updated_ctx)
    if org_options is not None:
        recommended = next((o for o in org_options if o.is_recommended), None)
        reason = recommended.reason if recommended else ""
        rec_reply = f"이 작업에 적합한 조직을 추천드릴게요.\n{reason}" if reason else "이 작업에 적합한 조직을 추천드릴게요."
        try:
            _save_dialog_context(db, conv, updated_ctx, ctx_version)
        except StaleDialogError:
            pass
        db.commit()

        def org_rec_gen() -> Generator[str, None, None]:
            token_data = json.dumps({"type": "token", "content": rec_reply}, ensure_ascii=False)
            yield f"data: {token_data}\n\n"
            done_payload: dict[str, Any] = {
                "type": "done",
                "full_reply": rec_reply,
                "dialog_state": classification.next_state.value,
                "intent_summary": f"{classification.intent.value} (confidence: {classification.confidence:.2f})",
                "org_recommend": [o.model_dump() for o in org_options],
            }
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            try:
                with _session_scope() as pdb:
                    _persist_message(pdb, conv_id, "assistant", rec_reply)
            except Exception:
                logger.exception("Failed to persist org recommendation message")

        return StreamingResponse(
            org_rec_gen(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def generate() -> Generator[str, None, None]:
        # Short circuit: confirmation
        if classification.is_confirmation and updated_ctx.proposed_plans:
            # ── Scheduling intent: create ScheduledJob ──
            if updated_ctx.intent == IntentType.SCHEDULING:
                try:
                    with _session_scope() as pdb:
                        job = create_scheduled_job_from_slots(pdb, updated_ctx.accumulated_slots)
                    hr = updated_ctx.accumulated_slots.get("human_readable", "")
                    reply = f"스케줄이 등록되었습니다: **{job.name}** ({hr})"
                    token_data = json.dumps({"type": "token", "content": reply}, ensure_ascii=False)
                    yield f"data: {token_data}\n\n"
                    done_payload: dict[str, Any] = {
                        "type": "done",
                        "full_reply": reply,
                        "dialog_state": DialogState.IDLE.value,
                        "confirmation_required": False,
                    }
                    yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    with _session_scope() as pdb:
                        _persist_message(pdb, conv_id, "assistant", reply)
                        pconv = pdb.get(ChatConversation, conv_id)
                        if pconv:
                            _save_dialog_context(pdb, pconv, DialogContext(), ctx_version)
                except ScheduleValidationError as exc:
                    reply = f"스케줄 등록에 실패했습니다: {exc}\n다시 정보를 알려주세요."
                    token_data = json.dumps({"type": "token", "content": reply}, ensure_ascii=False)
                    yield f"data: {token_data}\n\n"
                    done_payload = {
                        "type": "done",
                        "full_reply": reply,
                        "dialog_state": DialogState.SLOT_FILLING.value,
                        "confirmation_required": False,
                    }
                    yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                    try:
                        with _session_scope() as pdb2:
                            _persist_message(pdb2, conv_id, "assistant", reply)
                            slot_ctx = DialogContext(
                                state=DialogState.SLOT_FILLING,
                                intent=updated_ctx.intent,
                                accumulated_slots=updated_ctx.accumulated_slots,
                                proposed_plans=updated_ctx.proposed_plans,
                                turn_count=updated_ctx.turn_count,
                            )
                            pconv2 = pdb2.get(ChatConversation, conv_id)
                            if pconv2:
                                _save_dialog_context(pdb2, pconv2, slot_ctx, ctx_version)
                    except Exception:
                        logger.exception("Failed to persist scheduling validation error")
                except Exception:
                    logger.exception("Failed to create scheduled job (stream)")
                    reply = "스케줄 등록 중 오류가 발생했습니다."
                    token_data = json.dumps({"type": "token", "content": reply}, ensure_ascii=False)
                    yield f"data: {token_data}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'full_reply': reply, 'dialog_state': DialogState.IDLE.value}, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                return

            plan, plans = coerce_proposed_plans(updated_ctx.proposed_plans)
            reply = "실행을 시작합니다."
            token_data = json.dumps({"type": "token", "content": reply}, ensure_ascii=False)
            yield f"data: {token_data}\n\n"
            done_payload: dict[str, Any] = {
                "type": "done",
                "full_reply": reply,
                "dialog_state": DialogState.EXECUTING.value,
                "confirmation_required": False,
            }
            if plan:
                done_payload["plan"] = {"target": plan.target, "env": plan.env, "label": plan.label}
            if plans:
                done_payload["plans"] = [{"target": p.target, "env": p.env, "label": p.label} for p in plans]
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            # Persist
            try:
                with _session_scope() as pdb:
                    _persist_message(pdb, conv_id, "assistant", reply, plan=plan, plans=plans)
                    exec_ctx = DialogContext(
                        state=DialogState.EXECUTING,
                        intent=updated_ctx.intent,
                        accumulated_slots=updated_ctx.accumulated_slots,
                        proposed_plans=updated_ctx.proposed_plans,
                        turn_count=updated_ctx.turn_count,
                    )
                    pconv = pdb.get(ChatConversation, conv_id)
                    if pconv:
                        _save_dialog_context(pdb, pconv, exec_ctx, ctx_version)
            except StaleDialogError:
                logger.warning("Stale dialog context on confirmation persist (stream)")
            except Exception:
                logger.exception("Failed to persist confirmation message")
            return

        # Short circuit: rejection
        if classification.is_rejection:
            reply = "취소했습니다. 다른 작업이 있으면 말씀해주세요."
            token_data = json.dumps({"type": "token", "content": reply}, ensure_ascii=False)
            yield f"data: {token_data}\n\n"
            done_payload = {
                "type": "done",
                "full_reply": reply,
                "dialog_state": DialogState.IDLE.value,
            }
            yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            try:
                with _session_scope() as pdb:
                    _persist_message(pdb, conv_id, "assistant", reply)
                    pconv = pdb.get(ChatConversation, conv_id)
                    if pconv:
                        _save_dialog_context(pdb, pconv, DialogContext(), ctx_version)
            except StaleDialogError:
                logger.warning("Stale dialog context on rejection persist (stream)")
            except Exception:
                logger.exception("Failed to persist rejection message")
            return

        # Stage 2: Streaming response
        full_text = ""
        try:
            for chunk in run_stage2_stream(
                classification, history, req.message,
                updated_ctx, projects, settings.assistant_name,
                org_context=org_context,
            ):
                full_text += chunk
                data = json.dumps({"type": "token", "content": chunk}, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except Exception as exc:
            logger.error("Stage 2 streaming failed: %s", exc)
            err_data = json.dumps({"type": "error", "content": f"응답 생성 실패: {exc}"})
            yield f"data: {err_data}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Build done event
        plan: ChatPlan | None = None
        plans_list: list[ChatPlan] | None = None
        project_select: list[ProjectInfo] | None = None

        if classification.proposed_plans:
            plan, plans_list = coerce_proposed_plans(classification.proposed_plans)

        if classification.needs_project_select:
            project_select = projects if projects else None

        confirmation_required = classification.next_state == DialogState.CONFIRMING

        done_payload = {"type": "done", "full_reply": full_text}
        if plan:
            done_payload["plan"] = {"target": plan.target, "env": plan.env, "label": plan.label}
        if plans_list:
            done_payload["plans"] = [
                {"target": p.target, "env": p.env, "label": p.label} for p in plans_list
            ]
        if project_select:
            done_payload["project_select"] = [p.model_dump() for p in project_select]
        done_payload["dialog_state"] = classification.next_state.value
        done_payload["confirmation_required"] = confirmation_required
        done_payload["intent_summary"] = f"{classification.intent.value} (confidence: {classification.confidence:.2f})"

        yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

        # Persist assistant reply + dialog context
        try:
            with _session_scope() as pdb:
                _persist_message(
                    pdb, conv_id, "assistant", full_text,
                    plan=plan, plans=plans_list, project_select=project_select,
                )
                pconv = pdb.get(ChatConversation, conv_id)
                if pconv:
                    _save_dialog_context(pdb, pconv, updated_ctx, ctx_version)
        except StaleDialogError:
            logger.warning("Stale dialog context on stream persist")
        except Exception:
            logger.exception("Failed to persist streamed assistant message")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    if _use_upce():
        return _chat_upce(req, db)

    # ── Legacy path ──
    # Build Gemini conversation contents from history
    contents: list[dict] = []
    for msg in req.history:
        contents.append({
            "role": "user" if msg.role == "user" else "model",
            "parts": [{"text": msg.content}],
        })
    # Append current message
    contents.append({
        "role": "user",
        "parts": [{"text": req.message}],
    })

    system_prompt = _build_system_prompt()

    try:
        raw_reply = _call_gemini(system_prompt, contents)
    except Exception as exc:
        logger.error("Gemini call failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"LLM call failed: {exc}")

    reply, plan, plans, choices, project_select = _extract_plan_from_reply(raw_reply)
    reply, plan, plans, choices, project_select = _apply_action_gate(
        req.history, reply, plan, plans, choices, project_select,
    )
    reply, plan, plans, choices, project_select = _inject_project_select(
        reply, plan, plans, choices, project_select,
    )

    # Persist to DB
    conv = _ensure_conversation(db, req.conversation_id, org_id=req.org_id)
    if not conv.title and req.message:
        conv.title = req.message[:100]
    _persist_message(db, conv.id, "user", req.message)
    _persist_message(db, conv.id, "assistant", reply, plan=plan, plans=plans, choices=choices, project_select=project_select)
    db.commit()

    return ChatResponse(reply=reply, plan=plan, plans=plans, choices=choices, project_select=project_select)


@router.post("/chat/stream")
def chat_stream(req: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    """SSE streaming chat endpoint. Yields tokens as they arrive from Gemini."""
    if _use_upce():
        return _chat_stream_upce(req, db)

    # ── Legacy path ──
    contents: list[dict] = []
    for msg in req.history:
        contents.append({
            "role": "user" if msg.role == "user" else "model",
            "parts": [{"text": msg.content}],
        })
    contents.append({
        "role": "user",
        "parts": [{"text": req.message}],
    })

    system_prompt = _build_system_prompt()

    # Persist user message before streaming starts
    conv = _ensure_conversation(db, req.conversation_id, org_id=req.org_id)
    if not conv.title and req.message:
        conv.title = req.message[:100]
    _persist_message(db, conv.id, "user", req.message)
    db.commit()
    conv_id = conv.id
    history_for_gate = req.history

    def generate() -> Generator[str, None, None]:
        full_text = ""
        try:
            for chunk in _stream_gemini(system_prompt, contents):
                full_text += chunk
                data = json.dumps({"type": "token", "content": chunk}, ensure_ascii=False)
                yield f"data: {data}\n\n"
        except Exception as exc:
            logger.error("Gemini streaming failed: %s", exc)
            err_data = json.dumps({"type": "error", "content": f"LLM call failed: {exc}"})
            yield f"data: {err_data}\n\n"
            yield "data: [DONE]\n\n"
            return

        # After streaming completes, check for plan/plans/choices/project_select in the full response
        reply, plan, plans, choices, project_select = _extract_plan_from_reply(full_text)
        reply, plan, plans, choices, project_select = _apply_action_gate(
            history_for_gate, reply, plan, plans, choices, project_select,
        )
        reply, plan, plans, choices, project_select = _inject_project_select(
            reply, plan, plans, choices, project_select,
        )
        done_payload: dict[str, Any] = {"type": "done", "full_reply": reply}
        if plan:
            done_payload["plan"] = {"target": plan.target, "env": plan.env, "label": plan.label}
        if plans:
            done_payload["plans"] = [
                {"target": p.target, "env": p.env, "label": p.label} for p in plans
            ]
        if choices:
            done_payload["choices"] = [
                {"label": c.label, "description": c.description, "value": c.value} for c in choices
            ]
        if project_select:
            done_payload["project_select"] = [p.model_dump() for p in project_select]
        yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

        # Persist assistant reply after streaming completes
        try:
            with _session_scope() as persist_db:
                _persist_message(persist_db, conv_id, "assistant", reply, plan=plan, plans=plans, choices=choices, project_select=project_select)
        except Exception:
            logger.exception("Failed to persist streamed assistant message")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Projects ─────────────────────────────────────────────────────────


@router.get("/projects", response_model=list[ProjectInfo])
def list_projects() -> list[ProjectInfo]:
    return _scan_projects()


# ── Conversations ────────────────────────────────────────────────────


@router.get("/conversations", response_model=ConversationList)
def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    org_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ConversationList:
    query = (
        db.query(ChatConversation, Organization.name)
        .outerjoin(Organization, ChatConversation.org_id == Organization.id)
    )
    count_query = db.query(ChatConversation)
    if org_id is not None:
        query = query.filter(ChatConversation.org_id == org_id)
        count_query = count_query.filter(ChatConversation.org_id == org_id)
    rows = query.order_by(ChatConversation.updated_at.desc()).limit(limit).all()
    total = count_query.count()
    return ConversationList(
        items=[
            ConversationRead(
                id=conv.id,
                title=conv.title,
                org_id=conv.org_id,
                org_name=org_name,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )
            for conv, org_name in rows
        ],
        total=total,
    )


@router.post("/conversations", response_model=ConversationRead, status_code=201)
def create_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
) -> ConversationRead:
    conv = ChatConversation(
        id=payload.id or str(uuid.uuid4()),
        title=payload.title,
        org_id=payload.org_id or None,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    org_name = _resolve_org_name(db, conv.org_id)
    return ConversationRead(
        id=conv.id,
        title=conv.title,
        org_id=conv.org_id,
        org_name=org_name,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
) -> ConversationDetail:
    conv = db.get(ChatConversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    messages = (
        db.query(ChatMessageRow)
        .filter(ChatMessageRow.conversation_id == conversation_id)
        .order_by(ChatMessageRow.created_at.asc())
        .all()
    )
    org_name = _resolve_org_name(db, conv.org_id)
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        org_id=conv.org_id,
        org_name=org_name,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[ChatMessageRead.model_validate(m) for m in messages],
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
) -> None:
    conv = db.get(ChatConversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    db.query(ChatMessageRow).filter(ChatMessageRow.conversation_id == conversation_id).delete()
    db.delete(conv)
    db.commit()


@router.patch("/conversations/{conversation_id}", response_model=ConversationRead)
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
) -> ConversationRead:
    conv = db.get(ChatConversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    if payload.title is not None:
        conv.title = payload.title
    if payload.org_id is not None:
        conv.org_id = payload.org_id if payload.org_id else None
    db.commit()
    db.refresh(conv)
    org_name = _resolve_org_name(db, conv.org_id)
    return ConversationRead(
        id=conv.id,
        title=conv.title,
        org_id=conv.org_id,
        org_name=org_name,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


# ── Reports ──────────────────────────────────────────────────────────


def _report_dirs() -> list[Path]:
    dirs: list[Path] = []
    if settings.run_output_dir.is_dir():
        dirs.append(settings.run_output_dir)
    research_reports = settings.automation_root / "research_reports"
    if research_reports.is_dir() and research_reports != settings.run_output_dir:
        dirs.append(research_reports)
    return dirs


_MAX_REPORT_SCAN = 500  # safety cap on total files enumerated


def _scan_reports() -> list[ReportListItem]:
    items: list[ReportListItem] = []
    seen: set[str] = set()
    for base_dir in _report_dirs():
        collected: list[Path] = []
        for path in base_dir.rglob("*"):
            if len(collected) >= _MAX_REPORT_SCAN:
                break
            if not path.is_file():
                continue
            if path.suffix.lower() in (".md", ".json"):
                collected.append(path)
        for path in sorted(collected, key=lambda p: p.stat().st_mtime, reverse=True):
            suffix = path.suffix.lower()
            rel = str(path.relative_to(base_dir))
            if rel in seen:
                continue
            seen.add(rel)
            stat = path.stat()
            items.append(
                ReportListItem(
                    filename=rel,
                    created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    size_bytes=stat.st_size,
                    report_type="markdown" if suffix == ".md" else "json",
                )
            )
    return items[:200]


@router.get("/reports", response_model=list[ReportListItem])
def list_reports() -> list[ReportListItem]:
    return _scan_reports()


@router.get("/reports/{filename:path}")
def get_report(filename: str) -> FileResponse:
    if ".." in filename or filename.startswith("/"):
        raise HTTPException(status_code=400, detail="invalid filename")

    for base_dir in _report_dirs():
        candidate = (base_dir / filename).resolve()
        # Path traversal 방어: resolve 후 base_dir 안에 있는지 확인
        try:
            candidate.relative_to(base_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid filename")
        if candidate.is_file() and candidate.suffix.lower() in (".md", ".json"):
            media_type = "text/markdown" if candidate.suffix.lower() == ".md" else "application/json"
            return FileResponse(str(candidate), media_type=media_type)

    raise HTTPException(status_code=404, detail="report not found")
