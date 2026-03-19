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
    AnalysisHistoryItem,
    ConfigFile,
    LocalScanResult,
    ProjectConfigResponse,
    ProjectCreate,
    ProjectEnvResponse,
    ProjectHistoryResponse,
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
    force_pull: bool = Query(False, description="Force pull updates if already cloned"),
    db: Session = Depends(get_db),
) -> ProjectPrepareResponse:
    """Prepare a project for analysis (clone if needed).

    For github_only projects, performs a shallow clone.
    For local/github projects, verifies the path exists.
    """
    from pathlib import Path
    from .clone_service import ensure_local_clone, is_cloned

    project = db.scalar(select(Project).where(Project.id == project_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # If local path exists and is valid, just return it
    if project.local_path:
        local_path = Path(project.local_path)
        if local_path.exists():
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

    # Check if already cloned
    already_cloned = is_cloned(github_repo.full_name)

    try:
        clone_path = await ensure_local_clone(
            clone_url=github_repo.clone_url,
            full_name=github_repo.full_name,
            branch=github_repo.default_branch,
            force_pull=force_pull,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Update project with local path
    project.local_path = str(clone_path)
    if project.source_type == "github_only":
        project.source_type = "github"
    db.commit()

    return ProjectPrepareResponse(
        project_id=project_id,
        local_path=str(clone_path),
        cloned=not already_cloned,
    )


# ── GET /projects/{id}/env ────────────────────────────────────────────


@router.get("/{project_id}/env", response_model=ProjectEnvResponse)
def get_project_env(
    project_id: str,
    db: Session = Depends(get_db),
) -> ProjectEnvResponse:
    """Get project .env file contents (sensitive values masked).

    Returns:
        - has_env: whether .env file exists
        - has_env_example: whether .env.example exists
        - env_content: parsed .env with sensitive values masked
        - env_example_content: parsed .env.example (unmasked)
    """
    from .env_reader import read_project_env

    project = db.scalar(select(Project).where(Project.id == project_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.local_path:
        raise HTTPException(
            status_code=400,
            detail="Project has no local path. Use /prepare endpoint first.",
        )

    env_data = read_project_env(project.local_path)

    return ProjectEnvResponse(
        has_env=env_data["has_env"],
        has_env_example=env_data["has_env_example"],
        env_content=env_data["env_content"],
        env_example_content=env_data["env_example_content"],
    )


# ── GET /projects/{id}/config ────────────────────────────────────────────


@router.get("/{project_id}/config", response_model=ProjectConfigResponse)
def get_project_config(
    project_id: str,
    db: Session = Depends(get_db),
) -> ProjectConfigResponse:
    """Get project configuration files.

    Reads common config files like package.json, pyproject.toml, etc.
    """
    from .config_reader import read_project_configs

    project = db.scalar(select(Project).where(Project.id == project_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.local_path:
        raise HTTPException(
            status_code=400,
            detail="Project has no local path. Use /prepare endpoint first.",
        )

    configs = read_project_configs(project.local_path)

    return ProjectConfigResponse(
        files=[ConfigFile(**c) for c in configs]
    )


# ── GET /projects/{id}/history ────────────────────────────────────────────


@router.get("/{project_id}/history", response_model=ProjectHistoryResponse)
def get_project_history(
    project_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ProjectHistoryResponse:
    """Get analysis history for a project.

    Returns orchestration runs associated with this project.
    """
    from .models import OrchestrationRun

    project = db.scalar(select(Project).where(Project.id == project_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Query runs for this project
    query = (
        select(OrchestrationRun)
        .where(OrchestrationRun.project_id == project_id)
        .order_by(OrchestrationRun.created_at.desc())
    )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = db.scalar(count_query) or 0

    # Apply pagination
    query = query.offset(offset).limit(limit)
    runs = db.scalars(query).all()

    items = [
        AnalysisHistoryItem(
            id=run.id,
            run_type=run.target,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.finished_at,
            user_prompt=run.user_prompt[:200] if run.user_prompt else "",
        )
        for run in runs
    ]

    return ProjectHistoryResponse(items=items, total=total)
