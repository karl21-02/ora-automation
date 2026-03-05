"""Shared fixtures for UPCE dialog engine tests."""
from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ora_automation_api.database import Base
from ora_automation_api.dialog_engine import (
    DialogContext,
    DialogState,
    IntentClassification,
    IntentType,
    MissingSlot,
    ResearchSlots,
    TestingSlots,
)
from ora_automation_api.schemas import ProjectInfo


# ── In-memory SQLite DB ──────────────────────────────────────────────


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    """Create an in-memory SQLite database with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


# ── Mock project list ────────────────────────────────────────────────


MOCK_PROJECTS: list[ProjectInfo] = [
    ProjectInfo(name="OraAiServer", path="/workspace/Ora/OraAiServer", has_makefile=True),
    ProjectInfo(name="OraFrontend", path="/workspace/Ora/OraFrontend", has_makefile=True),
    ProjectInfo(name="OraInfra", path="/workspace/Ora/OraInfra", has_dockerfile=True),
]


@pytest.fixture()
def projects() -> list[ProjectInfo]:
    return list(MOCK_PROJECTS)


# ── Stage 1 mock helper ─────────────────────────────────────────────


def make_stage1_response(
    *,
    intent: str = "unclear",
    confidence: float = 0.8,
    current_state: str = "idle",
    next_state: str = "idle",
    research_slots: dict | None = None,
    testing_slots: dict | None = None,
    needs_clarification: bool = False,
    missing_slots: list[dict] | None = None,
    proposed_plans: list[dict] | None = None,
    needs_project_select: bool = False,
    is_confirmation: bool = False,
    is_rejection: bool = False,
    response_guidance: str = "",
) -> dict:
    """Build a dict matching the IntentClassification JSON schema."""
    return {
        "intent": intent,
        "confidence": confidence,
        "current_state": current_state,
        "next_state": next_state,
        "research_slots": research_slots,
        "testing_slots": testing_slots,
        "needs_clarification": needs_clarification,
        "missing_slots": missing_slots,
        "proposed_plans": proposed_plans,
        "needs_project_select": needs_project_select,
        "is_confirmation": is_confirmation,
        "is_rejection": is_rejection,
        "response_guidance": response_guidance,
    }


# ── Stage 2 mock helper ─────────────────────────────────────────────


def make_stage2_chunks(*texts: str) -> Generator[str, None, None]:
    """Return a generator yielding text chunks (simulates streaming)."""
    for t in texts:
        yield t
