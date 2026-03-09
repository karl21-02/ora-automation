"""UPCE 2-Stage Dialog Engine — unit tests & E2E multi-turn scenarios.

All Gemini calls are mocked so these tests run without network access.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from ora_automation_api.dialog_engine import (
    DialogContext,
    DialogState,
    IntentClassification,
    IntentType,
    MissingSlot,
    ResearchSlots,
    TestingSlots,
    build_proposed_plans,
    coerce_proposed_plans,
    merge_slots,
    run_stage1,
    run_stage2_sync,
)
from ora_automation_api.exceptions import LLMConnectionError
from ora_automation_api.schemas import ChatPlan, ProjectInfo

from conftest import MOCK_PROJECTS, make_stage1_response, make_stage2_chunks


# =====================================================================
# 1. Pure logic tests (no mocking needed)
# =====================================================================


class TestMergeSlots:
    """merge_slots: accumulate slots across turns."""

    def test_merge_research_slots(self):
        ctx = DialogContext(state=DialogState.UNDERSTANDING, intent=IntentType.RESEARCH)
        classification = IntentClassification(
            intent=IntentType.RESEARCH,
            next_state=DialogState.SLOT_FILLING,
            research_slots=ResearchSlots(topic="인증 시스템 보안 강화"),
        )
        updated = merge_slots(ctx, classification)

        assert updated.state == DialogState.SLOT_FILLING
        assert updated.accumulated_slots["topic"] == "인증 시스템 보안 강화"
        assert updated.turn_count == 1

    def test_merge_preserves_existing_slots(self):
        ctx = DialogContext(
            state=DialogState.SLOT_FILLING,
            intent=IntentType.RESEARCH,
            accumulated_slots={"topic": "보안 강화"},
            turn_count=1,
        )
        classification = IntentClassification(
            intent=IntentType.RESEARCH,
            next_state=DialogState.CONFIRMING,
            research_slots=ResearchSlots(projects=["OraAiServer"]),
        )
        updated = merge_slots(ctx, classification)

        assert updated.accumulated_slots["topic"] == "보안 강화"
        assert updated.accumulated_slots["projects"] == ["OraAiServer"]
        assert updated.turn_count == 2

    def test_merge_testing_slots(self):
        ctx = DialogContext(state=DialogState.UNDERSTANDING, intent=IntentType.TESTING)
        classification = IntentClassification(
            intent=IntentType.TESTING,
            next_state=DialogState.SLOT_FILLING,
            testing_slots=TestingSlots(service="ai", scope="single"),
        )
        updated = merge_slots(ctx, classification)

        assert updated.accumulated_slots["service"] == "ai"
        assert updated.accumulated_slots["scope"] == "single"

    def test_rejection_resets_slots(self):
        ctx = DialogContext(
            state=DialogState.CONFIRMING,
            intent=IntentType.RESEARCH,
            accumulated_slots={"topic": "보안", "projects": ["A"]},
            turn_count=3,
        )
        classification = IntentClassification(
            intent=IntentType.REJECT,
            next_state=DialogState.IDLE,
            is_rejection=True,
        )
        updated = merge_slots(ctx, classification)

        assert updated.accumulated_slots == {}
        assert updated.state == DialogState.IDLE

    def test_unclear_preserves_previous_intent(self):
        ctx = DialogContext(
            state=DialogState.SLOT_FILLING,
            intent=IntentType.RESEARCH,
            accumulated_slots={"topic": "보안"},
        )
        classification = IntentClassification(
            intent=IntentType.UNCLEAR,
            next_state=DialogState.SLOT_FILLING,
        )
        updated = merge_slots(ctx, classification)

        assert updated.intent == IntentType.RESEARCH


class TestCoerceProposedPlans:
    """coerce_proposed_plans: validate and convert raw plan dicts."""

    def test_single_valid_plan(self):
        raw = [{"target": "run-cycle", "env": {"FOCUS": "보안"}, "label": "OraAiServer"}]
        plan, plans = coerce_proposed_plans(raw)

        assert plan is not None
        assert plans is None
        assert plan.target == "run-cycle"
        assert plan.env["FOCUS"] == "보안"
        assert plan.label == "OraAiServer"

    def test_multiple_valid_plans(self):
        raw = [
            {"target": "run-cycle", "env": {"FOCUS": "보안"}, "label": "OraAiServer"},
            {"target": "run-cycle", "env": {"FOCUS": "보안"}, "label": "OraFrontend"},
        ]
        plan, plans = coerce_proposed_plans(raw)

        assert plan is None
        assert plans is not None
        assert len(plans) == 2
        assert plans[0].label == "OraAiServer"
        assert plans[1].label == "OraFrontend"

    def test_invalid_target_filtered(self):
        raw = [{"target": "rm-rf-everything", "env": {}, "label": "bad"}]
        plan, plans = coerce_proposed_plans(raw)

        assert plan is None
        assert plans is None

    def test_none_input(self):
        plan, plans = coerce_proposed_plans(None)
        assert plan is None
        assert plans is None

    def test_empty_list(self):
        plan, plans = coerce_proposed_plans([])
        assert plan is None
        assert plans is None

    def test_mixed_valid_invalid(self):
        raw = [
            {"target": "run-cycle", "env": {"FOCUS": "X"}, "label": "A"},
            {"target": "INVALID", "env": {}, "label": "B"},
        ]
        plan, plans = coerce_proposed_plans(raw)

        # Only one valid → single plan
        assert plan is not None
        assert plans is None
        assert plan.label == "A"


class TestBuildProposedPlans:
    """build_proposed_plans: construct plan dicts from slots."""

    def test_research_single_project(self):
        slots = {"topic": "인증 보안", "projects": ["OraAiServer"], "target": "run-cycle"}
        plans = build_proposed_plans(slots, IntentType.RESEARCH)

        assert len(plans) == 1
        assert plans[0]["target"] == "run-cycle"
        assert plans[0]["env"]["FOCUS"] == "인증 보안"
        assert plans[0]["label"] == "OraAiServer"

    def test_research_multi_project(self):
        slots = {"topic": "성능 최적화", "projects": ["OraAiServer", "OraFrontend"]}
        plans = build_proposed_plans(slots, IntentType.RESEARCH)

        assert len(plans) == 2
        assert plans[0]["label"] == "OraAiServer"
        assert plans[1]["label"] == "OraFrontend"
        # Default target
        assert plans[0]["target"] == "run-cycle"

    def test_research_deep_profile(self):
        slots = {"topic": "아키텍처", "depth": "deep"}
        plans = build_proposed_plans(slots, IntentType.RESEARCH)

        assert len(plans) == 1
        assert plans[0]["env"]["ORCHESTRATION_PROFILE"] == "strict"

    def test_research_no_projects(self):
        slots = {"topic": "API 개선"}
        plans = build_proposed_plans(slots, IntentType.RESEARCH)

        assert len(plans) == 1
        assert plans[0]["label"] == ""

    def test_testing_single_service(self):
        slots = {"service": "ai", "scope": "single"}
        plans = build_proposed_plans(slots, IntentType.TESTING)

        assert len(plans) == 1
        assert plans[0]["target"] == "e2e-service"
        assert plans[0]["env"]["SERVICE"] == "ai"

    def test_testing_all_scope(self):
        slots = {"scope": "all"}
        plans = build_proposed_plans(slots, IntentType.TESTING)

        assert len(plans) == 1
        assert plans[0]["target"] == "e2e-service-all"

    def test_general_chat_returns_empty(self):
        plans = build_proposed_plans({}, IntentType.GENERAL_CHAT)
        assert plans == []


# =====================================================================
# 2. Stage 1 tests (mock _call_gemini_json)
# =====================================================================


class TestRunStage1:
    """run_stage1: mock Gemini JSON-mode calls."""

    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_research_intent(self, mock_gemini):
        mock_gemini.return_value = make_stage1_response(
            intent="research",
            confidence=0.92,
            next_state="understanding",
            research_slots={"topic": "인증 시스템 보안 강화"},
            missing_slots=[{"name": "projects", "description": "대상 프로젝트"}],
            needs_clarification=True,
            response_guidance="사용자에게 프로젝트를 물어보세요.",
        )

        ctx = DialogContext()
        result = run_stage1("리서치 하고 싶어", [], ctx, MOCK_PROJECTS)

        assert result.intent == IntentType.RESEARCH
        assert result.confidence == pytest.approx(0.92)
        assert result.next_state == DialogState.UNDERSTANDING
        assert result.research_slots is not None
        assert result.research_slots.topic == "인증 시스템 보안 강화"

    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_confirmation_detection(self, mock_gemini):
        mock_gemini.return_value = make_stage1_response(
            intent="confirm",
            confidence=0.95,
            current_state="confirming",
            next_state="executing",
            is_confirmation=True,
        )

        ctx = DialogContext(state=DialogState.CONFIRMING, intent=IntentType.RESEARCH)
        result = run_stage1("네", [], ctx, MOCK_PROJECTS)

        assert result.is_confirmation is True
        assert result.next_state == DialogState.EXECUTING

    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_rejection_detection(self, mock_gemini):
        mock_gemini.return_value = make_stage1_response(
            intent="reject",
            confidence=0.90,
            current_state="confirming",
            next_state="idle",
            is_rejection=True,
        )

        ctx = DialogContext(state=DialogState.CONFIRMING)
        result = run_stage1("취소", [], ctx, MOCK_PROJECTS)

        assert result.is_rejection is True
        assert result.next_state == DialogState.IDLE

    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_gemini_failure_fallback(self, mock_gemini):
        mock_gemini.side_effect = LLMConnectionError("GOOGLE_CLOUD_PROJECT_ID not set")

        ctx = DialogContext()
        result = run_stage1("아무 말이나", [], ctx, MOCK_PROJECTS)

        assert result.intent == IntentType.UNCLEAR
        assert result.confidence == 0.0
        assert result.needs_clarification is True

    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_project_select_needed(self, mock_gemini):
        mock_gemini.return_value = make_stage1_response(
            intent="research",
            confidence=0.85,
            next_state="slot_filling",
            research_slots={"topic": "인증 보안"},
            needs_project_select=True,
            missing_slots=[{"name": "projects", "description": "대상 프로젝트 선택 필요"}],
            response_guidance="프로젝트 선택 UI를 보여주세요.",
        )

        ctx = DialogContext(state=DialogState.UNDERSTANDING)
        result = run_stage1("인증 시스템 보안 강화", [], ctx, MOCK_PROJECTS)

        assert result.needs_project_select is True
        assert result.next_state == DialogState.SLOT_FILLING


# =====================================================================
# 3. E2E multi-turn scenario (Stage 1 + Stage 2 mocked)
# =====================================================================


class TestE2EMultiTurnResearch:
    """Full 4-turn research flow: IDLE → UNDERSTANDING → SLOT_FILLING → CONFIRMING → EXECUTING."""

    @patch("ora_automation_api.dialog_engine._stream_gemini_stage2")
    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_full_research_flow(self, mock_s1, mock_s2, projects):
        history: list[dict] = []
        ctx = DialogContext()

        # ── Turn 1: "리서치 하고 싶어" → UNDERSTANDING ──
        mock_s1.return_value = make_stage1_response(
            intent="research",
            confidence=0.88,
            next_state="understanding",
            research_slots={"topic": None},
            missing_slots=[{"name": "topic", "description": "연구 주제"}],
            needs_clarification=True,
            response_guidance="어떤 주제를 연구하고 싶은지 물어보세요.",
        )
        mock_s2.return_value = make_stage2_chunks("어떤 주제에 대해 ", "리서치하고 싶으세요?")

        c1 = run_stage1("리서치 하고 싶어", history, ctx, projects)
        ctx = merge_slots(ctx, c1)
        reply1 = run_stage2_sync(c1, history, "리서치 하고 싶어", ctx, projects)

        assert c1.next_state == DialogState.UNDERSTANDING
        assert ctx.state == DialogState.UNDERSTANDING
        assert "리서치" in reply1
        history.append({"role": "user", "content": "리서치 하고 싶어"})
        history.append({"role": "assistant", "content": reply1})

        # ── Turn 2: "인증 시스템 보안 강화" → SLOT_FILLING ──
        mock_s1.return_value = make_stage1_response(
            intent="research",
            confidence=0.92,
            current_state="understanding",
            next_state="slot_filling",
            research_slots={"topic": "인증 시스템 보안 강화"},
            needs_project_select=True,
            missing_slots=[{"name": "projects", "description": "대상 프로젝트"}],
            response_guidance="프로젝트를 선택하도록 안내하세요.",
        )
        mock_s2.return_value = make_stage2_chunks("어떤 프로젝트를 ", "대상으로 할까요?")

        c2 = run_stage1("인증 시스템 보안 강화", history, ctx, projects)
        ctx = merge_slots(ctx, c2)
        reply2 = run_stage2_sync(c2, history, "인증 시스템 보안 강화", ctx, projects)

        assert c2.next_state == DialogState.SLOT_FILLING
        assert ctx.accumulated_slots["topic"] == "인증 시스템 보안 강화"
        assert c2.needs_project_select is True
        assert "프로젝트" in reply2
        history.append({"role": "user", "content": "인증 시스템 보안 강화"})
        history.append({"role": "assistant", "content": reply2})

        # ── Turn 3: project selection → CONFIRMING ──
        mock_s1.return_value = make_stage1_response(
            intent="research",
            confidence=0.95,
            current_state="slot_filling",
            next_state="confirming",
            research_slots={"projects": ["OraAiServer"]},
            proposed_plans=[
                {"target": "run-cycle", "env": {"FOCUS": "인증 시스템 보안 강화"}, "label": "OraAiServer"},
            ],
            response_guidance="실행 계획을 보여주고 확인을 요청하세요.",
        )
        mock_s2.return_value = make_stage2_chunks(
            "다음 계획으로 실행할까요?\n",
            "- run-cycle (FOCUS: 인증 시스템 보안 강화)\n",
            "실행할까요?",
        )

        c3 = run_stage1("다음 프로젝트 선택: OraAiServer", history, ctx, projects)
        ctx = merge_slots(ctx, c3)
        reply3 = run_stage2_sync(c3, history, "다음 프로젝트 선택: OraAiServer", ctx, projects)

        assert c3.next_state == DialogState.CONFIRMING
        assert ctx.accumulated_slots["projects"] == ["OraAiServer"]
        assert ctx.proposed_plans is not None
        assert len(ctx.proposed_plans) == 1
        assert "실행" in reply3
        history.append({"role": "user", "content": "다음 프로젝트 선택: OraAiServer"})
        history.append({"role": "assistant", "content": reply3})

        # ── Turn 4: "네" → EXECUTING ──
        mock_s1.return_value = make_stage1_response(
            intent="confirm",
            confidence=0.98,
            current_state="confirming",
            next_state="executing",
            is_confirmation=True,
            response_guidance="실행을 시작한다고 알려주세요.",
        )

        c4 = run_stage1("네", history, ctx, projects)
        ctx = merge_slots(ctx, c4)

        assert c4.is_confirmation is True
        assert ctx.state == DialogState.EXECUTING
        assert ctx.proposed_plans is not None

        # Validate the final plans can be coerced
        plan, plans = coerce_proposed_plans(ctx.proposed_plans)
        assert plan is not None
        assert plan.target == "run-cycle"
        assert plan.env["FOCUS"] == "인증 시스템 보안 강화"


class TestE2ERejection:
    """Rejection scenario: user starts a task then cancels."""

    @patch("ora_automation_api.dialog_engine._stream_gemini_stage2")
    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_rejection_resets_to_idle(self, mock_s1, mock_s2, projects):
        ctx = DialogContext()
        history: list[dict] = []

        # ── Turn 1: "테스트 해줘" → UNDERSTANDING ──
        mock_s1.return_value = make_stage1_response(
            intent="testing",
            confidence=0.85,
            next_state="understanding",
            testing_slots={"service": None},
            missing_slots=[{"name": "service", "description": "테스트 대상 서비스"}],
            response_guidance="어떤 서비스를 테스트할지 물어보세요.",
        )
        mock_s2.return_value = make_stage2_chunks("어떤 서비스를 테스트할까요?")

        c1 = run_stage1("테스트 해줘", history, ctx, projects)
        ctx = merge_slots(ctx, c1)
        reply1 = run_stage2_sync(c1, history, "테스트 해줘", ctx, projects)

        assert ctx.state == DialogState.UNDERSTANDING
        assert ctx.intent == IntentType.TESTING
        history.append({"role": "user", "content": "테스트 해줘"})
        history.append({"role": "assistant", "content": reply1})

        # ── Turn 2: "취소" → IDLE (reset) ──
        mock_s1.return_value = make_stage1_response(
            intent="reject",
            confidence=0.90,
            current_state="understanding",
            next_state="idle",
            is_rejection=True,
            response_guidance="취소되었음을 알려주세요.",
        )

        c2 = run_stage1("취소", history, ctx, projects)
        ctx = merge_slots(ctx, c2)

        assert c2.is_rejection is True
        assert ctx.state == DialogState.IDLE
        assert ctx.accumulated_slots == {}


class TestE2EMultiProjectResearch:
    """Multi-project research flow with 2 projects."""

    @patch("ora_automation_api.dialog_engine._stream_gemini_stage2")
    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_multi_project_plans(self, mock_s1, mock_s2, projects):
        ctx = DialogContext(
            state=DialogState.SLOT_FILLING,
            intent=IntentType.RESEARCH,
            accumulated_slots={"topic": "성능 최적화"},
            turn_count=2,
        )
        history = [
            {"role": "user", "content": "성능 최적화 리서치"},
            {"role": "assistant", "content": "어떤 프로젝트를 대상으로 할까요?"},
        ]

        mock_s1.return_value = make_stage1_response(
            intent="research",
            confidence=0.95,
            current_state="slot_filling",
            next_state="confirming",
            research_slots={"projects": ["OraAiServer", "OraFrontend"]},
            proposed_plans=[
                {"target": "run-cycle", "env": {"FOCUS": "성능 최적화"}, "label": "OraAiServer"},
                {"target": "run-cycle", "env": {"FOCUS": "성능 최적화"}, "label": "OraFrontend"},
            ],
        )
        mock_s2.return_value = make_stage2_chunks("2개 프로젝트에 대해 실행할까요?")

        c = run_stage1("OraAiServer, OraFrontend 선택", history, ctx, projects)
        ctx = merge_slots(ctx, c)

        assert ctx.state == DialogState.CONFIRMING
        assert ctx.accumulated_slots["projects"] == ["OraAiServer", "OraFrontend"]
        assert ctx.proposed_plans is not None
        assert len(ctx.proposed_plans) == 2

        plan, plans = coerce_proposed_plans(ctx.proposed_plans)
        assert plan is None  # multi → no single plan
        assert plans is not None
        assert len(plans) == 2
        assert plans[0].label == "OraAiServer"
        assert plans[1].label == "OraFrontend"


class TestStage2Sync:
    """run_stage2_sync: collects streaming chunks into a single string."""

    @patch("ora_automation_api.dialog_engine._stream_gemini_stage2")
    def test_collects_chunks(self, mock_stream, projects):
        mock_stream.return_value = make_stage2_chunks("안녕하세요! ", "무엇을 ", "도와드릴까요?")

        ctx = DialogContext()
        classification = IntentClassification(
            intent=IntentType.GENERAL_CHAT,
            next_state=DialogState.IDLE,
        )
        result = run_stage2_sync(classification, [], "안녕", ctx, projects)

        assert result == "안녕하세요! 무엇을 도와드릴까요?"

    @patch("ora_automation_api.dialog_engine._stream_gemini_stage2")
    def test_empty_stream(self, mock_stream, projects):
        mock_stream.return_value = make_stage2_chunks()

        ctx = DialogContext()
        classification = IntentClassification()
        result = run_stage2_sync(classification, [], "test", ctx, projects)

        assert result == ""
