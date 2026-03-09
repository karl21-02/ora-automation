"""Tests for local workspace scanner and project sync."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ora_automation_api.database import Base
from ora_automation_api.local_scanner import (
    extract_git_remote,
    is_github_url,
    normalize_github_url,
    scan_local_workspace,
)
from ora_automation_api.models import GithubInstallation, GithubRepo, Project
from ora_automation_api.project_service import sync_local_workspace


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def db_session():
    """Create an in-memory SQLite database with FK enforcement."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def temp_workspace():
    """Create a temporary workspace with mock git repos."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create repo1 with GitHub remote
        repo1 = workspace / "repo1"
        repo1.mkdir()
        (repo1 / ".git").mkdir()
        (repo1 / ".git" / "config").write_text(
            '[remote "origin"]\n\turl = git@github.com:owner/repo1.git\n'
        )
        (repo1 / "main.py").write_text("print('hello')")

        # Create repo2 with HTTPS remote
        repo2 = workspace / "repo2"
        repo2.mkdir()
        (repo2 / ".git").mkdir()
        (repo2 / ".git" / "config").write_text(
            '[remote "origin"]\n\turl = https://github.com/owner/repo2.git\n'
        )
        (repo2 / "index.ts").write_text("console.log('hello')")

        # Create repo3 without remote
        repo3 = workspace / "repo3"
        repo3.mkdir()
        (repo3 / ".git").mkdir()
        (repo3 / ".git" / "config").write_text("[core]\n\tbare = false\n")

        # Create non-git directory
        (workspace / "not-a-repo").mkdir()
        (workspace / "not-a-repo" / "file.txt").write_text("hello")

        yield workspace


# ── URL Normalization Tests ──────────────────────────────────────────


def test_normalize_github_url_ssh():
    """Test SSH URL normalization."""
    assert normalize_github_url("git@github.com:owner/repo.git") == "github.com/owner/repo"


def test_normalize_github_url_https():
    """Test HTTPS URL normalization."""
    assert normalize_github_url("https://github.com/owner/repo.git") == "github.com/owner/repo"


def test_normalize_github_url_https_no_suffix():
    """Test HTTPS URL without .git suffix."""
    assert normalize_github_url("https://github.com/owner/repo") == "github.com/owner/repo"


def test_normalize_github_url_http():
    """Test HTTP URL normalization."""
    assert normalize_github_url("http://github.com/owner/repo.git") == "github.com/owner/repo"


def test_normalize_github_url_case_insensitive():
    """Test URL normalization is case-insensitive."""
    assert normalize_github_url("https://GitHub.com/Owner/Repo") == "github.com/owner/repo"


def test_normalize_github_url_empty():
    """Test empty URL returns empty string."""
    assert normalize_github_url("") == ""


def test_normalize_github_url_trailing_slash():
    """Test trailing slash is removed."""
    assert normalize_github_url("https://github.com/owner/repo/") == "github.com/owner/repo"


def test_is_github_url_true():
    """Test is_github_url returns True for GitHub URLs."""
    assert is_github_url("git@github.com:owner/repo.git") is True
    assert is_github_url("https://github.com/owner/repo") is True


def test_is_github_url_false():
    """Test is_github_url returns False for non-GitHub URLs."""
    assert is_github_url("git@gitlab.com:owner/repo.git") is False
    assert is_github_url("https://bitbucket.org/owner/repo") is False
    assert is_github_url(None) is False
    assert is_github_url("") is False


# ── Git Remote Extraction Tests ──────────────────────────────────────


def test_extract_git_remote(temp_workspace):
    """Test extracting git remote URL from repo."""
    repo_path = temp_workspace / "repo1"
    url = extract_git_remote(repo_path)
    assert url == "git@github.com:owner/repo1.git"


def test_extract_git_remote_no_remote(temp_workspace):
    """Test repo without remote returns None."""
    repo_path = temp_workspace / "repo3"
    url = extract_git_remote(repo_path)
    assert url is None


def test_extract_git_remote_not_git_dir(temp_workspace):
    """Test non-git directory returns None."""
    repo_path = temp_workspace / "not-a-repo"
    url = extract_git_remote(repo_path)
    assert url is None


# ── Workspace Scan Tests ──────────────────────────────────────────────


def test_scan_local_workspace(temp_workspace):
    """Test scanning workspace for git repos."""
    repos = scan_local_workspace(temp_workspace)

    assert len(repos) == 3

    # Find repos by name
    repo_by_name = {r["name"]: r for r in repos}

    assert "repo1" in repo_by_name
    assert repo_by_name["repo1"]["remote_url"] == "git@github.com:owner/repo1.git"
    assert repo_by_name["repo1"]["language"] == "Python"

    assert "repo2" in repo_by_name
    assert repo_by_name["repo2"]["remote_url"] == "https://github.com/owner/repo2.git"
    assert repo_by_name["repo2"]["language"] == "TypeScript"

    assert "repo3" in repo_by_name
    assert repo_by_name["repo3"]["remote_url"] is None


def test_scan_local_workspace_empty():
    """Test scanning non-existent workspace returns empty list."""
    repos = scan_local_workspace("/nonexistent/path")
    assert repos == []


# ── Project Sync Tests ──────────────────────────────────────────────


def test_sync_local_workspace_creates_projects(db_session, temp_workspace):
    """Test syncing creates new projects."""
    result = sync_local_workspace(str(temp_workspace), db_session)

    assert result["created"] == 3
    assert result["updated"] == 0
    assert result["unchanged"] == 0

    # Verify projects were created
    projects = db_session.query(Project).all()
    assert len(projects) == 3


def test_sync_local_workspace_unchanged(db_session, temp_workspace):
    """Test re-syncing marks projects as unchanged."""
    # First sync
    sync_local_workspace(str(temp_workspace), db_session)

    # Second sync
    result = sync_local_workspace(str(temp_workspace), db_session)

    assert result["created"] == 0
    assert result["updated"] == 0
    assert result["unchanged"] == 3


def test_sync_local_workspace_links_github(db_session, temp_workspace):
    """Test syncing links projects to GitHub repos when available."""
    # Create GitHub installation and repo
    installation = GithubInstallation(
        id="inst-001",
        installation_id=12345,
        account_type="Organization",
        account_login="owner",
        account_id=67890,
    )
    github_repo = GithubRepo(
        id="repo-001",
        installation_id="inst-001",
        repo_id=999,
        name="repo1",
        full_name="owner/repo1",
        html_url="https://github.com/owner/repo1",
        clone_url="https://github.com/owner/repo1.git",
    )
    db_session.add_all([installation, github_repo])
    db_session.commit()

    # Sync local workspace
    result = sync_local_workspace(str(temp_workspace), db_session)

    # Find the linked project
    linked_project = db_session.query(Project).filter(
        Project.github_repo_id == "repo-001"
    ).first()

    assert linked_project is not None
    assert linked_project.name == "repo1"
    assert linked_project.source_type == "github"


def test_sync_local_workspace_updates_existing(db_session, temp_workspace):
    """Test syncing updates existing projects when GitHub match found."""
    # First sync without GitHub repos
    sync_local_workspace(str(temp_workspace), db_session)

    # Add GitHub repo that matches repo1
    installation = GithubInstallation(
        id="inst-001",
        installation_id=12345,
        account_type="Organization",
        account_login="owner",
        account_id=67890,
    )
    github_repo = GithubRepo(
        id="repo-001",
        installation_id="inst-001",
        repo_id=999,
        name="repo1",
        full_name="owner/repo1",
        html_url="https://github.com/owner/repo1",
        clone_url="https://github.com/owner/repo1.git",
    )
    db_session.add_all([installation, github_repo])
    db_session.commit()

    # Re-sync
    result = sync_local_workspace(str(temp_workspace), db_session)

    assert result["updated"] == 1  # repo1 now linked to GitHub
    assert result["unchanged"] == 2  # repo2, repo3 unchanged

    # Verify project was updated
    project = db_session.query(Project).filter(Project.name == "repo1").first()
    assert project.github_repo_id == "repo-001"
    assert project.source_type == "github"
