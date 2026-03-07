"""Tests for Phase 7: Gemini-based organization recommendation (ORG_RECOMMEND).

All Gemini calls are mocked — no network access needed.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ora_automation_api.database import Base
from ora_automation_api.dialog_engine import (
    DialogContext,
    DialogState,
    IntentClassification,
    IntentType,
    OrgRecommendationResult,
    recommend_org,
)
from ora_automation_api.models import (
    ChatConversation,
    Organization,
    OrganizationChapter,
    OrganizationSilo,
)
from ora_automation_api.chat_router import (
    _build_org_summaries_for_recommend,
    _maybe_recommend_org,
)
from ora_automation_api.schemas import OrgRecommendOption


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_org(db: Session, name: str, description: str = "") -> Organization:
    org = Organization(id=str(uuid.uuid4()), name=name, description=description)
    db.add(org)
    db.flush()
    return org


def _make_conv(db: Session, org_id: str | None = None) -> ChatConversation:
    conv = ChatConversation(id=str(uuid.uuid4()), title="test", org_id=org_id)
    db.add(conv)
    db.flush()
    return conv


def _research_classification(confidence: float = 0.9) -> IntentClassification:
    return IntentClassification(
        intent=IntentType.RESEARCH,
        confidence=confidence,
        next_state=DialogState.UNDERSTANDING,
    )


def _general_classification() -> IntentClassification:
    return IntentClassification(
        intent=IntentType.GENERAL_CHAT,
        confidence=0.9,
        next_state=DialogState.IDLE,
    )


# =====================================================================
# 1. recommend_org() function tests
# =====================================================================


class TestRecommendOrgFunction:
    def test_empty_orgs_returns_empty(self):
        result = recommend_org("보안 분석 해줘", "research", [])
        assert result.recommended_org_id is None
        assert result.rankings == []

    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_returns_recommendation(self, mock_gemini):
        mock_gemini.return_value = {
            "recommended_org_id": "org-1",
            "reason": "보안 관련 분석에 가장 적합합니다.",
            "rankings": [
                {"org_id": "org-1", "org_name": "Security Team", "score": 0.9, "reason": "보안 전문"},
                {"org_id": "org-2", "org_name": "Dev Team", "score": 0.3, "reason": "개발 중심"},
            ],
        }

        result = recommend_org(
            "보안 취약점 분석해줘",
            "research (confidence: 0.90)",
            [
                {"org_id": "org-1", "org_name": "Security Team"},
                {"org_id": "org-2", "org_name": "Dev Team"},
            ],
        )
        assert result.recommended_org_id == "org-1"
        assert len(result.rankings) == 2
        assert result.reason == "보안 관련 분석에 가장 적합합니다."

    @patch("ora_automation_api.dialog_engine._call_gemini_json")
    def test_gemini_failure_returns_empty(self, mock_gemini):
        mock_gemini.side_effect = RuntimeError("Gemini down")

        result = recommend_org(
            "분석해줘",
            "research",
            [{"org_id": "org-1", "org_name": "Team A"}],
        )
        assert result.recommended_org_id is None
        assert result.rankings == []


# =====================================================================
# 2. _build_org_summaries_for_recommend() tests
# =====================================================================


class TestBuildOrgSummaries:
    def test_no_orgs_returns_empty(self, db):
        summaries = _build_org_summaries_for_recommend(db)
        assert summaries == []

    def test_returns_org_info(self, db):
        org = _make_org(db, "My Team", description="R&D 팀")
        db.commit()

        summaries = _build_org_summaries_for_recommend(db)
        assert len(summaries) == 1
        assert summaries[0]["org_id"] == org.id
        assert summaries[0]["org_name"] == "My Team"
        assert summaries[0]["description"] == "R&D 팀"

    def test_includes_chapters_and_silos(self, db):
        org = _make_org(db, "Full Org")
        ch = OrganizationChapter(
            id=str(uuid.uuid4()),
            org_id=org.id,
            name="Security Chapter",
            description="보안 챕터",
        )
        silo = OrganizationSilo(
            id=str(uuid.uuid4()),
            org_id=org.id,
            name="Platform Silo",
            description="플랫폼",
        )
        db.add_all([ch, silo])
        db.commit()

        summaries = _build_org_summaries_for_recommend(db)
        assert len(summaries) == 1
        assert "chapters" in summaries[0]
        assert summaries[0]["chapters"][0]["name"] == "Security Chapter"
        assert "silos" in summaries[0]
        assert summaries[0]["silos"][0]["name"] == "Platform Silo"


# =====================================================================
# 3. _maybe_recommend_org() tests
# =====================================================================


class TestMaybeRecommendOrg:
    def test_skip_when_org_id_exists(self, db):
        org = _make_org(db, "Existing")
        conv = _make_conv(db, org_id=org.id)
        db.commit()

        result = _maybe_recommend_org(
            db, conv, "분석해줘",
            _research_classification(),
            DialogContext(),
        )
        assert result is None

    def test_skip_when_zero_orgs(self, db):
        conv = _make_conv(db)
        db.commit()

        result = _maybe_recommend_org(
            db, conv, "분석해줘",
            _research_classification(),
            DialogContext(),
        )
        assert result is None

    def test_auto_apply_when_one_org(self, db):
        org = _make_org(db, "Only Org")
        conv = _make_conv(db)
        db.commit()

        result = _maybe_recommend_org(
            db, conv, "분석해줘",
            _research_classification(),
            DialogContext(),
        )
        assert result is None
        assert conv.org_id == org.id

    def test_skip_for_general_chat(self, db):
        _make_org(db, "Org A")
        _make_org(db, "Org B")
        conv = _make_conv(db)
        db.commit()

        result = _maybe_recommend_org(
            db, conv, "안녕하세요",
            _general_classification(),
            DialogContext(),
        )
        assert result is None

    @patch("ora_automation_api.chat_router.recommend_org")
    def test_recommend_for_research(self, mock_recommend, db):
        org_a = _make_org(db, "Org A", "보안팀")
        org_b = _make_org(db, "Org B", "개발팀")
        conv = _make_conv(db)
        db.commit()

        mock_recommend.return_value = OrgRecommendationResult(
            recommended_org_id=org_a.id,
            reason="보안 분석에 적합",
            rankings=[
                {"org_id": org_a.id, "org_name": "Org A", "score": 0.9, "reason": "보안 전문"},
                {"org_id": org_b.id, "org_name": "Org B", "score": 0.3, "reason": "개발 중심"},
            ],
        )

        result = _maybe_recommend_org(
            db, conv, "보안 취약점 분석해줘",
            _research_classification(),
            DialogContext(),
        )
        assert result is not None
        assert len(result) == 2
        recommended = [o for o in result if o.is_recommended]
        assert len(recommended) == 1
        assert recommended[0].org_id == org_a.id

    def test_skip_when_already_recommended(self, db):
        _make_org(db, "Org A")
        _make_org(db, "Org B")
        conv = _make_conv(db)
        db.commit()

        ctx = DialogContext(accumulated_slots={"org_recommend_done": True})

        result = _maybe_recommend_org(
            db, conv, "분석해줘",
            _research_classification(),
            ctx,
        )
        assert result is None


# =====================================================================
# 4. Org selection message detection tests
# =====================================================================


class TestOrgSelectionMessage:
    def test_detect_prefix(self):
        msg = "ora:org_select:abc-123"
        assert msg.startswith("ora:org_select:")

    def test_extract_org_id(self):
        msg = "ora:org_select:abc-123"
        org_id = msg[len("ora:org_select:"):].strip()
        assert org_id == "abc-123"

    def test_empty_means_unclassified(self):
        msg = "ora:org_select:"
        org_id = msg[len("ora:org_select:"):].strip()
        assert org_id == ""
        assert not org_id  # falsy
