"""Notion integration API endpoints."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import NotionSyncState
from .notion_client import NotionAPIError, NotionClient
from .notion_publisher import NotionPublisher
from .schemas import (
    NotionPublishResponse,
    NotionSetupResponse,
    NotionStatusResponse,
    NotionSyncResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/notion", tags=["notion"])


def _require_token() -> str:
    token = settings.notion_api_token
    if not token:
        raise HTTPException(status_code=503, detail="NOTION_API_TOKEN not configured")
    return token


def _get_sync(db: Session, entity_type: str, entity_key: str = "singleton") -> NotionSyncState | None:
    return db.scalar(
        select(NotionSyncState).where(
            NotionSyncState.entity_type == entity_type,
            NotionSyncState.entity_key == entity_key,
        )
    )


def _require_setup(db: Session) -> tuple[str, str, str, str]:
    """Return (hub_page_id, reports_db_id, topics_db_id, dashboard_page_id) or raise 400."""
    hub = _get_sync(db, "hub_page")
    reports_db = _get_sync(db, "reports_db")
    topics_db = _get_sync(db, "topics_db")
    dashboard = _get_sync(db, "dashboard_page")
    if not all([hub, reports_db, topics_db, dashboard]):
        raise HTTPException(status_code=400, detail="Run POST /api/v1/notion/setup first")
    return (
        hub.notion_page_id,  # type: ignore[union-attr]
        reports_db.notion_page_id,  # type: ignore[union-attr]
        topics_db.notion_page_id,  # type: ignore[union-attr]
        dashboard.notion_page_id,  # type: ignore[union-attr]
    )


def _save_sync(
    db: Session,
    entity_type: str,
    entity_key: str,
    notion_page_id: str,
    notion_url: str | None = None,
    source_report_path: str | None = None,
    metadata_json: dict | None = None,
) -> NotionSyncState:
    existing = _get_sync(db, entity_type, entity_key)
    if existing:
        existing.notion_page_id = notion_page_id
        existing.notion_url = notion_url
        existing.source_report_path = source_report_path
        existing.metadata_json = metadata_json or {}
        existing.synced_at = datetime.now(timezone.utc)
        db.add(existing)
    else:
        existing = NotionSyncState(
            entity_type=entity_type,
            entity_key=entity_key,
            notion_page_id=notion_page_id,
            notion_url=notion_url,
            source_report_path=source_report_path,
            metadata_json=metadata_json or {},
        )
        db.add(existing)
    db.commit()
    db.refresh(existing)
    return existing


def _find_report_json_files() -> list[Path]:
    """Scan research_reports directories for JSON report files."""
    files: list[Path] = []
    for search_dir in [
        settings.run_output_dir,
        settings.automation_root / "research_reports",
    ]:
        if not search_dir.exists():
            continue
        count = 0
        for jf in search_dir.rglob("*.json"):
            if count >= 500:
                break
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                if "ranked" in data and "report_version" in data:
                    files.append(jf)
            except Exception:
                continue
            count += 1
    return sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)


# ── POST /setup ───────────────────────────────────────────────────────


@router.post("/setup", response_model=NotionSetupResponse)
def setup_notion(db: Session = Depends(get_db)) -> NotionSetupResponse:
    """Create Ora R&D Hub structure in Notion (idempotent)."""
    token = _require_token()

    # Check if already set up
    hub = _get_sync(db, "hub_page")
    reports_db = _get_sync(db, "reports_db")
    topics_db = _get_sync(db, "topics_db")
    dashboard = _get_sync(db, "dashboard_page")

    if all([hub, reports_db, topics_db, dashboard]):
        return NotionSetupResponse(
            hub_page_id=hub.notion_page_id,  # type: ignore[union-attr]
            reports_db_id=reports_db.notion_page_id,  # type: ignore[union-attr]
            topics_db_id=topics_db.notion_page_id,  # type: ignore[union-attr]
            dashboard_page_id=dashboard.notion_page_id,  # type: ignore[union-attr]
            status="already_exists",
        )

    client = NotionClient(token=token)
    try:
        # 1. Hub page (workspace-level)
        if not hub:
            hub_page = client.create_page(
                parent={"workspace": True},
                properties={"title": [{"text": {"content": "Ora R&D Hub"}}]},
                icon={"emoji": "\U0001f680"},
            )
            hub_page_id = hub_page["id"]
            _save_sync(db, "hub_page", "singleton", hub_page_id, hub_page.get("url"))
        else:
            hub_page_id = hub.notion_page_id

        # 2. R&D Reports database
        if not reports_db:
            rdb = client.create_database(
                parent={"type": "page_id", "page_id": hub_page_id},
                title=[{"type": "text", "text": {"content": "R&D Reports"}}],
                properties={
                    "Name": {"title": {}},
                    "Report Date": {"date": {}},
                    "Focus": {"rich_text": {}},
                    "Version": {"rich_text": {}},
                    "Topic Count": {"number": {}},
                    "Top Score": {"number": {}},
                    "Debate Rounds": {"number": {}},
                    "Profile": {"rich_text": {}},
                    "Section Status": {"rich_text": {}},
                },
                icon={"emoji": "\U0001f4ca"},
            )
            _save_sync(db, "reports_db", "singleton", rdb["id"], rdb.get("url"))
            reports_db_id = rdb["id"]
        else:
            reports_db_id = reports_db.notion_page_id

        # 3. Research Topics database
        if not topics_db:
            tdb = client.create_database(
                parent={"type": "page_id", "page_id": hub_page_id},
                title=[{"type": "text", "text": {"content": "Research Topics"}}],
                properties={
                    "Name": {"title": {}},
                    "Topic ID": {"rich_text": {}},
                    "Total Score": {"number": {}},
                    "Impact": {"number": {}},
                    "Feasibility": {"number": {}},
                    "Novelty": {"number": {}},
                    "Risk Penalty": {"number": {}},
                    "Research Signal": {"number": {}},
                    "Project Count": {"number": {}},
                    "Rank": {"number": {}},
                },
                icon={"emoji": "\U0001f9ea"},
            )
            _save_sync(db, "topics_db", "singleton", tdb["id"], tdb.get("url"))
            topics_db_id = tdb["id"]
        else:
            topics_db_id = topics_db.notion_page_id

        # 4. Dashboard page
        if not dashboard:
            dash = client.create_page(
                parent={"type": "page_id", "page_id": hub_page_id},
                properties={"title": [{"text": {"content": "Analysis Dashboard"}}]},
                children=[
                    {
                        "object": "block",
                        "type": "heading_2",
                        "heading_2": {
                            "rich_text": [{"type": "text", "text": {"content": "Ora R&D Dashboard"}}],
                        },
                    },
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {"type": "text", "text": {"content": "Dashboard will be updated after each analysis run."}},
                            ],
                        },
                    },
                ],
                icon={"emoji": "\U0001f4cb"},
            )
            _save_sync(db, "dashboard_page", "singleton", dash["id"], dash.get("url"))
            dashboard_page_id = dash["id"]
        else:
            dashboard_page_id = dashboard.notion_page_id

        return NotionSetupResponse(
            hub_page_id=hub_page_id,
            reports_db_id=reports_db_id,
            topics_db_id=topics_db_id,
            dashboard_page_id=dashboard_page_id,
            status="created",
        )

    except NotionAPIError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))
    finally:
        client.close()


# ── POST /publish/{report_path} ──────────────────────────────────────


@router.post("/publish/{report_path:path}", response_model=NotionPublishResponse)
def publish_report(report_path: str, db: Session = Depends(get_db)) -> NotionPublishResponse:
    """Publish a specific JSON report to Notion (idempotent)."""
    token = _require_token()
    hub_id, reports_db_id, topics_db_id, _ = _require_setup(db)

    # Check idempotency
    existing = _get_sync(db, "report", report_path)
    if existing:
        return NotionPublishResponse(
            report_page_id=existing.notion_page_id,
            report_url=existing.notion_url,
            status="already_synced",
        )

    # Resolve file path
    file_path = _resolve_report_path(report_path)
    if not file_path:
        raise HTTPException(status_code=404, detail=f"Report file not found: {report_path}")

    try:
        report_data = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse report: {exc}")

    client = NotionClient(token=token)
    try:
        publisher = NotionPublisher(
            client=client,
            reports_db_id=reports_db_id,
            topics_db_id=topics_db_id,
            hub_page_id=hub_id,
        )
        result = publisher.publish_report(report_data, str(file_path))
    except NotionAPIError as exc:
        raise HTTPException(status_code=exc.status_code or 502, detail=str(exc))
    finally:
        client.close()

    # Record sync
    _save_sync(
        db,
        "report",
        report_path,
        result["report_page_id"],
        result.get("report_url"),
        str(file_path),
        {"topic_count": len(result.get("topic_pages", []))},
    )

    return NotionPublishResponse(
        report_page_id=result["report_page_id"],
        report_url=result.get("report_url"),
        topic_pages=result.get("topic_pages", []),
        status="published",
    )


# ── GET /status ───────────────────────────────────────────────────────


@router.get("/status", response_model=NotionStatusResponse)
def notion_status(db: Session = Depends(get_db)) -> NotionStatusResponse:
    """Check Notion connection and sync status."""
    token = settings.notion_api_token
    if not token:
        return NotionStatusResponse(connected=False)

    client = NotionClient(token=token)
    try:
        user_info = client.check_connection()
        bot_name = user_info.get("name") or user_info.get("bot", {}).get("owner", {}).get("user", {}).get("name", "")
    except NotionAPIError:
        return NotionStatusResponse(connected=False)
    finally:
        client.close()

    # Count synced reports
    synced_reports = db.scalars(
        select(NotionSyncState).where(NotionSyncState.entity_type == "report")
    ).all()
    synced_names = {row.entity_key for row in synced_reports}

    last_sync = None
    if synced_reports:
        last_sync = max(row.synced_at for row in synced_reports)

    # Find unsynced
    all_report_files = _find_report_json_files()
    unsynced = [f.name for f in all_report_files if f.name not in synced_names]

    return NotionStatusResponse(
        connected=True,
        bot_name=bot_name,
        synced_reports_count=len(synced_names),
        unsynced_reports=unsynced[:50],
        last_sync_at=last_sync,
    )


# ── POST /sync ────────────────────────────────────────────────────────


@router.post("/sync", response_model=NotionSyncResponse)
def sync_all_reports(db: Session = Depends(get_db)) -> NotionSyncResponse:
    """Publish all unsynced reports to Notion."""
    token = _require_token()
    hub_id, reports_db_id, topics_db_id, _ = _require_setup(db)

    # Find synced report names
    synced_rows = db.scalars(
        select(NotionSyncState).where(NotionSyncState.entity_type == "report")
    ).all()
    synced_keys = {row.entity_key for row in synced_rows}

    all_files = _find_report_json_files()
    unsynced_files = [f for f in all_files if f.name not in synced_keys]

    client = NotionClient(token=token)
    try:
        publisher = NotionPublisher(
            client=client,
            reports_db_id=reports_db_id,
            topics_db_id=topics_db_id,
            hub_page_id=hub_id,
        )

        synced: list[str] = []
        skipped: list[str] = []
        errors: list[dict] = []

        for file_path in unsynced_files:
            try:
                report_data = json.loads(file_path.read_text(encoding="utf-8"))
                result = publisher.publish_report(report_data, str(file_path))
                _save_sync(
                    db,
                    "report",
                    file_path.name,
                    result["report_page_id"],
                    result.get("report_url"),
                    str(file_path),
                    {"topic_count": len(result.get("topic_pages", []))},
                )
                synced.append(file_path.name)
            except NotionAPIError as exc:
                errors.append({"file": file_path.name, "error": str(exc)})
            except Exception as exc:
                errors.append({"file": file_path.name, "error": str(exc)})
    finally:
        client.close()

    return NotionSyncResponse(
        synced=synced,
        skipped=skipped,
        errors=errors,
        status="completed",
    )


# ── Helpers ───────────────────────────────────────────────────────────


def _resolve_report_path(report_path: str) -> Path | None:
    """Try to resolve a report path from various locations."""
    candidates = [
        Path(report_path),
        settings.run_output_dir / report_path,
        settings.automation_root / "research_reports" / report_path,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    # Also search recursively
    for search_dir in [settings.run_output_dir, settings.automation_root / "research_reports"]:
        if not search_dir.exists():
            continue
        for i, match in enumerate(search_dir.rglob(report_path)):
            if match.is_file():
                return match
            if i >= 100:
                break
    return None
