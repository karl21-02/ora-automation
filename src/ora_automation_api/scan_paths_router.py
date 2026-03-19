"""Scan Paths API endpoints for local workspace management."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .local_scanner import scan_local_workspace
from .models import Project, ScanPath
from .schemas import (
    ScanPathCreate,
    ScanPathList,
    ScanPathRead,
    ScanPathUpdate,
    ScanResult,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scan-paths", tags=["scan-paths"])


# ── GET /scan-paths ────────────────────────────────────────────────────────


@router.get("", response_model=ScanPathList)
def list_scan_paths(
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ScanPathList:
    """List all scan paths with optional filters."""
    query = select(ScanPath)

    if enabled is not None:
        query = query.where(ScanPath.enabled == enabled)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = db.scalar(count_query) or 0

    # Apply pagination
    query = query.order_by(ScanPath.created_at.desc()).offset(offset).limit(limit)
    scan_paths = db.scalars(query).all()

    return ScanPathList(
        items=[ScanPathRead.model_validate(sp) for sp in scan_paths],
        total=total,
    )


# ── POST /scan-paths ────────────────────────────────────────────────────────


@router.post("", response_model=ScanPathRead, status_code=201)
def create_scan_path(
    payload: ScanPathCreate,
    db: Session = Depends(get_db),
) -> ScanPathRead:
    """Create a new scan path."""
    # Normalize and validate path
    path_str = payload.path.strip()
    path_obj = Path(path_str).expanduser().resolve()

    if not path_obj.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {path_str}")
    if not path_obj.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {path_str}")

    normalized_path = str(path_obj)

    # Check for duplicate
    existing = db.scalar(select(ScanPath).where(ScanPath.path == normalized_path))
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Scan path already exists: {normalized_path}",
        )

    scan_path = ScanPath(
        id=uuid4().hex,
        path=normalized_path,
        name=payload.name.strip() if payload.name else None,
        recursive=payload.recursive,
    )
    db.add(scan_path)
    db.commit()
    db.refresh(scan_path)

    return ScanPathRead.model_validate(scan_path)


# ── GET /scan-paths/{id} ────────────────────────────────────────────────────


@router.get("/{scan_path_id}", response_model=ScanPathRead)
def get_scan_path(
    scan_path_id: str,
    db: Session = Depends(get_db),
) -> ScanPathRead:
    """Get a scan path by ID."""
    scan_path = db.scalar(select(ScanPath).where(ScanPath.id == scan_path_id))
    if not scan_path:
        raise HTTPException(status_code=404, detail="Scan path not found")
    return ScanPathRead.model_validate(scan_path)


# ── PATCH /scan-paths/{id} ────────────────────────────────────────────────────


@router.patch("/{scan_path_id}", response_model=ScanPathRead)
def update_scan_path(
    scan_path_id: str,
    payload: ScanPathUpdate,
    db: Session = Depends(get_db),
) -> ScanPathRead:
    """Update a scan path."""
    scan_path = db.scalar(select(ScanPath).where(ScanPath.id == scan_path_id))
    if not scan_path:
        raise HTTPException(status_code=404, detail="Scan path not found")

    update_data = payload.model_dump(exclude_unset=True)

    if "name" in update_data:
        update_data["name"] = update_data["name"].strip() if update_data["name"] else None

    for key, value in update_data.items():
        setattr(scan_path, key, value)

    db.commit()
    db.refresh(scan_path)

    return ScanPathRead.model_validate(scan_path)


# ── DELETE /scan-paths/{id} ────────────────────────────────────────────────────


@router.delete("/{scan_path_id}", status_code=204)
def delete_scan_path(
    scan_path_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a scan path.

    Projects created from this scan path will have their scan_path_id set to NULL.
    """
    scan_path = db.scalar(select(ScanPath).where(ScanPath.id == scan_path_id))
    if not scan_path:
        raise HTTPException(status_code=404, detail="Scan path not found")

    db.delete(scan_path)
    db.commit()


# ── POST /scan-paths/{id}/scan ────────────────────────────────────────────


@router.post("/{scan_path_id}/scan", response_model=ScanResult)
def scan_path(
    scan_path_id: str,
    db: Session = Depends(get_db),
) -> ScanResult:
    """Execute scan on a specific path and sync projects to database."""
    scan_path = db.scalar(select(ScanPath).where(ScanPath.id == scan_path_id))
    if not scan_path:
        raise HTTPException(status_code=404, detail="Scan path not found")

    if not scan_path.enabled:
        raise HTTPException(status_code=400, detail="Scan path is disabled")

    start_time = time.time()

    # Scan directory (returns list of dicts with name, path, remote_url, language)
    scanned_repos = scan_local_workspace(scan_path.path)

    created = 0
    updated = 0

    for repo in scanned_repos:
        existing = db.scalar(select(Project).where(Project.local_path == repo["path"]))

        if existing:
            # Update if language changed
            if repo["language"] and existing.language != repo["language"]:
                existing.language = repo["language"]
                updated += 1
        else:
            # Create new project
            project = Project(
                id=uuid4().hex,
                name=repo["name"],
                source_type="local",
                local_path=repo["path"],
                scan_path_id=scan_path.id,
                language=repo["language"],
            )
            db.add(project)
            created += 1

    # Update scan path stats
    scan_path.last_scanned_at = func.now()
    scan_path.project_count = len(scanned_repos)

    db.commit()

    duration_ms = int((time.time() - start_time) * 1000)

    return ScanResult(
        scan_path_id=scan_path_id,
        projects_found=len(scanned_repos),
        projects_created=created,
        projects_updated=updated,
        duration_ms=duration_ms,
    )


# ── POST /scan-paths/scan-all ────────────────────────────────────────────


@router.post("/scan-all", response_model=list[ScanResult])
def scan_all_paths(
    db: Session = Depends(get_db),
) -> list[ScanResult]:
    """Execute scan on all enabled paths."""
    scan_paths = db.scalars(
        select(ScanPath).where(ScanPath.enabled == True)
    ).all()

    results = []

    for sp in scan_paths:
        start_time = time.time()
        scanned_repos = scan_local_workspace(sp.path)

        created = 0
        updated = 0

        for repo in scanned_repos:
            existing = db.scalar(select(Project).where(Project.local_path == repo["path"]))

            if existing:
                if repo["language"] and existing.language != repo["language"]:
                    existing.language = repo["language"]
                    updated += 1
            else:
                project = Project(
                    id=uuid4().hex,
                    name=repo["name"],
                    source_type="local",
                    local_path=repo["path"],
                    scan_path_id=sp.id,
                    language=repo["language"],
                )
                db.add(project)
                created += 1

        sp.last_scanned_at = func.now()
        sp.project_count = len(scanned_repos)

        duration_ms = int((time.time() - start_time) * 1000)

        results.append(ScanResult(
            scan_path_id=sp.id,
            projects_found=len(scanned_repos),
            projects_created=created,
            projects_updated=updated,
            duration_ms=duration_ms,
        ))

    db.commit()

    return results
