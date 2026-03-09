"""UPCE Dialog Engine — 2-Stage LLM Intent Classification.

Stage 1 (Understanding): Gemini JSON-mode call for intent/slot/state classification.
Stage 2 (Response Gen): Streaming text generation with state-specific prompts.
"""
from __future__ import annotations

import json
import logging
import os
from collections.abc import Generator
from enum import Enum
from typing import Any
from urllib import error, request

from pydantic import BaseModel, Field

from .exceptions import LLMConnectionError, LLMParseError, LLMTimeoutError
from .plan_utils import ALLOWED_ENV_KEYS, ALLOWED_TARGETS, coerce_plan as _coerce_plan
from ora_rd_orchestrator.gemini_provider import _get_gemini_token, _get_ssl_context, _urlopen

from .schemas import ChatPlan, ProjectInfo

logger = logging.getLogger(__name__)


# ── Org Recommendation ───────────────────────────────────────────────


class OrgRecommendationResult(BaseModel):
    recommended_org_id: str | None = None
    reason: str = ""
    rankings: list[dict] = Field(default_factory=list)


_ORG_RECOMMEND_PROMPT = """\
You are an organization matching engine for the Ora R&D platform.
Given a user's message and available organizations, recommend the best-fit organization.

## User message
{user_message}

## Intent
{intent_summary}

## Available organizations
{org_summaries}

Return JSON:
{{
  "recommended_org_id": "<best org_id>",
  "reason": "<1-2 sentence in Korean>",
  "rankings": [
    {{"org_id": "...", "org_name": "...", "score": 0.0, "reason": "..."}}
  ]
}}
Rules: rank ALL orgs by fit. Korean reasons. If no clear winner, recommend the first org as default.
"""


def recommend_org(
    user_message: str,
    intent_summary: str,
    org_summaries: list[dict],
) -> OrgRecommendationResult:
    """Call Gemini to recommend the best-fit organization."""
    if not org_summaries:
        return OrgRecommendationResult()

    summaries_str = json.dumps(org_summaries, ensure_ascii=False, indent=2)
    prompt = _ORG_RECOMMEND_PROMPT.format(
        user_message=user_message,
        intent_summary=intent_summary,
        org_summaries=summaries_str,
    )
    try:
        raw = _call_gemini_json(prompt, [{"role": "user", "parts": [{"text": "추천해주세요."}]}])
        return OrgRecommendationResult.model_validate(raw)
    except Exception as exc:
        logger.warning("recommend_org failed: %s", exc)
        return OrgRecommendationResult()


# ── Enums ─────────────────────────────────────────────────────────────


class DialogState(str, Enum):
    IDLE = "idle"
    UNDERSTANDING = "understanding"
    SLOT_FILLING = "slot_filling"
    CONFIRMING = "confirming"
    EXECUTING = "executing"
    REPORTING = "reporting"


class IntentType(str, Enum):
    RESEARCH = "research"
    TESTING = "testing"
    SCHEDULING = "scheduling"
    PROJECT_INQUIRY = "project_inquiry"
    REPORT_INQUIRY = "report_inquiry"
    MODIFY_PLAN = "modify_plan"
    CONFIRM = "confirm"
    REJECT = "reject"
    GENERAL_CHAT = "general_chat"
    UNCLEAR = "unclear"


# ── Slot Models ───────────────────────────────────────────────────────


class MissingSlot(BaseModel):
    name: str
    description: str = ""


class ResearchSlots(BaseModel):
    topic: str | None = None
    projects: list[str] | None = None
    depth: str | None = None
    target: str | None = None


class TestingSlots(BaseModel):
    service: str | None = None
    scope: str | None = None
    projects: list[str] | None = None


class SchedulingSlots(BaseModel):
    topic: str | None = None
    frequency_type: str | None = None  # "cron" | "interval"
    cron_expression: str | None = None  # "0 9 * * *"
    interval_minutes: int | None = None  # 360
    human_readable: str | None = None  # "매일 오전 9시"
    target: str | None = None  # default: run-cycle
    auto_publish: bool | None = None
    projects: list[str] | None = None


# ── Stage 1 Output ────────────────────────────────────────────────────


class IntentClassification(BaseModel):
    intent: IntentType = IntentType.UNCLEAR
    confidence: float = 0.0
    current_state: DialogState = DialogState.IDLE
    next_state: DialogState = DialogState.IDLE
    research_slots: ResearchSlots | None = None
    testing_slots: TestingSlots | None = None
    scheduling_slots: SchedulingSlots | None = None
    needs_clarification: bool = True
    missing_slots: list[MissingSlot] | None = None
    proposed_plans: list[dict] | None = None
    needs_project_select: bool = False
    is_confirmation: bool = False
    is_rejection: bool = False
    response_guidance: str = ""


# ── Dialog Context (persisted per conversation) ───────────────────────


class DialogContext(BaseModel):
    state: DialogState = DialogState.IDLE
    intent: IntentType | None = None
    accumulated_slots: dict[str, Any] = Field(default_factory=dict)
    proposed_plans: list[dict] | None = None
    turn_count: int = 0


# ── Gemini JSON-mode call ─────────────────────────────────────────────


def _call_gemini_json(system_prompt: str, contents: list[dict]) -> dict:
    """Call Gemini with JSON response mode (responseMimeType: application/json)."""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "").strip()
    if not project_id:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT_ID not set")

    primary_location = os.getenv("GOOGLE_CLOUD_LOCATION", "").strip() or "us-central1"
    fallback_raw = os.getenv("GOOGLE_CLOUD_FALLBACK_LOCATIONS", "").strip()
    fallback_locations = [x.strip() for x in fallback_raw.split(",") if x.strip()]
    locations = [primary_location] + [x for x in fallback_locations if x != primary_location]

    model = os.getenv("GEMINI_MODEL", "").strip() or "gemini-2.5-flash"
    timeout = float(os.getenv("ORA_RD_LLM_HTTP_TIMEOUT", "90").strip() or 90)

    token = _get_gemini_token()

    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
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
                raise LLMParseError("Gemini response missing candidates")
            parts = candidates[0].get("content", {}).get("parts", [])
            texts: list[str] = []
            if isinstance(parts, list):
                for part in parts:
                    if isinstance(part, dict) and part.get("text"):
                        texts.append(str(part["text"]))
            text = "\n".join(texts).strip()
            return json.loads(text)
        except json.JSONDecodeError as exc:
            last_error = LLMParseError(f"Gemini JSON parse error: {exc}")
            continue
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            last_error = LLMConnectionError(f"Gemini HTTP {exc.code} at {location}: {detail[:600]}")
            continue
        except (LLMParseError, LLMConnectionError):
            raise
        except Exception as exc:
            last_error = LLMConnectionError(f"Gemini call failed: {exc}")
            continue

    raise last_error or LLMConnectionError("All Gemini locations failed")


# ── Stage 1: Understanding ────────────────────────────────────────────


_STAGE1_SYSTEM_PROMPT = """\
You are an intent classification engine for the Ora R&D orchestration platform.
Your ONLY job is to analyze the user message and return structured JSON.

## Available make targets
{allowed_targets}

## Available env keys
{allowed_env_keys}

## Available Ora projects
{project_list}

## Current dialog state
State: {current_state}
Accumulated slots: {accumulated_slots}
Turn count: {turn_count}

{org_context}

## Intent types
- research: User wants R&D analysis (run-cycle, run-cycle-deep, etc.)
- testing: User wants E2E testing or QA (e2e-service, e2e-service-all, qa-program)
- scheduling: User wants to set up a recurring/scheduled analysis (e.g. "매일 아침 9시에 분석해줘", "6시간마다 보안 트렌드 분석")
- project_inquiry: User asks about available projects
- report_inquiry: User asks about reports or past results
- modify_plan: User wants to change a proposed plan
- confirm: User confirms/agrees (e.g. "네", "확인", "실행해줘", "yes", "go ahead")
- reject: User rejects/cancels (e.g. "취소", "아니", "다시", "no", "cancel")
- general_chat: General conversation, greetings, questions about the system
- unclear: Cannot determine intent

## State transition rules
1. IDLE -> UNDERSTANDING: When a new actionable intent is detected
2. UNDERSTANDING -> SLOT_FILLING: When intent is clear but slots are missing
3. SLOT_FILLING -> SLOT_FILLING: When some slots are filled but others remain
4. SLOT_FILLING -> CONFIRMING: When ALL required slots for the intent are filled
5. CONFIRMING -> EXECUTING: When user confirms (is_confirmation=true)
6. CONFIRMING -> IDLE: When user rejects (is_rejection=true)
7. Any -> IDLE: When user changes topic or cancels

## Required slots by intent
- research: topic (REQUIRED), projects (optional but recommended), depth (optional), target (default: run-cycle)
- testing: service (REQUIRED for e2e-service), scope (single/all), projects (optional)
- scheduling: topic (REQUIRED), frequency_type (REQUIRED: "cron" or "interval"), cron_expression or interval_minutes (REQUIRED based on frequency_type), human_readable (REQUIRED: natural language description of schedule), target (optional, default: run-cycle), auto_publish (optional), projects (optional)

## Schedule parsing rules
Convert natural language time expressions to cron or interval:
- "매일 아침 9시" / "every day at 9am" → frequency_type="cron", cron_expression="0 9 * * *"
- "매일 오후 6시" / "daily at 6pm" → frequency_type="cron", cron_expression="0 18 * * *"
- "매주 월요일 10시" / "every Monday at 10am" → frequency_type="cron", cron_expression="0 10 * * 1"
- "평일 아침 8시" / "weekdays at 8am" → frequency_type="cron", cron_expression="0 8 * * 1-5"
- "6시간마다" / "every 6 hours" → frequency_type="interval", interval_minutes=360
- "30분마다" / "every 30 minutes" → frequency_type="interval", interval_minutes=30
- "12시간마다" / "every 12 hours" → frequency_type="interval", interval_minutes=720
Always set human_readable to a concise Korean description of the schedule (e.g. "매일 오전 9시", "6시간마다").

## Plan generation rules
- Only set proposed_plans when next_state is CONFIRMING
- For research: target=run-cycle, env.FOCUS=topic
- For testing: target=e2e-service (or e2e-service-all), env.SERVICE=service
- For scheduling: target=run-cycle (or user-specified), env.FOCUS=topic, include schedule_meta with frequency_type, cron_expression or interval_minutes, human_readable, and auto_publish
- For multi-project: generate one plan per project with label=project_name
- If depth is "deep" or "strict": set ORCHESTRATION_PROFILE=strict

## Confirmation detection
Positive: "네", "응", "예", "좋아", "확인", "실행", "해줘", "ㅇㅇ", "yes", "ok", "go", "sure", "do it", "execute", "confirm", "proceed"
Negative: "아니", "취소", "다시", "안해", "ㄴㄴ", "no", "cancel", "stop", "never mind"
If current_state is CONFIRMING and user sends a positive signal, set is_confirmation=true.
If current_state is CONFIRMING and user sends a negative signal, set is_rejection=true.

## needs_project_select
Set to true when:
- Intent is research or testing AND projects slot is empty AND topic/service is already known
- User explicitly asks about projects ("어떤 프로젝트가 있어?")

## Output JSON schema
Return EXACTLY this JSON structure (no extra keys, no markdown):
{{
  "intent": "<IntentType>",
  "confidence": <0.0-1.0>,
  "current_state": "<DialogState>",
  "next_state": "<DialogState>",
  "research_slots": {{"topic": "...", "projects": [...], "depth": "...", "target": "..."}} | null,
  "testing_slots": {{"service": "...", "scope": "...", "projects": [...]}} | null,
  "scheduling_slots": {{"topic": "...", "frequency_type": "cron|interval", "cron_expression": "...", "interval_minutes": N, "human_readable": "...", "target": "...", "auto_publish": bool, "projects": [...]}} | null,
  "needs_clarification": <bool>,
  "missing_slots": [{{"name": "...", "description": "..."}}] | null,
  "proposed_plans": [{{"target": "...", "env": {{}}, "label": "..."}}] | null,
  "needs_project_select": <bool>,
  "is_confirmation": <bool>,
  "is_rejection": <bool>,
  "response_guidance": "<instruction for Stage 2 response generation>"
}}
"""


def _build_stage1_prompt(
    dialog_ctx: DialogContext,
    projects: list[ProjectInfo],
    org_context: str = "",
) -> str:
    project_list = ", ".join(p.name for p in projects) if projects else "(none detected)"
    return _STAGE1_SYSTEM_PROMPT.format(
        allowed_targets=", ".join(sorted(ALLOWED_TARGETS)),
        allowed_env_keys=", ".join(sorted(ALLOWED_ENV_KEYS)),
        project_list=project_list,
        current_state=dialog_ctx.state.value,
        accumulated_slots=json.dumps(dialog_ctx.accumulated_slots, ensure_ascii=False),
        turn_count=dialog_ctx.turn_count,
        org_context=org_context,
    )


def run_stage1(
    user_message: str,
    conversation_history: list[dict],
    dialog_ctx: DialogContext,
    projects: list[ProjectInfo],
    org_context: str = "",
) -> IntentClassification:
    """Run Stage 1: Intent classification via Gemini JSON mode."""
    system_prompt = _build_stage1_prompt(dialog_ctx, projects, org_context=org_context)

    # Build contents: conversation history + current message
    contents: list[dict] = []
    for msg in conversation_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        contents.append({
            "role": "user" if role == "user" else "model",
            "parts": [{"text": content}],
        })
    contents.append({
        "role": "user",
        "parts": [{"text": user_message}],
    })

    try:
        raw = _call_gemini_json(system_prompt, contents)
        classification = IntentClassification.model_validate(raw)
    except (LLMParseError, LLMConnectionError, LLMTimeoutError, ValueError) as exc:
        logger.warning("Stage 1 classification failed, falling back to UNCLEAR: %s", exc)
        classification = IntentClassification(
            intent=IntentType.UNCLEAR,
            confidence=0.0,
            current_state=dialog_ctx.state,
            next_state=DialogState.IDLE,
            needs_clarification=True,
            response_guidance="Stage 1 분류 실패. 사용자에게 자연스럽게 다시 물어봐주세요.",
        )

    return classification


# ── Slot Merge ────────────────────────────────────────────────────────


def merge_slots(existing_ctx: DialogContext, classification: IntentClassification) -> DialogContext:
    """Merge newly classified slots into existing dialog context."""
    new_slots = dict(existing_ctx.accumulated_slots)

    if classification.research_slots:
        rs = classification.research_slots
        if rs.topic:
            new_slots["topic"] = rs.topic
        if rs.projects:
            new_slots["projects"] = rs.projects
        if rs.depth:
            new_slots["depth"] = rs.depth
        if rs.target:
            new_slots["target"] = rs.target

    if classification.testing_slots:
        ts = classification.testing_slots
        if ts.service:
            new_slots["service"] = ts.service
        if ts.scope:
            new_slots["scope"] = ts.scope
        if ts.projects:
            new_slots["projects"] = ts.projects

    if classification.scheduling_slots:
        ss = classification.scheduling_slots
        if ss.topic:
            new_slots["topic"] = ss.topic
        if ss.frequency_type:
            new_slots["frequency_type"] = ss.frequency_type
        if ss.cron_expression:
            new_slots["cron_expression"] = ss.cron_expression
        if ss.interval_minutes is not None:
            new_slots["interval_minutes"] = ss.interval_minutes
        if ss.human_readable:
            new_slots["human_readable"] = ss.human_readable
        if ss.target:
            new_slots["target"] = ss.target
        if ss.auto_publish is not None:
            new_slots["auto_publish"] = ss.auto_publish
        if ss.projects:
            new_slots["projects"] = ss.projects

    # Reset on topic change / rejection
    if classification.is_rejection:
        new_slots = {}

    return DialogContext(
        state=classification.next_state,
        intent=classification.intent if classification.intent != IntentType.UNCLEAR else existing_ctx.intent,
        accumulated_slots=new_slots,
        proposed_plans=classification.proposed_plans or existing_ctx.proposed_plans,
        turn_count=existing_ctx.turn_count + 1,
    )


# ── Plan Builder ──────────────────────────────────────────────────────


def build_proposed_plans(
    slots: dict[str, Any],
    intent_type: IntentType,
) -> list[dict]:
    """Build ChatPlan-compatible dicts from accumulated slots."""
    plans: list[dict] = []

    if intent_type == IntentType.RESEARCH:
        target = slots.get("target", "run-cycle")
        env: dict[str, str] = {}
        if slots.get("topic"):
            env["FOCUS"] = slots["topic"]
        if slots.get("depth") in ("deep", "strict"):
            env["ORCHESTRATION_PROFILE"] = "strict"
        projects = slots.get("projects", [])
        if projects and len(projects) > 1:
            for proj in projects:
                plans.append({"target": target, "env": {**env}, "label": proj})
        else:
            label = projects[0] if projects else ""
            plans.append({"target": target, "env": env, "label": label})

    elif intent_type == IntentType.TESTING:
        service = slots.get("service", "ai")
        scope = slots.get("scope", "single")
        if scope == "all":
            target = "e2e-service-all"
            env = {}
        else:
            target = "e2e-service"
            env = {"SERVICE": service}
        projects = slots.get("projects", [])
        if projects and len(projects) > 1:
            for proj in projects:
                plans.append({"target": target, "env": {**env}, "label": proj})
        else:
            label = projects[0] if projects else ""
            plans.append({"target": target, "env": env, "label": label})

    elif intent_type == IntentType.SCHEDULING:
        target = slots.get("target", "run-cycle")
        env = {}
        if slots.get("topic"):
            env["FOCUS"] = slots["topic"]
        schedule_meta: dict[str, Any] = {}
        if slots.get("frequency_type"):
            schedule_meta["frequency_type"] = slots["frequency_type"]
        if slots.get("cron_expression"):
            schedule_meta["cron_expression"] = slots["cron_expression"]
        if slots.get("interval_minutes") is not None:
            schedule_meta["interval_minutes"] = slots["interval_minutes"]
        if slots.get("human_readable"):
            schedule_meta["human_readable"] = slots["human_readable"]
        if slots.get("auto_publish") is not None:
            schedule_meta["auto_publish"] = slots["auto_publish"]
        projects = slots.get("projects", [])
        if projects and len(projects) > 1:
            for proj in projects:
                plans.append({
                    "target": target, "env": {**env}, "label": proj,
                    "schedule_meta": schedule_meta,
                })
        else:
            label = projects[0] if projects else ""
            plans.append({
                "target": target, "env": env, "label": label,
                "schedule_meta": schedule_meta,
            })

    return plans


# ── Stage 2 Prompts ───────────────────────────────────────────────────


_STAGE2_PROMPTS: dict[DialogState, str] = {
    DialogState.IDLE: """\
You are {assistant_name}, a friendly R&D orchestration assistant for the ora-automation platform.
Respond naturally to the user in their language. Keep it conversational.
Available projects: {project_list}
{org_context}
{response_guidance}""",

    DialogState.UNDERSTANDING: """\
You are {assistant_name}, a friendly R&D orchestration assistant.
The user has a new request but we need more clarity. Ask a focused clarifying question.
Available projects: {project_list}
{org_context}
{response_guidance}""",

    DialogState.SLOT_FILLING: """\
You are {assistant_name}, a friendly R&D orchestration assistant.
We're gathering information for the user's request. Ask naturally about the missing information.
Current slots: {accumulated_slots}
Missing: {missing_slots}
Available projects: {project_list}
{org_context}
{response_guidance}

CRITICAL — Project picker rule:
If you need the user to select projects, do NOT list project names as plain text.
Just ask naturally which projects they want to target. The system will show a picker UI.""",

    DialogState.CONFIRMING: """\
You are {assistant_name}, a friendly R&D orchestration assistant.
Present the execution plan clearly and ask the user to confirm.
Plan details: {proposed_plans}
{org_context}
{response_guidance}

Format the plan summary nicely in the user's language. End with a clear confirmation question like "실행할까요?" or "Shall I proceed?"
Do NOT include any JSON blocks in your response.""",

    DialogState.EXECUTING: """\
You are {assistant_name}, a friendly R&D orchestration assistant.
The user has confirmed. Acknowledge that execution is starting.
{org_context}
{response_guidance}""",

    DialogState.REPORTING: """\
You are {assistant_name}, a friendly R&D orchestration assistant.
Share results or report information with the user.
{org_context}
{response_guidance}""",
}


def _build_stage2_prompt(
    classification: IntentClassification,
    dialog_ctx: DialogContext,
    projects: list[ProjectInfo],
    assistant_name: str,
    org_context: str = "",
) -> str:
    """Build Stage 2 system prompt based on dialog state."""
    state = classification.next_state
    template = _STAGE2_PROMPTS.get(state, _STAGE2_PROMPTS[DialogState.IDLE])

    project_list = ", ".join(p.name for p in projects) if projects else "(none)"
    missing_slots_str = ""
    if classification.missing_slots:
        missing_slots_str = ", ".join(f"{s.name}: {s.description}" for s in classification.missing_slots)

    proposed_plans_str = ""
    if classification.proposed_plans:
        proposed_plans_str = json.dumps(classification.proposed_plans, ensure_ascii=False, indent=2)

    return template.format(
        assistant_name=assistant_name,
        project_list=project_list,
        response_guidance=classification.response_guidance,
        accumulated_slots=json.dumps(dialog_ctx.accumulated_slots, ensure_ascii=False),
        missing_slots=missing_slots_str,
        proposed_plans=proposed_plans_str,
        org_context=org_context,
    )


# ── Stage 2: Streaming Response ──────────────────────────────────────


def run_stage2_stream(
    classification: IntentClassification,
    conversation_history: list[dict],
    user_message: str,
    dialog_ctx: DialogContext,
    projects: list[ProjectInfo],
    assistant_name: str = "Ora",
    org_context: str = "",
) -> Generator[str, None, None]:
    """Run Stage 2: Generate streaming response via Gemini."""
    system_prompt = _build_stage2_prompt(classification, dialog_ctx, projects, assistant_name, org_context=org_context)

    contents: list[dict] = []
    for msg in conversation_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        contents.append({
            "role": "user" if role == "user" else "model",
            "parts": [{"text": content}],
        })
    contents.append({
        "role": "user",
        "parts": [{"text": user_message}],
    })

    yield from _stream_gemini_stage2(system_prompt, contents)


def _stream_gemini_stage2(system_prompt: str, contents: list[dict]) -> Generator[str, None, None]:
    """Gemini streaming call for Stage 2 (reuses same pattern as chat_router._stream_gemini)."""
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

            buffer = b""
            for raw_line in resp:
                buffer += raw_line
                if raw_line == b"\n" or raw_line == b"\r\n":
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
            return
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            last_error = LLMConnectionError(f"Gemini HTTP {exc.code} at {location}: {detail[:600]}")
            continue
        except LLMConnectionError:
            raise
        except Exception as exc:
            last_error = LLMConnectionError(f"Gemini stream failed: {exc}")
            continue

    raise last_error or LLMConnectionError("All Gemini locations failed")


def run_stage2_sync(
    classification: IntentClassification,
    conversation_history: list[dict],
    user_message: str,
    dialog_ctx: DialogContext,
    projects: list[ProjectInfo],
    assistant_name: str = "Ora",
    org_context: str = "",
) -> str:
    """Run Stage 2 synchronously (non-streaming) by collecting all chunks."""
    chunks: list[str] = []
    for chunk in run_stage2_stream(
        classification, conversation_history, user_message,
        dialog_ctx, projects, assistant_name, org_context=org_context,
    ):
        chunks.append(chunk)
    return "".join(chunks)


# ── Plan coercion (validate proposed plans) ───────────────────────────


def coerce_proposed_plans(raw_plans: list[dict] | None) -> tuple[
    ChatPlan | None, list[ChatPlan] | None
]:
    """Validate and convert proposed plans to ChatPlan objects.

    Returns (single_plan, multi_plans).
    """
    if not raw_plans:
        return None, None

    valid_plans: list[ChatPlan] = []
    for p in raw_plans:
        if not isinstance(p, dict):
            continue
        try:
            target, env, _ = _coerce_plan(p)
            valid_plans.append(ChatPlan(
                target=target,
                env=env,
                label=str(p.get("label", "")),
            ))
        except RuntimeError:
            continue

    if not valid_plans:
        return None, None

    if len(valid_plans) == 1:
        return valid_plans[0], None

    return None, valid_plans
