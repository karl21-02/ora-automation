"""Project synchronization service.

Syncs local workspace repos with GitHub repos into a unified Project table.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy.orm import Session

from .local_scanner import is_github_url, normalize_github_url, scan_local_workspace
from .models import GithubRepo, Project

logger = logging.getLogger(__name__)


def sync_local_workspace(
    workspace_path: str,
    db: Session,
) -> dict[str, int]:
    """Scan local workspace and sync projects to database.

    For each local repo:
    - If already exists (by local_path): update if needed
    - If new: create Project, try to match with GithubRepo by URL

    Args:
        workspace_path: Path to the workspace root.
        db: Database session.

    Returns:
        Dict with counts: created, updated, unchanged.
    """
    local_repos = scan_local_workspace(workspace_path)
    github_repos = db.query(GithubRepo).all()

    # Build lookup map for GitHub repos by normalized URL
    github_by_url: dict[str, GithubRepo] = {}
    for gh in github_repos:
        normalized = normalize_github_url(gh.clone_url)
        if normalized:
            github_by_url[normalized] = gh

    created, updated, unchanged = 0, 0, 0

    for local in local_repos:
        local_path = local["path"]

        # Check if project already exists
        existing = db.query(Project).filter(Project.local_path == local_path).first()

        # Try to match with GitHub repo
        github_match: GithubRepo | None = None
        if local["remote_url"] and is_github_url(local["remote_url"]):
            normalized_local = normalize_github_url(local["remote_url"])
            github_match = github_by_url.get(normalized_local)

        if existing:
            # Update existing project if GitHub match found
            needs_update = False

            if github_match and not existing.github_repo_id:
                existing.github_repo_id = github_match.id
                existing.source_type = "github"
                needs_update = True

            if local["language"] and existing.language != local["language"]:
                existing.language = local["language"]
                needs_update = True

            if needs_update:
                updated += 1
            else:
                unchanged += 1
        else:
            # Create new project
            project = Project(
                id=uuid4().hex,
                name=local["name"],
                local_path=local_path,
                language=local["language"],
                source_type="github" if github_match else "local",
                github_repo_id=github_match.id if github_match else None,
            )
            db.add(project)
            created += 1

    db.commit()
    logger.info(
        "Local sync complete: created=%d, updated=%d, unchanged=%d",
        created, updated, unchanged,
    )
    return {"created": created, "updated": updated, "unchanged": unchanged}


def match_project_to_github(
    project: Project,
    db: Session,
) -> bool:
    """Try to match an existing local project to a GitHub repo.

    Args:
        project: Project to match.
        db: Database session.

    Returns:
        True if a match was found and linked.
    """
    if project.github_repo_id:
        return False  # Already linked

    if not project.local_path:
        return False

    # Get remote URL from local repo
    from pathlib import Path
    from .local_scanner import extract_git_remote

    repo_path = Path(project.local_path)
    if not repo_path.exists():
        return False

    remote_url = extract_git_remote(repo_path)
    if not remote_url or not is_github_url(remote_url):
        return False

    # Find matching GitHub repo
    normalized = normalize_github_url(remote_url)
    github_repos = db.query(GithubRepo).all()

    for gh in github_repos:
        if normalize_github_url(gh.clone_url) == normalized:
            project.github_repo_id = gh.id
            project.source_type = "github"
            db.commit()
            logger.info("Matched project %s to GitHub repo %s", project.name, gh.full_name)
            return True

    return False
