from __future__ import annotations

import json
import logging
import os
import re
import ssl
import time
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from ora_rd_orchestrator.chatbot import (
    ALLOWED_ENV_KEYS,
    ALLOWED_TARGETS,
    _coerce_plan,
    _extract_json,
)

from .config import settings
from .database import SessionLocal, get_db
from .models import ChatConversation, ChatMessageRow
from .schemas import (
    ChatMessageRead,
    ChatPlan,
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationDetail,
    ConversationList,
    ConversationRead,
    ReportListItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])

# ── Gemini direct call (mirrors scripts/llm_round_openai.py pattern) ─────

_SYSTEM_PROMPT = """\
You are Ora, a friendly R&D orchestration assistant for the ora-automation platform.

Your job:
1. Chat naturally with the user to understand what they want to do.
2. When you have enough information to execute an orchestration, include a JSON plan block.
3. If the user's intent is still unclear, ask clarifying questions. Do NOT generate a plan until you are confident.

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

When you are ready to propose a plan, include EXACTLY this JSON block at the END of your message:
```json
{{"target": "<target>", "env": {{"KEY": "VALUE"}}, "plan_ready": true}}
```

If you are NOT ready (still chatting), do NOT include any JSON block. Just reply naturally in the user's language.\
"""


def _resolve_ca_bundle() -> str:
    env_bundle = os.getenv("ORA_RD_CA_BUNDLE", "").strip() or os.getenv("SSL_CERT_FILE", "").strip()
    if env_bundle and os.path.exists(env_bundle):
        return env_bundle
    try:
        import certifi

        bundle = certifi.where()
        if bundle and os.path.exists(bundle):
            return bundle
    except Exception:
        pass
    return ""


def _urlopen(req: request.Request, timeout: float):
    ca_bundle = _resolve_ca_bundle()
    retries = 2
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            if ca_bundle:
                context = ssl.create_default_context(cafile=ca_bundle)
                return request.urlopen(req, timeout=timeout, context=context)
            return request.urlopen(req, timeout=timeout)
        except Exception as exc:
            last_exc = exc
            if attempt >= retries:
                break
            time.sleep(1.0 * attempt)
    raise last_exc or RuntimeError("HTTP request failed")


def _get_gemini_token() -> str:
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not cred_path or not os.path.exists(cred_path):
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS not set or file missing")

    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_file(
        cred_path,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    credentials.refresh(GoogleAuthRequest())
    if not credentials.token:
        raise RuntimeError("Failed to obtain Google OAuth token")
    return credentials.token


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


def _build_system_prompt() -> str:
    return _SYSTEM_PROMPT.format(
        allowed_targets=", ".join(sorted(ALLOWED_TARGETS)),
        allowed_env_keys=", ".join(sorted(ALLOWED_ENV_KEYS)),
    )


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
            ca_bundle = _resolve_ca_bundle()
            if ca_bundle:
                context = ssl.create_default_context(cafile=ca_bundle)
                resp = request.urlopen(req_obj, timeout=timeout, context=context)
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


def _extract_plan_from_reply(text: str) -> tuple[str, ChatPlan | None]:
    """Extract plan JSON from reply text, return (clean_reply, plan_or_none)."""
    pattern = r"```json\s*(\{.*?\})\s*```"
    match = re.search(pattern, text, re.DOTALL)

    plan_json: dict | None = None
    if match:
        try:
            plan_json = json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    if not plan_json:
        # Try _extract_json from chatbot module as fallback
        extracted = _extract_json(text)
        if extracted and extracted.get("plan_ready"):
            plan_json = extracted

    if not plan_json or not plan_json.get("plan_ready"):
        return text, None

    # Validate via chatbot _coerce_plan
    try:
        target, env, _ = _coerce_plan(plan_json)
    except RuntimeError:
        return text, None

    # Remove the JSON block from the displayed reply
    clean_reply = re.sub(r"```json\s*\{.*?\}\s*```", "", text, flags=re.DOTALL).strip()
    if not clean_reply:
        clean_reply = f"Ready to execute **{target}**."

    return clean_reply, ChatPlan(target=target, env=env)


# ── Endpoints ────────────────────────────────────────────────────────


def _ensure_conversation(db: Session, conversation_id: str | None) -> ChatConversation:
    """Get or create a conversation row."""
    if conversation_id:
        conv = db.get(ChatConversation, conversation_id)
        if conv:
            return conv
    conv = ChatConversation(id=conversation_id or str(uuid.uuid4()), title="")
    db.add(conv)
    db.flush()
    return conv


def _persist_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: str,
    plan: ChatPlan | None = None,
    run_id: str | None = None,
) -> None:
    plan_dict = {"target": plan.target, "env": plan.env} if plan else None
    db.add(ChatMessageRow(
        conversation_id=conversation_id,
        role=role,
        content=content,
        plan=plan_dict,
        run_id=run_id,
    ))


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
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

    reply, plan = _extract_plan_from_reply(raw_reply)

    # Persist to DB
    conv = _ensure_conversation(db, req.conversation_id)
    if not conv.title and req.message:
        conv.title = req.message[:100]
    _persist_message(db, conv.id, "user", req.message)
    _persist_message(db, conv.id, "assistant", reply, plan=plan)
    db.commit()

    return ChatResponse(reply=reply, plan=plan)


@router.post("/chat/stream")
def chat_stream(req: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    """SSE streaming chat endpoint. Yields tokens as they arrive from Gemini."""
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
    conv = _ensure_conversation(db, req.conversation_id)
    if not conv.title and req.message:
        conv.title = req.message[:100]
    _persist_message(db, conv.id, "user", req.message)
    db.commit()
    conv_id = conv.id

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

        # After streaming completes, check for plan in the full response
        reply, plan = _extract_plan_from_reply(full_text)
        done_payload: dict[str, Any] = {"type": "done", "full_reply": reply}
        if plan:
            done_payload["plan"] = {"target": plan.target, "env": plan.env}
        yield f"data: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

        # Persist assistant reply after streaming completes
        try:
            persist_db = SessionLocal()
            try:
                _persist_message(persist_db, conv_id, "assistant", reply, plan=plan)
                persist_db.commit()
            finally:
                persist_db.close()
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


# ── Conversations ────────────────────────────────────────────────────


@router.get("/conversations", response_model=ConversationList)
def list_conversations(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> ConversationList:
    rows = (
        db.query(ChatConversation)
        .order_by(ChatConversation.updated_at.desc())
        .limit(limit)
        .all()
    )
    total = db.query(ChatConversation).count()
    return ConversationList(
        items=[ConversationRead.model_validate(r) for r in rows],
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
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return ConversationRead.model_validate(conv)


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
    return ConversationDetail(
        **ConversationRead.model_validate(conv).model_dump(),
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
def update_conversation_title(
    conversation_id: str,
    payload: ConversationCreate,
    db: Session = Depends(get_db),
) -> ConversationRead:
    conv = db.get(ChatConversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="conversation not found")
    conv.title = payload.title
    db.commit()
    db.refresh(conv)
    return ConversationRead.model_validate(conv)


# ── Reports ──────────────────────────────────────────────────────────


def _report_dirs() -> list[Path]:
    dirs: list[Path] = []
    if settings.run_output_dir.is_dir():
        dirs.append(settings.run_output_dir)
    research_reports = settings.automation_root / "research_reports"
    if research_reports.is_dir() and research_reports != settings.run_output_dir:
        dirs.append(research_reports)
    return dirs


def _scan_reports() -> list[ReportListItem]:
    items: list[ReportListItem] = []
    seen: set[str] = set()
    for base_dir in _report_dirs():
        for path in sorted(base_dir.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in (".md", ".json"):
                continue
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
    if ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")

    for base_dir in _report_dirs():
        candidate = base_dir / filename
        if candidate.is_file() and candidate.suffix.lower() in (".md", ".json"):
            media_type = "text/markdown" if candidate.suffix.lower() == ".md" else "application/json"
            return FileResponse(str(candidate), media_type=media_type)

    raise HTTPException(status_code=404, detail="report not found")
