"""GitHub App integration API endpoints."""
from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .database import get_db
from .github_client import GitHubAppClient, verify_webhook_signature
from .models import GithubInstallation, GithubRepo
from .schemas import GithubInstallationRead, GithubRepoRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/github", tags=["github"])


def _get_github_client() -> GitHubAppClient:
    """Get GitHub App client, raise 503 if not configured."""
    if not settings.github_app_configured:
        raise HTTPException(
            status_code=503,
            detail="GitHub App not configured. Set GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY.",
        )
    return GitHubAppClient(settings)


# ── GET /install-url ────────────────────────────────────────────────────


@router.get("/install-url")
def get_install_url() -> dict:
    """Get GitHub App installation URL."""
    app_name = settings.github_app_name
    return {
        "url": f"https://github.com/apps/{app_name}/installations/new",
        "app_name": app_name,
    }


# ── POST /webhook ────────────────────────────────────────────────────────


@router.post("/webhook", status_code=200)
async def handle_webhook(request: Request, db: Session = Depends(get_db)) -> dict:
    """Handle GitHub webhook events.

    Supported events:
    - installation.created: Save new installation
    - installation.deleted: Mark installation as deleted
    - installation.suspend: Mark installation as suspended
    - installation.unsuspend: Mark installation as active
    """
    # Verify signature if secret is configured
    if settings.github_webhook_secret:
        signature = request.headers.get("X-Hub-Signature-256", "")
        body = await request.body()
        if not verify_webhook_signature(body, signature, settings.github_webhook_secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = await request.json()
    event = request.headers.get("X-GitHub-Event", "")
    action = payload.get("action", "")

    logger.info("GitHub webhook: event=%s, action=%s", event, action)

    if event == "installation":
        return await _handle_installation_event(payload, action, db)

    return {"status": "ignored", "event": event}


async def _handle_installation_event(payload: dict, action: str, db: Session) -> dict:
    """Handle installation events."""
    installation_data = payload.get("installation", {})
    installation_id = installation_data.get("id")
    account = installation_data.get("account", {})

    if action == "created":
        # Check if already exists
        existing = db.scalar(
            select(GithubInstallation).where(
                GithubInstallation.installation_id == installation_id
            )
        )
        if existing:
            existing.status = "active"
            db.commit()
            return {"status": "reactivated", "installation_id": installation_id}

        # Create new installation
        inst = GithubInstallation(
            id=uuid4().hex,
            installation_id=installation_id,
            account_type=account.get("type", "User"),
            account_login=account.get("login", ""),
            account_id=account.get("id", 0),
            avatar_url=account.get("avatar_url"),
            status="active",
        )
        db.add(inst)
        db.commit()
        return {"status": "created", "installation_id": installation_id}

    elif action == "deleted":
        existing = db.scalar(
            select(GithubInstallation).where(
                GithubInstallation.installation_id == installation_id
            )
        )
        if existing:
            existing.status = "deleted"
            db.commit()
        return {"status": "deleted", "installation_id": installation_id}

    elif action in ("suspend", "suspended"):
        existing = db.scalar(
            select(GithubInstallation).where(
                GithubInstallation.installation_id == installation_id
            )
        )
        if existing:
            existing.status = "suspended"
            db.commit()
        return {"status": "suspended", "installation_id": installation_id}

    elif action in ("unsuspend", "unsuspended"):
        existing = db.scalar(
            select(GithubInstallation).where(
                GithubInstallation.installation_id == installation_id
            )
        )
        if existing:
            existing.status = "active"
            db.commit()
        return {"status": "unsuspended", "installation_id": installation_id}

    return {"status": "ignored", "action": action}


# ── GET /installations ────────────────────────────────────────────────────


@router.get("/installations", response_model=list[GithubInstallationRead])
def list_installations(
    status: str | None = None,
    db: Session = Depends(get_db),
) -> list[GithubInstallationRead]:
    """List all GitHub App installations."""
    query = select(GithubInstallation)
    if status:
        query = query.where(GithubInstallation.status == status)
    else:
        query = query.where(GithubInstallation.status != "deleted")

    installations = db.scalars(query).all()

    # Add repos_count for each installation
    result = []
    for inst in installations:
        count = db.scalar(
            select(func.count(GithubRepo.id)).where(
                GithubRepo.installation_id == inst.id
            )
        )
        inst_dict = GithubInstallationRead.model_validate(inst).model_dump()
        inst_dict["repos_count"] = count or 0
        result.append(GithubInstallationRead(**inst_dict))

    return result


# ── POST /installations/{id}/sync ────────────────────────────────────────


@router.post("/installations/{installation_id}/sync")
async def sync_installation(
    installation_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """Sync repositories for an installation from GitHub."""
    installation = db.scalar(
        select(GithubInstallation).where(GithubInstallation.id == installation_id)
    )
    if not installation:
        raise HTTPException(status_code=404, detail="Installation not found")

    if installation.status != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Installation is {installation.status}, cannot sync",
        )

    client = _get_github_client()

    try:
        repos = await client.list_installation_repos(installation.installation_id)
    except Exception as e:
        logger.exception("Failed to fetch repos from GitHub")
        raise HTTPException(status_code=502, detail=f"GitHub API error: {e}")

    created, updated = 0, 0

    for repo_data in repos:
        existing = db.scalar(
            select(GithubRepo).where(GithubRepo.repo_id == repo_data.repo_id)
        )

        if existing:
            # Update existing repo
            existing.name = repo_data.name
            existing.full_name = repo_data.full_name
            existing.description = repo_data.description
            existing.html_url = repo_data.html_url
            existing.clone_url = repo_data.clone_url
            existing.default_branch = repo_data.default_branch
            existing.language = repo_data.language
            existing.stars = repo_data.stars
            existing.is_private = repo_data.is_private
            existing.synced_at = datetime.utcnow()
            updated += 1
        else:
            # Create new repo
            repo = GithubRepo(
                id=uuid4().hex,
                installation_id=installation.id,
                repo_id=repo_data.repo_id,
                name=repo_data.name,
                full_name=repo_data.full_name,
                description=repo_data.description,
                html_url=repo_data.html_url,
                clone_url=repo_data.clone_url,
                default_branch=repo_data.default_branch,
                language=repo_data.language,
                stars=repo_data.stars,
                is_private=repo_data.is_private,
            )
            db.add(repo)
            created += 1

    installation.synced_at = datetime.utcnow()
    db.commit()

    return {
        "status": "synced",
        "installation_id": installation_id,
        "created": created,
        "updated": updated,
        "total": len(repos),
    }


# ── DELETE /installations/{id} ────────────────────────────────────────────


@router.delete("/installations/{installation_id}", status_code=204)
def delete_installation(
    installation_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Mark an installation as deleted (soft delete)."""
    installation = db.scalar(
        select(GithubInstallation).where(GithubInstallation.id == installation_id)
    )
    if not installation:
        raise HTTPException(status_code=404, detail="Installation not found")

    installation.status = "deleted"
    db.commit()


# ── GET /repos ────────────────────────────────────────────────────────────


@router.get("/repos", response_model=list[GithubRepoRead])
def list_repos(
    installation_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[GithubRepoRead]:
    """List synced GitHub repositories."""
    query = select(GithubRepo)

    if installation_id:
        query = query.where(GithubRepo.installation_id == installation_id)

    # Only show repos from active installations
    query = query.join(GithubInstallation).where(
        GithubInstallation.status == "active"
    )

    repos = db.scalars(query.order_by(GithubRepo.full_name)).all()
    return [GithubRepoRead.model_validate(r) for r in repos]
