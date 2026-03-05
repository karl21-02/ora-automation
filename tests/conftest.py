"""Shared fixtures for UPCE dialog engine tests."""
from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ora_automation_api.database import Base, get_db
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


# ── FastAPI TestClient ────────────────────────────────────────────────


@pytest.fixture()
def client():
    """TestClient backed by in-memory SQLite with UPCE enabled.

    Uses StaticPool + check_same_thread=False so the same in-memory DB
    is accessible from any thread (FastAPI test client runs in its own thread).
    """
    import ora_automation_api.database as db_module
    import ora_automation_api.main as main_module
    import ora_automation_api.chat_router as chat_module
    from fastapi.testclient import TestClient

    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(test_engine)
    TestSessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False,
    )

    def override_get_db():
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    # Save originals
    orig_db_engine = db_module.engine
    orig_db_session_local = db_module.SessionLocal
    orig_chat_session_local = chat_module.SessionLocal

    # Patch engine and SessionLocal at all module levels
    db_module.engine = test_engine
    db_module.SessionLocal = TestSessionLocal
    chat_module.SessionLocal = TestSessionLocal

    main_module.app.dependency_overrides[get_db] = override_get_db

    # Replace startup handlers to avoid real engine / migrations
    orig_on_startup = list(main_module.app.router.on_startup)
    main_module.app.router.on_startup = []

    with patch.dict(os.environ, {"ORA_CHAT_USE_UPCE": "1"}):
        with patch.object(chat_module, "_scan_projects", return_value=list(MOCK_PROJECTS)):
            with TestClient(main_module.app) as c:
                yield c

    # Restore
    main_module.app.dependency_overrides.clear()
    main_module.app.router.on_startup = orig_on_startup
    db_module.engine = orig_db_engine
    db_module.SessionLocal = orig_db_session_local
    chat_module.SessionLocal = orig_chat_session_local
    test_engine.dispose()


# ── Mock project list ────────────────────────────────────────────────


MOCK_PROJECTS: list[ProjectInfo] = [
    ProjectInfo(name="OraAiServer", path="/workspace/Ora/OraAiServer", has_makefile=True),
    ProjectInfo(name="OraFrontend", path="/workspace/Ora/OraFrontend", has_makefile=True),
    ProjectInfo(name="OraInfra", path="/workspace/Ora/OraInfra", has_dockerfile=True),
]


@pytest.fixture()
def projects() -> list[ProjectInfo]:
    return list(MOCK_PROJECTS)


# ── UPCE env mock ────────────────────────────────────────────────────


@pytest.fixture()
def mock_upce_env():
    """Enable UPCE mode and mock _scan_projects."""
    with patch.dict(os.environ, {"ORA_CHAT_USE_UPCE": "1"}):
        with patch("ora_automation_api.chat_router._scan_projects", return_value=list(MOCK_PROJECTS)):
            yield


# ── Stage 1 mock fixtures ────────────────────────────────────────────


@pytest.fixture()
def mock_gemini_stage1():
    """Patch _call_gemini_json to return a controllable response."""
    with patch("ora_automation_api.dialog_engine._call_gemini_json") as mock:
        yield mock


@pytest.fixture()
def mock_gemini_stage2():
    """Patch _stream_gemini_stage2 to return a controllable generator."""
    with patch("ora_automation_api.dialog_engine._stream_gemini_stage2") as mock:
        yield mock


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
