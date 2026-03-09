"""Unified Projects API endpoints."""
from __future__ import annotations

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .models import GithubRepo, Project
from .project_service import sync_local_workspace
from .schemas import (
    LocalScanResult,
    ProjectCreate,
    ProjectList,
    ProjectPrepareResponse,
    ProjectRead,
    ProjectUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/unified-projects", tags=["projects"])


# ── GET /projects ────────────────────────────────────────────────────────


@router.get("", response_model=ProjectList)
def list_projects(
    source_type: str | None = Query(None, description="Filter by source type: local, github, github_only"),
    enabled: bool | None = Query(None, description="Filter by enabled status"),
    search: str | None = Query(None, description="Search by name"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ProjectList:
    """List all projects with optional filters."""
    query = select(Project)

    if source_type:
        query = query.where(Project.source_type == source_type)
    if enabled is not None:
        query = query.where(Project.enabled == enabled)
    if search:
        query = query.where(Project.name.ilike(f"%{search}%"))

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = db.scalar(count_query) or 0

    # Apply pagination
    query = query.order_by(Project.name).offset(offset).limit(limit)
    projects = db.scalars(query).all()

    return ProjectList(
        items=[ProjectRead.model_validate(p) for p in projects],
        total=total,
    )


# ── POST /projects ────────────────────────────────────────────────────────


@router.post("", response_model=ProjectRead, status_code=201)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
) -> ProjectRead:
    """Create a new project manually."""
    # Check for duplicate local_path
    if payload.local_path:
        existing = db.scalar(
            select(Project).where(Project.local_path == payload.local_path)
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Project with local_path '{payload.local_path}' already exists",
            )

    # Validate github_repo_id if provided
    if payload.github_repo_id:
        repo = db.scalar(
            select(GithubRepo).where(GithubRepo.id == payload.github_repo_id)
        )
        if not repo:
            raise HTTPException(status_code=404, detail="GitHub repo not found")

    project = Project(
        id=uuid4().hex,
        name=payload.name.strip(),
        description=payload.description,
        source_type=payload.source_type,
        local_path=payload.local_path,
        github_repo_id=payload.github_repo_id,
        enabled=payload.enabled,
        language=payload.language,
        default_branch=payload.default_branch,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    return ProjectRead.model_validate(project)


# ── GET /projects/{id} ────────────────────────────────────────────────────


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
) -> ProjectRead:
    """Get a project by ID."""
    project = db.scalar(select(Project).where(Project.id == project_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectRead.model_validate(project)


# ── PATCH /projects/{id} ────────────────────────────────────────────────────


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
) -> ProjectRead:
    """Update a project."""
    project = db.scalar(select(Project).where(Project.id == project_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    update_data = payload.model_dump(exclude_unset=True)

    # Check for duplicate local_path
    if "local_path" in update_data and update_data["local_path"]:
        existing = db.scalar(
            select(Project).where(
                Project.local_path == update_data["local_path"],
                Project.id != project_id,
            )
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Project with local_path '{update_data['local_path']}' already exists",
            )

    # Validate github_repo_id if provided
    if "github_repo_id" in update_data and update_data["github_repo_id"]:
        repo = db.scalar(
            select(GithubRepo).where(GithubRepo.id == update_data["github_repo_id"])
        )
        if not repo:
            raise HTTPException(status_code=404, detail="GitHub repo not found")

    for key, value in update_data.items():
        setattr(project, key, value)

    db.commit()
    db.refresh(project)

    return ProjectRead.model_validate(project)


# ── DELETE /projects/{id} ────────────────────────────────────────────────────


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a project."""
    project = db.scalar(select(Project).where(Project.id == project_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    db.delete(project)
    db.commit()


# ── POST /projects/scan-local ────────────────────────────────────────────


@router.post("/scan-local", response_model=LocalScanResult)
def scan_local(
    workspace_path: str | None = Query(None, description="Custom workspace path"),
    db: Session = Depends(get_db),
) -> LocalScanResult:
    """Scan local workspace and sync projects to database."""
    path = workspace_path or str(settings.projects_root)
    result = sync_local_workspace(path, db)
    return LocalScanResult(**result)


# ── POST /projects/{id}/prepare ────────────────────────────────────────────


@router.post("/{project_id}/prepare", response_model=ProjectPrepareResponse)
async def prepare_project(
    project_id: str,
    db: Session = Depends(get_db),
) -> ProjectPrepareResponse:
    """Prepare a project for analysis (clone if needed).

    For github_only projects, performs a shallow clone.
    For local/github projects, verifies the path exists.
    """
    project = db.scalar(select(Project).where(Project.id == project_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # If local path exists, just return it
    if project.local_path:
        from pathlib import Path
        if Path(project.local_path).exists():
            return ProjectPrepareResponse(
                project_id=project_id,
                local_path=project.local_path,
                cloned=False,
            )

    # Need to clone from GitHub
    if not project.github_repo_id:
        raise HTTPException(
            status_code=400,
            detail="Project has no local path and no GitHub repo linked",
        )

    github_repo = db.scalar(
        select(GithubRepo).where(GithubRepo.id == project.github_repo_id)
    )
    if not github_repo:
        raise HTTPException(status_code=404, detail="Linked GitHub repo not found")

    # Perform shallow clone
    from pathlib import Path
    import asyncio

    clone_dir = settings.github_clone_base_dir / github_repo.full_name
    clone_dir.parent.mkdir(parents=True, exist_ok=True)

    if clone_dir.exists():
        # Already cloned, just update local_path
        project.local_path = str(clone_dir)
        db.commit()
        return ProjectPrepareResponse(
            project_id=project_id,
            local_path=str(clone_dir),
            cloned=False,
        )

    # Clone the repo
    cmd = [
        "git", "clone",
        "--depth", "1",
        "--single-branch",
        github_repo.clone_url,
        str(clone_dir),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Clone failed: {stderr.decode()[:500]}",
        )

    # Update project with local path
    project.local_path = str(clone_dir)
    project.source_type = "github"
    db.commit()

    return ProjectPrepareResponse(
        project_id=project_id,
        local_path=str(clone_dir),
        cloned=True,
    )
