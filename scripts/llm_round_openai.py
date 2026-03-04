#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import ssl
import sys
import time
import uuid
from typing import Any
from urllib import error, request


OPENAI_BASE_URL_ENV = "ORA_RD_LLM_BASE_URL"
OPENAI_MODEL_ENV = "ORA_RD_LLM_MODEL"
OPENAI_TIMEOUT_ENV = "ORA_RD_LLM_HTTP_TIMEOUT"
OPENAI_TEMPERATURE_ENV = "ORA_RD_LLM_TEMPERATURE"
LLM_PROVIDER_ENV = "ORA_RD_LLM_PROVIDER"
GEMINI_MODEL_ENV = "ORA_RD_GEMINI_MODEL"
GEMINI_BASE_URL_ENV = "ORA_RD_GEMINI_BASE_URL"


def _read_input_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        raise RuntimeError("empty stdin payload")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"stdin is not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("stdin JSON must be object")
    return parsed


def _resolve_ca_bundle() -> str:
    env_bundle = os.getenv("ORA_RD_CA_BUNDLE", "").strip() or os.getenv("SSL_CERT_FILE", "").strip()
    if env_bundle and os.path.exists(env_bundle):
        return env_bundle
    try:
        import certifi  # type: ignore

        bundle = certifi.where()
        if bundle and os.path.exists(bundle):
            return bundle
    except Exception:
        pass
    return ""


def _http_retry_count() -> int:
    raw = os.getenv("ORA_RD_LLM_HTTP_RETRIES", "").strip()
    if not raw:
        return 3
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


def _http_retry_delay() -> float:
    raw = os.getenv("ORA_RD_LLM_HTTP_RETRY_DELAY", "").strip()
    if not raw:
        return 1.0
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 1.0


def _urlopen(req: request.Request, timeout: float):
    ca_bundle = _resolve_ca_bundle()
    retries = _http_retry_count()
    retry_delay = _http_retry_delay()
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
            if retry_delay > 0:
                time.sleep(retry_delay * attempt)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("HTTP request failed with unknown error")


def _load_env_value_from_file(path: str, key: str) -> str:
    if not path or not os.path.exists(path):
        return ""
    prefix = f"{key}="
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                if raw.startswith("export "):
                    raw = raw[len("export ") :].strip()
                if not raw.startswith(prefix):
                    continue
                value = raw[len(prefix) :].strip()
                if value and value[0] in {"'", '"'} and value[-1:] == value[0]:
                    value = value[1:-1]
                return value.strip()
    except Exception:
        return ""
    return ""


def _resolve_gemini_api_key() -> str:
    direct = os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip()
    if direct:
        return direct

    script_dir = os.path.abspath(os.path.dirname(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, ".."))
    ora_root = os.path.abspath(os.path.join(repo_root, ".."))
    candidate_files = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(repo_root, ".env"),
        os.path.join(repo_root, ".env.local"),
        os.path.join(ora_root, "OraAiServer", ".env"),
        os.path.join(ora_root, "OraAiServer", ".env.local"),
    ]
    for file_path in candidate_files:
        value = _load_env_value_from_file(file_path, "GEMINI_API_KEY")
        if value:
            return value
        value = _load_env_value_from_file(file_path, "GOOGLE_API_KEY")
        if value:
            return value
    return ""


def _extract_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise RuntimeError("empty LLM response content")
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("LLM response is not JSON object")
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM JSON parse failed: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM JSON root is not object")
    return parsed


def _risk_to_score(risk: str) -> float:
    normalized = (risk or "").strip().lower()
    if normalized == "high":
        return 8.5
    if normalized == "medium":
        return 6.5
    return 3.5


def _score_to_risk(score: float) -> str:
    if score >= 8.0:
        return "high"
    if score >= 6.0:
        return "medium"
    return "low"


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, min_v: float, max_v: float) -> float:
    if value < min_v:
        return min_v
    if value > max_v:
        return max_v
    return value


def _coerce_services(raw: Any, fallback: list[str]) -> list[str]:
    if isinstance(raw, str):
        items = [x.strip() for x in raw.split(",") if x.strip()]
        return items or fallback
    if isinstance(raw, list):
        items = [str(x).strip() for x in raw if str(x).strip()]
        return items or fallback
    return fallback


def _normalize_deliberation_output(payload: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    topics = payload.get("topics", [])
    topic_ids: set[str] = set()
    if isinstance(topics, list):
        for item in topics:
            if isinstance(item, dict):
                topic_id = str(item.get("topic_id", "")).strip()
                if topic_id:
                    topic_ids.add(topic_id)
    first_topic_id = next(iter(topic_ids), "")

    service_scope = payload.get("service_scope", [])
    if isinstance(service_scope, list):
        fallback_services = [str(x).strip() for x in service_scope if str(x).strip()]
    else:
        fallback_services = []
    if not fallback_services:
        fallback_services = ["global"]

    agent_rules = payload.get("agent_rules", {})
    owner_fallback = "Researcher"
    if isinstance(agent_rules, dict):
        for key in agent_rules.keys():
            k = str(key).strip()
            if k:
                owner_fallback = k
                break

    decisions_raw = out.get("decisions", [])
    if not isinstance(decisions_raw, list) or not decisions_raw:
        raise RuntimeError("LLM deliberation response must include non-empty 'decisions'")

    normalized_decisions: list[dict[str, Any]] = []
    for item in decisions_raw:
        if not isinstance(item, dict):
            continue

        topic_id = str(item.get("topic_id", "")).strip()
        if not topic_id or (topic_ids and topic_id not in topic_ids):
            topic_id = first_topic_id
        if not topic_id:
            continue

        owner = str(item.get("owner", "")).strip() or owner_fallback
        rationale = str(item.get("rationale", "")).strip()
        if not rationale:
            continue

        risk_score = _coerce_float(item.get("risk_score"), _risk_to_score(str(item.get("risk", ""))))
        risk_score = _clamp(risk_score, 0.0, 10.0)
        risk = str(item.get("risk", "")).strip().lower() or _score_to_risk(risk_score)
        if risk not in ("low", "medium", "high"):
            risk = _score_to_risk(risk_score)

        confidence = _clamp(_coerce_float(item.get("confidence"), 0.6), 0.0, 1.0)
        score_delta = _clamp(_coerce_float(item.get("score_delta"), 0.0), -5.0, 5.0)
        services = _coerce_services(item.get("service"), fallback=fallback_services)
        fail_label = str(item.get("fail_label", "")).strip().upper()
        if fail_label not in ("SKIP", "RETRY", "STOP"):
            if risk_score >= 8.0:
                fail_label = "STOP"
            elif risk_score >= 6.0:
                fail_label = "RETRY"
            else:
                fail_label = "SKIP"

        due = str(item.get("due", "")).strip()
        if not due:
            due = (dt.date.today() + dt.timedelta(days=14)).isoformat()

        next_action = str(item.get("next_action", "")).strip() or "근거 보강 후 PoC 실행"

        normalized_decisions.append(
            {
                "decision_id": str(item.get("decision_id", "")).strip() or f"decision-{uuid.uuid4()}",
                "owner": owner,
                "topic_id": topic_id,
                "rationale": rationale,
                "risk": risk,
                "risk_score": risk_score,
                "next_action": next_action,
                "due": due,
                "service": services,
                "score_delta": score_delta,
                "confidence": confidence,
                "fail_label": fail_label,
            }
        )

    if not normalized_decisions:
        raise RuntimeError("LLM deliberation response has no valid decision objects")

    score_adjustments = out.get("score_adjustments", {})
    if not isinstance(score_adjustments, dict):
        score_adjustments = {}
    action_log = out.get("action_log", [])
    if not isinstance(action_log, list):
        action_log = []
    round_summary = out.get("round_summary", {})
    if not isinstance(round_summary, dict):
        round_summary = {}
    if "round" not in round_summary:
        round_summary["round"] = payload.get("round", 1)
    if "summary" not in round_summary:
        round_summary["summary"] = "LLM deliberation completed"

    return {
        "score_adjustments": score_adjustments,
        "decisions": normalized_decisions,
        "action_log": action_log,
        "round_summary": round_summary,
    }


def _normalize_consensus_output(payload: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    topics = payload.get("topics", [])
    valid_topic_ids: set[str] = set()
    if isinstance(topics, list):
        for item in topics:
            if isinstance(item, dict):
                topic_id = str(item.get("topic_id", "")).strip()
                if topic_id:
                    valid_topic_ids.add(topic_id)

    candidate = out.get("final_consensus", out.get("consensus", []))
    if not isinstance(candidate, list):
        raise RuntimeError("LLM consensus response must include list 'final_consensus'")

    final_consensus: list[str] = []
    for item in candidate:
        topic_id = str(item).strip()
        if not topic_id:
            continue
        if valid_topic_ids and topic_id not in valid_topic_ids:
            continue
        if topic_id in final_consensus:
            continue
        final_consensus.append(topic_id)

    if not final_consensus:
        raise RuntimeError("LLM consensus response produced empty final_consensus")

    rationale = str(out.get("rationale", "")).strip()
    if not rationale:
        raise RuntimeError("LLM consensus response missing rationale")

    concerns = out.get("concerns", [])
    if not isinstance(concerns, list):
        concerns = []

    return {
        "final_consensus": final_consensus,
        "rationale": rationale,
        "concerns": concerns,
    }


def _normalize_scoring_output(payload: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    """Normalize LLM scoring response."""
    scores_raw = out.get("scores", {})
    if not isinstance(scores_raw, dict):
        raise RuntimeError("LLM scoring response must include 'scores' dict")

    topics = payload.get("topics", {})
    valid_ids = set(topics.keys()) if isinstance(topics, dict) else set()

    normalized: dict[str, Any] = {}
    for topic_id, item in scores_raw.items():
        if valid_ids and topic_id not in valid_ids:
            continue
        if not isinstance(item, dict):
            continue
        entry: dict[str, Any] = {}
        for key in ("impact", "feasibility", "novelty", "research_signal", "risk_penalty"):
            entry[key] = _clamp(_coerce_float(item.get(key), 5.0), 0.0, 10.0)
        entry["support"] = bool(item.get("support", False))
        entry["challenge"] = bool(item.get("challenge", False))
        entry["rationale"] = str(item.get("rationale", "")).strip()
        normalized[topic_id] = entry

    if not normalized:
        raise RuntimeError("LLM scoring response produced no valid scores")

    return {"scores": normalized}


def _normalize_strategy_output(payload: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    """Normalize LLM strategy card response."""
    cards = out.get("strategy_cards", out.get("cards", []))
    if not isinstance(cards, list):
        raise RuntimeError("LLM strategy response must include 'strategy_cards' list")
    if not cards:
        raise RuntimeError("LLM strategy response produced no cards")

    normalized: list[dict[str, Any]] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        topic_id = str(card.get("topic_id", "")).strip()
        if not topic_id:
            continue
        normalized.append({
            "topic_id": topic_id,
            "innovation_ideas": card.get("innovation_ideas", []),
            "competitive_edge": str(card.get("competitive_edge", "")).strip(),
            "cause_analysis": card.get("cause_analysis", []),
            "action_plan": card.get("action_plan", []),
            "success_metrics": card.get("success_metrics", []),
            "expected_impact": str(card.get("expected_impact", "")).strip(),
            "risk_mitigation": str(card.get("risk_mitigation", "")).strip(),
        })
    return {"strategy_cards": normalized}


def _normalize_qa_output(payload: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    """Normalize LLM QA verification response."""
    verification = out.get("verification", out.get("qa_results", []))
    if not isinstance(verification, list):
        raise RuntimeError("LLM QA response must include 'verification' list")
    if not verification:
        raise RuntimeError("LLM QA response produced no results")

    normalized: list[dict[str, Any]] = []
    for item in verification:
        if not isinstance(item, dict):
            continue
        topic_id = str(item.get("topic_id", "")).strip()
        if not topic_id:
            continue
        normalized.append({
            "topic_id": topic_id,
            "passed": bool(item.get("passed", True)),
            "evidence_quality": _clamp(_coerce_float(item.get("evidence_quality"), 5.0), 0.0, 10.0),
            "concerns": item.get("concerns", []),
            "recommendation": str(item.get("recommendation", "")).strip(),
            "confidence": _clamp(_coerce_float(item.get("confidence"), 0.5), 0.0, 1.0),
        })
    return {"verification": normalized}


def _build_messages(payload: dict[str, Any]) -> tuple[str, str]:
    version = str(payload.get("version", "")).strip()

    if version == "llm-deliberation-v1":
        system = (
            "You are a senior R&D committee deliberation model. "
            "Return ONLY JSON object that strictly matches requested output_contract. "
            "At least one decision is required. risk_score must be numeric 0~10."
        )
    elif version == "llm-consensus-v2":
        system = (
            "You are a final consensus model for R&D topic selection. "
            "Return ONLY JSON object with final_consensus, rationale, concerns. "
            "final_consensus must include at least one topic_id from input topics."
        )
    elif version == "llm-scoring-v1":
        system = (
            "당신은 R&D 연구 주제 평가 전문가입니다. "
            "각 토픽에 대해 impact, feasibility, novelty, research_signal, risk_penalty (0~10), "
            "support (bool), challenge (bool), rationale (string)을 JSON으로 반환하세요. "
            "반드시 {\"scores\": {\"topic_id\": {...}}} 형식만 출력하세요."
        )
    elif version == "llm-strategy-v1":
        system = (
            "당신은 R&D 전략 기획 전문가입니다. 각 토픽에 대해 혁신 아이디어, 경쟁 우위, "
            "원인 진단, 실행 계획, 성공 지표, 예상 임팩트, 리스크 완화 방안을 "
            "구체적이고 차별화된 관점으로 작성하세요. "
            "반드시 {\"strategy_cards\": [{...}]} 형식만 출력하세요. "
            "아이디어는 시장에서 돋보일 수 있는 구체적이고 독창적인 제안이어야 합니다."
        )
    elif version == "llm-qa-v1":
        system = (
            "당신은 R&D 품질 검증(QA) 전문가입니다. 각 토픽의 증거 품질, "
            "실행 가능성, 리스크를 종합적으로 검증하세요. "
            "반드시 {\"verification\": [{\"topic_id\": ..., \"passed\": bool, ...}]} 형식만 출력하세요."
        )
    elif version in ("llm-phase-plan-v1", "llm-consensus-rank-v1", "llm-fallback-decisions-v1"):
        system = str(payload.get("system_prompt", "")).strip() or (
            "You are an R&D orchestration assistant. Return ONLY valid JSON."
        )
    else:
        raise RuntimeError(f"Unsupported payload version: {version}")

    # Inject system_prompt from payload if present (persona injection)
    persona_prompt = payload.get("system_prompt", "")
    if persona_prompt:
        system = f"{system}\n\n## 페르소나\n{persona_prompt}"

    user = (
        "Use the following payload as source of truth. "
        "Output valid JSON only.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    return system, user


def _call_openai_chat(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    base_url = os.getenv(OPENAI_BASE_URL_ENV, "").strip() or "https://api.openai.com/v1"
    model = os.getenv(OPENAI_MODEL_ENV, "").strip() or "gpt-4o-mini"
    timeout = float(os.getenv(OPENAI_TIMEOUT_ENV, "90").strip() or 90)
    temperature = float(os.getenv(OPENAI_TEMPERATURE_ENV, "0.2").strip() or 0.2)

    body = {
        "model": model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }

    req = request.Request(
        url=f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with _urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI HTTP {exc.code}: {detail[:1200]}") from exc
    except Exception as exc:
        raise RuntimeError(f"OpenAI request failed: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI response JSON parse failed: {exc}") from exc

    try:
        choice = payload["choices"][0]
        content = choice["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"OpenAI response missing choices/message/content: {payload}") from exc

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if text:
                    parts.append(str(text))
        content = "\n".join(parts).strip()

    return _extract_json_object(str(content))


def _gemini_model_name() -> str:
    return (
        os.getenv("GEMINI_MODEL", "").strip()
        or os.getenv(GEMINI_MODEL_ENV, "").strip()
        or os.getenv("MCP_GEMINI_MODEL", "").strip()
        or "gemini-2.5-flash"
    )


def _call_gemini_vertex(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if not cred_path:
        raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS is not set")
    if not os.path.exists(cred_path):
        raise RuntimeError(f"Service account file not found: {cred_path}")

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "").strip()
    if not project_id:
        raise RuntimeError("GOOGLE_CLOUD_PROJECT_ID is not set")

    primary_location = os.getenv("GOOGLE_CLOUD_LOCATION", "").strip() or "us-central1"
    fallback_raw = os.getenv("GOOGLE_CLOUD_FALLBACK_LOCATIONS", "").strip()
    fallback_locations = [x.strip() for x in fallback_raw.split(",") if x.strip()]
    locations = [primary_location] + [x for x in fallback_locations if x != primary_location]

    timeout = float(os.getenv(OPENAI_TIMEOUT_ENV, "90").strip() or 90)
    temperature = float(os.getenv(OPENAI_TEMPERATURE_ENV, "0.2").strip() or 0.2)
    model = _gemini_model_name()

    try:
        from google.auth.transport.requests import Request as GoogleAuthRequest  # type: ignore
        from google.oauth2 import service_account  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "google-auth dependency is required for Vertex Gemini auth. "
            "Run: .venv/bin/pip install google-auth requests"
        ) from exc

    credentials = service_account.Credentials.from_service_account_file(
        cred_path,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    refresh_retries = _http_retry_count()
    refresh_delay = _http_retry_delay()
    refresh_last_exc: Exception | None = None
    for attempt in range(1, refresh_retries + 1):
        try:
            credentials.refresh(GoogleAuthRequest())
            refresh_last_exc = None
            break
        except Exception as exc:
            refresh_last_exc = exc
            if attempt >= refresh_retries:
                break
            if refresh_delay > 0:
                time.sleep(refresh_delay * attempt)
    if refresh_last_exc is not None:
        raise RuntimeError(
            "Google OAuth token refresh failed. "
            "Check DNS/network to oauth2.googleapis.com or set GEMINI_API_KEY fallback. "
            f"detail={refresh_last_exc}"
        ) from refresh_last_exc
    token = credentials.token
    if not token:
        raise RuntimeError("Failed to obtain Google OAuth token from service account")

    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": temperature,
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
                raise RuntimeError(f"Vertex response missing candidates: {payload}")
            parts = candidates[0].get("content", {}).get("parts", [])
            texts: list[str] = []
            if isinstance(parts, list):
                for part in parts:
                    if isinstance(part, dict) and part.get("text"):
                        texts.append(str(part["text"]))
            content = "\n".join(texts).strip()
            return _extract_json_object(content)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            last_error = RuntimeError(f"Vertex HTTP {exc.code} at {location}: {detail[:1200]}")
            continue
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"Vertex Gemini failed across locations {locations}: {last_error}")


def _call_gemini_api_key(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    api_key = _resolve_gemini_api_key()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY/GOOGLE_API_KEY is required")

    base_url = os.getenv(GEMINI_BASE_URL_ENV, "").strip() or "https://generativelanguage.googleapis.com/v1beta"
    model = _gemini_model_name()
    timeout = float(os.getenv(OPENAI_TIMEOUT_ENV, "90").strip() or 90)
    temperature = float(os.getenv(OPENAI_TEMPERATURE_ENV, "0.2").strip() or 0.2)

    body = {
        "system_instruction": {
            "parts": [{"text": system_prompt}],
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }

    req = request.Request(
        url=f"{base_url.rstrip('/')}/models/{model}:generateContent?key={api_key}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with _urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="ignore")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Gemini HTTP {exc.code}: {detail[:1200]}") from exc
    except Exception as exc:
        raise RuntimeError(f"Gemini request failed: {exc}") from exc

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini response JSON parse failed: {exc}") from exc

    try:
        candidates = payload["candidates"]
        first = candidates[0]
        parts = first["content"]["parts"]
        texts = []
        for part in parts:
            if isinstance(part, dict) and part.get("text"):
                texts.append(str(part["text"]))
        content = "\n".join(texts).strip()
    except Exception as exc:
        raise RuntimeError(f"Gemini response missing text content: {payload}") from exc

    return _extract_json_object(content)


def _call_gemini(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    # Vertex(Service Account) 우선. 실패 시 API key fallback 허용.
    disable_vertex_raw = os.getenv("ORA_RD_GEMINI_DISABLE_VERTEX", "").strip().lower()
    disable_vertex = disable_vertex_raw in {"1", "true", "yes", "on"}
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip() and not disable_vertex:
        try:
            return _call_gemini_vertex(system_prompt, user_prompt)
        except Exception as vertex_exc:
            has_api_key = bool(_resolve_gemini_api_key())
            if not has_api_key:
                raise RuntimeError(
                    "Gemini Vertex failed and API key fallback is unavailable. "
                    f"vertex_error={vertex_exc}"
                ) from vertex_exc
            try:
                return _call_gemini_api_key(system_prompt, user_prompt)
            except Exception as api_exc:
                raise RuntimeError(
                    "Gemini Vertex failed, and API key fallback also failed. "
                    f"vertex_error={vertex_exc}; api_key_error={api_exc}"
                ) from api_exc

    return _call_gemini_api_key(system_prompt, user_prompt)


def _call_llm(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    provider = os.getenv(LLM_PROVIDER_ENV, "auto").strip().lower()
    if provider not in {"auto", "gemini", "openai"}:
        raise RuntimeError(f"Invalid {LLM_PROVIDER_ENV}: {provider}")

    if provider == "gemini":
        return _call_gemini(system_prompt, user_prompt)
    if provider == "openai":
        return _call_openai_chat(system_prompt, user_prompt)

    if os.getenv("GEMINI_API_KEY", "").strip() or os.getenv("GOOGLE_API_KEY", "").strip():
        return _call_gemini(system_prompt, user_prompt)
    return _call_openai_chat(system_prompt, user_prompt)


def main() -> int:
    payload = _read_input_payload()
    version = str(payload.get("version", "")).strip()
    system_prompt, user_prompt = _build_messages(payload)
    out = _call_llm(system_prompt, user_prompt)

    if version == "llm-deliberation-v1":
        normalized = _normalize_deliberation_output(payload, out)
    elif version == "llm-consensus-v2":
        normalized = _normalize_consensus_output(payload, out)
    elif version == "llm-scoring-v1":
        normalized = _normalize_scoring_output(payload, out)
    elif version == "llm-strategy-v1":
        normalized = _normalize_strategy_output(payload, out)
    elif version == "llm-qa-v1":
        normalized = _normalize_qa_output(payload, out)
    elif version in ("llm-phase-plan-v1", "llm-consensus-rank-v1", "llm-fallback-decisions-v1"):
        # Passthrough — these versions return structured JSON directly
        normalized = out
    else:
        raise RuntimeError(f"Unsupported payload version: {version}")

    sys.stdout.write(json.dumps(normalized, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        sys.stderr.write(f"[llm_round_openai] {exc}\n")
        raise SystemExit(1)
