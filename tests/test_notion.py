"""Tests for Notion integration (all API calls mocked)."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ora_automation_api.database import Base, get_db
from ora_automation_api.models import NotionSyncState
from ora_automation_api.notion_client import NotionAPIError, NotionClient
from ora_automation_api.notion_publisher import (
    MAX_BLOCKS_PER_APPEND,
    MAX_TEXT_LEN,
    NotionPublisher,
    _split_into_batches,
    _split_rich_text,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def mock_session():
    """requests.Session mock for NotionClient."""
    with patch("ora_automation_api.notion_client.requests.Session") as MockSession:
        session_instance = MagicMock()
        MockSession.return_value = session_instance
        yield session_instance


@pytest.fixture()
def notion_client(mock_session):
    return NotionClient(token="ntn_test_token", api_version="2022-06-28")


@pytest.fixture()
def notion_db():
    """In-memory SQLite with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client():
    """FastAPI TestClient backed by in-memory SQLite."""
    import ora_automation_api.database as db_module
    import ora_automation_api.main as main_module
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

    orig_db_engine = db_module.engine
    orig_db_session_local = db_module.SessionLocal
    db_module.engine = test_engine
    db_module.SessionLocal = TestSessionLocal
    main_module.app.dependency_overrides[get_db] = override_get_db
    orig_on_startup = list(main_module.app.router.on_startup)
    main_module.app.router.on_startup = []

    with TestClient(main_module.app) as c:
        yield c

    main_module.app.dependency_overrides.clear()
    main_module.app.router.on_startup = orig_on_startup
    db_module.engine = orig_db_engine
    db_module.SessionLocal = orig_db_session_local
    test_engine.dispose()


SAMPLE_REPORT = {
    "report_version": "v1.0",
    "report_focus": "AI Strategy",
    "generated_at": "2025-01-15T10:00:00",
    "ranked": [
        {
            "topic_id": "t1",
            "topic_name": "RAG Pipeline",
            "total_score": 8.5,
            "features": {"impact": 7.0, "feasibility": 8.0, "novelty": 6.5, "risk_penalty": 2.0, "research_signal": 5.0},
            "project_count": 3,
            "evidence_count": 12,
            "evidence": ["snippet1"],
        },
        {
            "topic_id": "t2",
            "topic_name": "Edge AI",
            "total_score": 7.2,
            "features": {"impact": 6.0, "feasibility": 7.5, "novelty": 8.0, "risk_penalty": 3.0, "research_signal": 6.0},
            "project_count": 2,
            "evidence_count": 8,
            "evidence": ["snippet2"],
        },
    ],
    "executive_summary": {"full_text": "This is the executive summary."},
    "asis_analysis": {"full_text": "As-is analysis text."},
    "tobe_direction": {"full_text": "To-be direction text."},
    "feasibility_evidence": {"full_text": "Feasibility evidence text."},
    "strategy_cards": [
        {
            "rank": 1,
            "topic_id": "t1",
            "topic_name": "RAG Pipeline",
            "competitive_edge": "Strong RAG foundation",
            "innovation_ideas": [{"idea": "MetaRAG integration"}],
        },
    ],
    "consensus_summary": {"final_rationale": "Committee approved top 2 topics.", "final_consensus_ids": ["t1", "t2"]},
    "research_sources": [{"title": "MetaRAG Paper", "url": "https://arxiv.org/abs/2509.09360"}],
    "section_status": {"executive_summary": "ok", "asis_analysis": "ok"},
    "orchestration": {"profile": "standard"},
    "debate_rounds_executed": 2,
}


# ── NotionClient tests ────────────────────────────────────────────────


def test_client_retry_on_429(mock_session, notion_client):
    """429 response should retry after Retry-After header."""
    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.headers = {"Retry-After": "0.01"}
    resp_429.json.return_value = {}

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.content = b'{"ok":true}'
    resp_200.json.return_value = {"ok": True}

    mock_session.request.side_effect = [resp_429, resp_200]

    with patch("ora_automation_api.notion_client.time.sleep"):
        result = notion_client._request("GET", "/test")

    assert result == {"ok": True}
    assert mock_session.request.call_count == 2


def test_client_raises_on_401(mock_session, notion_client):
    """401 should raise NotionAPIError immediately."""
    resp = MagicMock()
    resp.status_code = 401
    resp.content = b'{"code":"unauthorized","message":"Invalid token"}'
    resp.json.return_value = {"code": "unauthorized", "message": "Invalid token"}
    resp.text = "unauthorized"
    mock_session.request.return_value = resp

    with pytest.raises(NotionAPIError) as exc_info:
        notion_client._request("GET", "/users/me")
    assert exc_info.value.status_code == 401


# ── Setup endpoint tests ──────────────────────────────────────────────


@patch("ora_automation_api.notion_router.NotionClient")
def test_setup_creates_structure(MockClient, client):
    """POST /notion/setup should create hub + 2 DBs + dashboard."""
    mock_instance = MagicMock()
    MockClient.return_value = mock_instance

    created_ids = iter(["hub-id", "rdb-id", "tdb-id", "dash-id"])
    def mock_create_page(**kwargs):
        return {"id": next(created_ids), "url": "https://notion.so/test"}
    def mock_create_database(**kwargs):
        return {"id": next(created_ids), "url": "https://notion.so/test"}

    mock_instance.create_page.side_effect = mock_create_page
    mock_instance.create_database.side_effect = mock_create_database

    with patch.dict(os.environ, {"NOTION_API_TOKEN": "ntn_test"}):
        resp = client.post("/api/v1/notion/setup")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in ("created", "already_exists")
    assert "hub_page_id" in data
    assert "reports_db_id" in data
    assert "topics_db_id" in data
    assert "dashboard_page_id" in data


@patch("ora_automation_api.notion_router.NotionClient")
def test_setup_idempotent(MockClient, client):
    """Second setup call should return existing IDs."""
    mock_instance = MagicMock()
    MockClient.return_value = mock_instance

    call_count = [0]
    def mock_create_page(**kwargs):
        call_count[0] += 1
        return {"id": f"id-{call_count[0]}", "url": "https://notion.so/test"}
    def mock_create_database(**kwargs):
        call_count[0] += 1
        return {"id": f"id-{call_count[0]}", "url": "https://notion.so/test"}

    mock_instance.create_page.side_effect = mock_create_page
    mock_instance.create_database.side_effect = mock_create_database

    with patch.dict(os.environ, {"NOTION_API_TOKEN": "ntn_test"}):
        resp1 = client.post("/api/v1/notion/setup")
        resp2 = client.post("/api/v1/notion/setup")

    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "already_exists"
    # IDs should be the same
    assert resp1.json()["hub_page_id"] == data2["hub_page_id"]


# ── Publish endpoint tests ────────────────────────────────────────────


@patch("ora_automation_api.notion_router.NotionClient")
def test_publish_report(MockClient, client, tmp_path):
    """POST /notion/publish should create report row + detail + topics."""
    mock_instance = MagicMock()
    MockClient.return_value = mock_instance

    call_count = [0]
    def mock_create_page(**kwargs):
        call_count[0] += 1
        return {"id": f"page-{call_count[0]}", "url": f"https://notion.so/page-{call_count[0]}"}
    def mock_create_database(**kwargs):
        call_count[0] += 1
        return {"id": f"db-{call_count[0]}", "url": f"https://notion.so/db-{call_count[0]}"}

    mock_instance.create_page.side_effect = mock_create_page
    mock_instance.create_database.side_effect = mock_create_database
    mock_instance.append_blocks.return_value = {}

    # First setup
    with patch.dict(os.environ, {"NOTION_API_TOKEN": "ntn_test"}):
        client.post("/api/v1/notion/setup")

    # Write test report
    report_file = tmp_path / "test_report.json"
    report_file.write_text(json.dumps(SAMPLE_REPORT), encoding="utf-8")

    with patch.dict(os.environ, {"NOTION_API_TOKEN": "ntn_test"}):
        with patch("ora_automation_api.notion_router._resolve_report_path", return_value=report_file):
            resp = client.post("/api/v1/notion/publish/test_report.json")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "published"
    assert "report_page_id" in data


def test_publish_without_setup_fails(client):
    """Publish without setup should return 400."""
    with patch.dict(os.environ, {"NOTION_API_TOKEN": "ntn_test"}):
        resp = client.post("/api/v1/notion/publish/nonexistent.json")
    assert resp.status_code == 400
    assert "setup" in resp.json()["detail"].lower()


# ── Status endpoint tests ─────────────────────────────────────────────


@patch("ora_automation_api.notion_router.NotionClient")
def test_status_connected(MockClient, client):
    """GET /notion/status with valid token should return connected=true."""
    mock_instance = MagicMock()
    MockClient.return_value = mock_instance
    mock_instance.check_connection.return_value = {"name": "TestBot"}

    with patch.dict(os.environ, {"NOTION_API_TOKEN": "ntn_test"}):
        resp = client.get("/api/v1/notion/status")

    assert resp.status_code == 200
    data = resp.json()
    assert data["connected"] is True


def test_status_no_token(client):
    """GET /notion/status without token should return connected=false."""
    with patch.dict(os.environ, {"NOTION_API_TOKEN": ""}):
        resp = client.get("/api/v1/notion/status")
    assert resp.status_code == 200
    assert resp.json()["connected"] is False


# ── Block batching tests ──────────────────────────────────────────────


def test_block_batching():
    """Blocks exceeding 100 should be split into multiple batches."""
    blocks = [{"type": "paragraph"} for _ in range(250)]
    batches = _split_into_batches(blocks, batch_size=100)
    assert len(batches) == 3
    assert len(batches[0]) == 100
    assert len(batches[1]) == 100
    assert len(batches[2]) == 50


# ── Text splitting tests ─────────────────────────────────────────────


def test_text_splitting():
    """Text exceeding 2000 chars should be split into multiple rich_text elements."""
    long_text = "A" * 5000
    parts = _split_rich_text(long_text, max_len=2000)
    assert len(parts) == 3
    assert len(parts[0]["text"]["content"]) == 2000
    assert len(parts[1]["text"]["content"]) == 2000
    assert len(parts[2]["text"]["content"]) == 1000
