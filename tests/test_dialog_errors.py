"""Error scenario tests for UPCE dialog engine.

Tests JSON parse errors, timeouts, streaming exceptions,
invalid plans, slot merging edge cases, and optimistic lock conflicts.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ora_automation_api.database import Base
from ora_automation_api.dialog_engine import (
    DialogContext,
    DialogState,
    IntentClassification,
    IntentType,
    ResearchSlots,
    coerce_proposed_plans,
    merge_slots,
    run_stage1,
    run_stage2_stream,
)
from ora_automation_api.chat_router import (
    StaleDialogError,
    _get_dialog_context,
    _save_dialog_context,
)
from ora_automation_api.models import ChatConversation
from ora_automation_api.schemas import ProjectInfo

from conftest import MOCK_PROJECTS, make_stage1_response


# ── Stage 1 error scenarios ──────────────────────────────────────────


class TestStage1JSONParseError:
    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_stage1_json_parse_error(self, mock_gemini):
        """Invalid JSON from Gemini → UNCLEAR fallback."""
        mock_gemini.side_effect = RuntimeError("Gemini JSON parse error: Expecting value")

        ctx = DialogContext()
        result = run_stage1("테스트", [], ctx, MOCK_PROJECTS)

        assert result.intent == IntentType.UNCLEAR
        assert result.confidence == 0.0
        assert result.needs_clarification is True


class TestStage1Timeout:
    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_stage1_timeout(self, mock_gemini):
        """Timeout from Gemini → UNCLEAR fallback."""
        mock_gemini.side_effect = TimeoutError("Request timed out")

        ctx = DialogContext()
        result = run_stage1("리서치", [], ctx, MOCK_PROJECTS)

        assert result.intent == IntentType.UNCLEAR
        assert result.confidence == 0.0
        assert result.next_state == DialogState.IDLE


# ── Stage 2 streaming error ──────────────────────────────────────────


class TestStage2StreamException:
    @patch("ora_automation_api.dialog_engine._stream_gemini_stage2")
    def test_stage2_stream_exception(self, mock_stream):
        """Streaming exception → empty string collected."""
        def failing_gen():
            yield "첫 번째 "
            raise RuntimeError("Stream interrupted")

        mock_stream.return_value = failing_gen()

        ctx = DialogContext()
        classification = IntentClassification(
            intent=IntentType.GENERAL_CHAT,
            next_state=DialogState.IDLE,
        )

        # run_stage2_stream yields chunks; collect manually
        chunks = []
        try:
            for chunk in run_stage2_stream(
                classification, [], "test", ctx, MOCK_PROJECTS,
            ):
                chunks.append(chunk)
        except RuntimeError:
            pass

        result = "".join(chunks)
        assert result == "첫 번째 "


# ── Plan coercion edge cases ────────────────────────────────────────


class TestCoercePlansAllInvalid:
    def test_coerce_plans_all_invalid(self):
        """All plans have invalid targets → (None, None)."""
        raw = [
            {"target": "rm-rf", "env": {}, "label": "bad1"},
            {"target": "DROP-TABLE", "env": {}, "label": "bad2"},
        ]
        plan, plans = coerce_proposed_plans(raw)
        assert plan is None
        assert plans is None


# ── Slot merge edge cases ────────────────────────────────────────────


class TestMergeSlotsNoneFields:
    def test_merge_slots_none_fields(self):
        """None fields in slots → existing slots preserved."""
        ctx = DialogContext(
            state=DialogState.SLOT_FILLING,
            intent=IntentType.RESEARCH,
            accumulated_slots={"topic": "보안", "projects": ["A"]},
        )
        # Classification with None topic and None projects
        classification = IntentClassification(
            intent=IntentType.RESEARCH,
            next_state=DialogState.SLOT_FILLING,
            research_slots=ResearchSlots(topic=None, projects=None, depth="deep"),
        )
        updated = merge_slots(ctx, classification)

        # Existing topic and projects should be preserved
        assert updated.accumulated_slots["topic"] == "보안"
        assert updated.accumulated_slots["projects"] == ["A"]
        # New depth should be added
        assert updated.accumulated_slots["depth"] == "deep"


# ── Optimistic lock (StaleDialogError) ───────────────────────────────


class TestStaleDialogVersion:
    def test_stale_dialog_version(self):
        """Optimistic lock conflict → StaleDialogError."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        db = Session()

        try:
            # Create a conversation
            conv = ChatConversation(id="test-stale", title="test")
            db.add(conv)
            db.commit()
            db.refresh(conv)

            # First save succeeds (version 0 → 1)
            ctx = DialogContext(state=DialogState.UNDERSTANDING)
            _save_dialog_context(db, conv, ctx, expected_version=0)
            db.commit()

            # Second save with stale version (still 0) → should fail
            ctx2 = DialogContext(state=DialogState.SLOT_FILLING)
            with pytest.raises(StaleDialogError):
                _save_dialog_context(db, conv, ctx2, expected_version=0)
        finally:
            db.close()
            engine.dispose()

    def test_version_increments(self):
        """Version increments correctly on each save."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        db = Session()

        try:
            conv = ChatConversation(id="test-ver", title="test")
            db.add(conv)
            db.commit()
            db.refresh(conv)

            # Version starts at 0
            _, ver = _get_dialog_context(conv)
            assert ver == 0

            # Save increments to 1
            _save_dialog_context(db, conv, DialogContext(), expected_version=0)
            db.commit()

            # Re-read to check version
            db.refresh(conv)
            _, ver2 = _get_dialog_context(conv)
            assert ver2 == 1

            # Save with correct version 1 → succeeds
            _save_dialog_context(db, conv, DialogContext(state=DialogState.CONFIRMING), expected_version=1)
            db.commit()

            db.refresh(conv)
            _, ver3 = _get_dialog_context(conv)
            assert ver3 == 2
        finally:
            db.close()
            engine.dispose()


# ── _get_dialog_context corrupted data ─────────────────────────────


class TestGetDialogContextCorruptedData:
    """_get_dialog_context logs a warning and resets to IDLE on bad data."""

    def test_corrupted_dict_returns_idle(self):
        """Unparseable dialog_context dict → fallback to fresh DialogContext."""
        conv = ChatConversation(id="corrupt-1", title="test")
        conv.dialog_context = {"state": "NONEXISTENT_STATE", "intent": 12345}
        conv.dialog_context_version = 3

        ctx, ver = _get_dialog_context(conv)

        assert ver == 3
        assert ctx.state == DialogState.IDLE
        assert ctx.intent is None

    def test_corrupted_dict_logs_warning(self, caplog):
        """Corrupted dialog_context → warning log emitted."""
        import logging

        conv = ChatConversation(id="corrupt-2", title="test")
        conv.dialog_context = {"state": "INVALID"}
        conv.dialog_context_version = 1

        with caplog.at_level(logging.WARNING, logger="ora_automation_api.chat_router"):
            _get_dialog_context(conv)

        assert any("Failed to parse dialog_context" in msg for msg in caplog.messages)

    def test_none_context_returns_fresh(self):
        """None dialog_context → fresh DialogContext with version 0."""
        conv = ChatConversation(id="none-ctx", title="test")
        conv.dialog_context = None
        conv.dialog_context_version = None

        ctx, ver = _get_dialog_context(conv)

        assert ver == 0
        assert ctx.state == DialogState.IDLE

    def test_non_dict_context_returns_fresh(self):
        """Non-dict dialog_context (e.g. a string) → fresh DialogContext."""
        conv = ChatConversation(id="str-ctx", title="test")
        conv.dialog_context = "not a dict"
        conv.dialog_context_version = 2

        ctx, ver = _get_dialog_context(conv)

        assert ver == 2
        assert ctx.state == DialogState.IDLE
