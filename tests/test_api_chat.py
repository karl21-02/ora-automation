"""API integration tests for UPCE chat endpoints.

All Gemini calls are mocked — these tests run without network access.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from ora_automation_api.exceptions import LLMConnectionError
from conftest import MOCK_PROJECTS, make_stage1_response, make_stage2_chunks


# ── Helpers ────────────────────────────────────────────────────────────


def _chat(client, message: str, history=None, conversation_id=None):
    body = {"message": message}
    if history:
        body["history"] = history
    if conversation_id:
        body["conversation_id"] = conversation_id
    return client.post("/api/v1/chat", json=body)


def _chat_stream(client, message: str, history=None, conversation_id=None):
    body = {"message": message}
    if history:
        body["history"] = history
    if conversation_id:
        body["conversation_id"] = conversation_id
    return client.post("/api/v1/chat/stream", json=body)


def _parse_sse(response) -> list[dict]:
    events = []
    for line in response.text.split("\n"):
        line = line.strip()
        if line.startswith("data: ") and line[6:] != "[DONE]":
            try:
                events.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                pass
    return events


# ── Tests ──────────────────────────────────────────────────────────────


class TestChatCreatesConversation:
    @patch("ora_automation_api.dialog_engine._stream_gemini_stage2")
    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_chat_creates_conversation(self, mock_s1, mock_s2, client):
        mock_s1.return_value = make_stage1_response(
            intent="general_chat", confidence=0.9, next_state="idle",
            response_guidance="인사하세요.",
        )
        mock_s2.return_value = make_stage2_chunks("안녕하세요!")

        resp = _chat(client, "안녕")
        assert resp.status_code == 200
        data = resp.json()
        assert data["reply"]
        assert "안녕" in data["reply"]


class TestChatReturnsDialogState:
    @patch("ora_automation_api.dialog_engine._stream_gemini_stage2")
    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_chat_returns_dialog_state(self, mock_s1, mock_s2, client):
        mock_s1.return_value = make_stage1_response(
            intent="research", confidence=0.9,
            next_state="understanding",
            research_slots={"topic": "보안"},
            response_guidance="주제를 물어보세요.",
        )
        mock_s2.return_value = make_stage2_chunks("어떤 주제를 연구하고 싶으세요?")

        resp = _chat(client, "리서치 하고 싶어")
        assert resp.status_code == 200
        data = resp.json()
        assert data["dialog_state"] == "understanding"
        assert data["intent_summary"] is not None
        assert "research" in data["intent_summary"]


class TestChatConfirmationFlow:
    @patch("ora_automation_api.dialog_engine._stream_gemini_stage2")
    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_chat_confirmation_flow(self, mock_s1, mock_s2, client):
        conv_id = "test-confirm-flow"

        # Turn 1: reach CONFIRMING state
        mock_s1.return_value = make_stage1_response(
            intent="research", confidence=0.95,
            next_state="confirming",
            research_slots={"topic": "보안", "projects": ["OraAiServer"]},
            proposed_plans=[
                {"target": "run-cycle", "env": {"FOCUS": "보안"}, "label": "OraAiServer"},
            ],
        )
        mock_s2.return_value = make_stage2_chunks("실행할까요?")
        resp1 = _chat(client, "보안 리서치 OraAiServer", conversation_id=conv_id)
        assert resp1.status_code == 200
        assert resp1.json()["dialog_state"] == "confirming"
        assert resp1.json()["confirmation_required"] is True

        # Turn 2: confirm → EXECUTING
        mock_s1.return_value = make_stage1_response(
            intent="confirm", confidence=0.98,
            current_state="confirming", next_state="executing",
            is_confirmation=True,
        )
        resp2 = _chat(
            client, "확인",
            conversation_id=conv_id,
            history=[
                {"role": "user", "content": "보안 리서치 OraAiServer"},
                {"role": "assistant", "content": "실행할까요?"},
            ],
        )
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["dialog_state"] == "executing"
        assert data["plan"] is not None
        assert data["plan"]["target"] == "run-cycle"


class TestChatRejectionResets:
    @patch("ora_automation_api.dialog_engine._stream_gemini_stage2")
    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_chat_rejection_resets(self, mock_s1, mock_s2, client):
        conv_id = "test-reject-flow"

        # Turn 1: reach CONFIRMING
        mock_s1.return_value = make_stage1_response(
            intent="research", confidence=0.95,
            next_state="confirming",
            proposed_plans=[
                {"target": "run-cycle", "env": {"FOCUS": "보안"}, "label": "A"},
            ],
        )
        mock_s2.return_value = make_stage2_chunks("실행할까요?")
        _chat(client, "리서치", conversation_id=conv_id)

        # Turn 2: reject
        mock_s1.return_value = make_stage1_response(
            intent="reject", confidence=0.90,
            current_state="confirming", next_state="idle",
            is_rejection=True,
        )
        resp = _chat(
            client, "취소",
            conversation_id=conv_id,
            history=[
                {"role": "user", "content": "리서치"},
                {"role": "assistant", "content": "실행할까요?"},
            ],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["dialog_state"] == "idle"
        assert "취소" in data["reply"]


class TestStreamSSEFormat:
    @patch("ora_automation_api.dialog_engine._stream_gemini_stage2")
    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_stream_sse_format(self, mock_s1, mock_s2, client):
        mock_s1.return_value = make_stage1_response(
            intent="general_chat", confidence=0.9, next_state="idle",
        )
        mock_s2.return_value = make_stage2_chunks("Hello ", "World")

        resp = _chat_stream(client, "hi")
        assert resp.status_code == 200
        events = _parse_sse(resp)
        token_events = [e for e in events if e.get("type") == "token"]
        done_events = [e for e in events if e.get("type") == "done"]
        assert len(token_events) >= 1
        assert len(done_events) == 1


class TestStreamDoneHasUPCEFields:
    @patch("ora_automation_api.dialog_engine._stream_gemini_stage2")
    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_stream_done_has_upce_fields(self, mock_s1, mock_s2, client):
        mock_s1.return_value = make_stage1_response(
            intent="research", confidence=0.85,
            next_state="understanding",
            response_guidance="주제를 물어보세요.",
        )
        mock_s2.return_value = make_stage2_chunks("어떤 주제?")

        resp = _chat_stream(client, "리서치")
        events = _parse_sse(resp)
        done = [e for e in events if e.get("type") == "done"][0]
        assert "dialog_state" in done
        assert done["dialog_state"] == "understanding"
        assert "intent_summary" in done
        assert "research" in done["intent_summary"]


class TestChatGeminiFailureFallback:
    @patch("ora_automation_api.dialog_engine._stream_gemini_stage2")
    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_chat_gemini_failure_fallback(self, mock_s1, mock_s2, client):
        # Stage 1 fails → UNCLEAR fallback, stage 2 still produces text
        mock_s1.side_effect = LLMConnectionError("Connection failed")
        mock_s2.return_value = make_stage2_chunks("죄송합니다, 다시 시도해주세요.")

        resp = _chat(client, "리서치 하고 싶어")
        assert resp.status_code == 200
        data = resp.json()
        # Stage 1 fallback produces UNCLEAR → stage 2 is called with IDLE state
        assert data["reply"]


class TestChatEmptyMessage422:
    def test_chat_empty_message_422(self, client):
        resp = client.post("/api/v1/chat", json={"message": ""})
        assert resp.status_code == 422


class TestMessagesPersisted:
    @patch("ora_automation_api.dialog_engine._stream_gemini_stage2")
    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_messages_persisted_in_db(self, mock_s1, mock_s2, client):
        conv_id = "test-persist-conv"
        mock_s1.return_value = make_stage1_response(
            intent="general_chat", confidence=0.9, next_state="idle",
        )
        mock_s2.return_value = make_stage2_chunks("안녕하세요!")

        _chat(client, "안녕", conversation_id=conv_id)

        # Fetch conversation and check messages
        resp = client.get(f"/api/v1/conversations/{conv_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["messages"]) == 2  # user + assistant
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][0]["content"] == "안녕"
        assert data["messages"][1]["role"] == "assistant"
