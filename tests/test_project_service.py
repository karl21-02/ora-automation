"""Tests for project synchronization service."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ora_automation_api.models import Base, GithubInstallation, GithubRepo, Project
from ora_automation_api.project_service import match_project_to_github, sync_local_workspace


@pytest.fixture
def db():
    """Create in-memory SQLite database for tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Enable FK constraints
    from sqlalchemy import event
    event.listen(engine, "connect", lambda c, _: c.execute("PRAGMA foreign_keys=ON"))

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def github_installation(db):
    """Create a test GitHub installation."""
    inst = GithubInstallation(
        id=uuid4().hex,
        installation_id=12345,
        account_type="Organization",
        account_login="test-org",
        account_id=1234,
    )
    db.add(inst)
    db.commit()
    return inst


@pytest.fixture
def github_repo(db, github_installation):
    """Create a test GitHub repo."""
    repo = GithubRepo(
        id=uuid4().hex,
        installation_id=github_installation.id,
        repo_id=67890,
        name="test-repo",
        full_name="test-org/test-repo",
        html_url="https://github.com/test-org/test-repo",
        clone_url="https://github.com/test-org/test-repo.git",
        default_branch="main",
    )
    db.add(repo)
    db.commit()
    return repo


# ── sync_local_workspace Tests ────────────────────────────────────────


def test_sync_local_workspace_creates_new_project(db):
    """Test sync creates new project from local scan."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a mock repo
        repo_path = Path(tmpdir) / "my-project"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()
        (repo_path / "main.py").touch()

        with patch("ora_automation_api.project_service.scan_local_workspace") as mock_scan:
            mock_scan.return_value = [{
                "name": "my-project",
                "path": str(repo_path),
                "remote_url": None,
                "language": "Python",
            }]

            result = sync_local_workspace(tmpdir, db)

        assert result["created"] == 1
        assert result["updated"] == 0
        assert result["unchanged"] == 0

        # Check project was created
        project = db.query(Project).filter(Project.name == "my-project").first()
        assert project is not None
        assert project.local_path == str(repo_path)
        assert project.language == "Python"
        assert project.source_type == "local"


def test_sync_local_workspace_matches_github_repo(db, github_repo):
    """Test sync matches local repo to GitHub repo by URL."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test-repo"
        repo_path.mkdir()

        with patch("ora_automation_api.project_service.scan_local_workspace") as mock_scan:
            mock_scan.return_value = [{
                "name": "test-repo",
                "path": str(repo_path),
                "remote_url": "git@github.com:test-org/test-repo.git",
                "language": "Python",
            }]

            result = sync_local_workspace(tmpdir, db)

        assert result["created"] == 1

        project = db.query(Project).filter(Project.name == "test-repo").first()
        assert project is not None
        assert project.github_repo_id == github_repo.id
        assert project.source_type == "github"


def test_sync_local_workspace_updates_existing(db, github_repo):
    """Test sync updates existing project when GitHub match is found."""
    # Create existing project without GitHub link
    existing = Project(
        id=uuid4().hex,
        name="test-repo",
        local_path="/old/path/test-repo",
        source_type="local",
    )
    db.add(existing)
    db.commit()

    with patch("ora_automation_api.project_service.scan_local_workspace") as mock_scan:
        mock_scan.return_value = [{
            "name": "test-repo",
            "path": "/old/path/test-repo",
            "remote_url": "https://github.com/test-org/test-repo.git",
            "language": "TypeScript",
        }]

        result = sync_local_workspace("/old/path", db)

    assert result["created"] == 0
    assert result["updated"] == 1
    assert result["unchanged"] == 0

    db.refresh(existing)
    assert existing.github_repo_id == github_repo.id
    assert existing.source_type == "github"
    assert existing.language == "TypeScript"


def test_sync_local_workspace_unchanged(db):
    """Test sync reports unchanged for existing project with no updates."""
    existing = Project(
        id=uuid4().hex,
        name="stable-project",
        local_path="/some/path/stable-project",
        source_type="local",
        language="Go",
    )
    db.add(existing)
    db.commit()

    with patch("ora_automation_api.project_service.scan_local_workspace") as mock_scan:
        mock_scan.return_value = [{
            "name": "stable-project",
            "path": "/some/path/stable-project",
            "remote_url": None,
            "language": "Go",
        }]

        result = sync_local_workspace("/some/path", db)

    assert result["created"] == 0
    assert result["updated"] == 0
    assert result["unchanged"] == 1


def test_sync_local_workspace_empty(db):
    """Test sync with no local repos."""
    with patch("ora_automation_api.project_service.scan_local_workspace") as mock_scan:
        mock_scan.return_value = []

        result = sync_local_workspace("/empty/path", db)

    assert result["created"] == 0
    assert result["updated"] == 0
    assert result["unchanged"] == 0


def test_sync_local_workspace_multiple_repos(db, github_repo):
    """Test sync with multiple local repos."""
    with patch("ora_automation_api.project_service.scan_local_workspace") as mock_scan:
        mock_scan.return_value = [
            {
                "name": "test-repo",
                "path": "/workspace/test-repo",
                "remote_url": "https://github.com/test-org/test-repo.git",
                "language": "Python",
            },
            {
                "name": "local-only",
                "path": "/workspace/local-only",
                "remote_url": None,
                "language": "JavaScript",
            },
            {
                "name": "non-github",
                "path": "/workspace/non-github",
                "remote_url": "https://gitlab.com/user/repo.git",
                "language": "Rust",
            },
        ]

        result = sync_local_workspace("/workspace", db)

    assert result["created"] == 3
    assert db.query(Project).count() == 3

    # Check GitHub-linked project
    gh_project = db.query(Project).filter(Project.name == "test-repo").first()
    assert gh_project.github_repo_id == github_repo.id
    assert gh_project.source_type == "github"

    # Check local-only projects
    local_project = db.query(Project).filter(Project.name == "local-only").first()
    assert local_project.github_repo_id is None
    assert local_project.source_type == "local"


# ── match_project_to_github Tests ─────────────────────────────────────


def test_match_project_to_github_success(db, github_repo):
    """Test matching an unlinked project to GitHub repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test-repo"
        repo_path.mkdir()
        git_dir = repo_path / ".git"
        git_dir.mkdir()
        config = git_dir / "config"
        config.write_text("""
[remote "origin"]
    url = git@github.com:test-org/test-repo.git
    fetch = +refs/heads/*:refs/remotes/origin/*
""")

        project = Project(
            id=uuid4().hex,
            name="test-repo",
            local_path=str(repo_path),
            source_type="local",
        )
        db.add(project)
        db.commit()

        result = match_project_to_github(project, db)

        assert result is True
        db.refresh(project)
        assert project.github_repo_id == github_repo.id
        assert project.source_type == "github"


def test_match_project_to_github_already_linked(db, github_repo):
    """Test no-op when project is already linked."""
    project = Project(
        id=uuid4().hex,
        name="linked-project",
        local_path="/some/path",
        source_type="github",
        github_repo_id=github_repo.id,
    )
    db.add(project)
    db.commit()

    result = match_project_to_github(project, db)

    assert result is False  # No change


def test_match_project_to_github_no_local_path(db):
    """Test returns False when project has no local_path."""
    project = Project(
        id=uuid4().hex,
        name="github-only-project",
        source_type="github_only",
    )
    db.add(project)
    db.commit()

    result = match_project_to_github(project, db)

    assert result is False


def test_match_project_to_github_no_remote(db):
    """Test returns False when local repo has no remote."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "no-remote"
        repo_path.mkdir()
        git_dir = repo_path / ".git"
        git_dir.mkdir()
        # No config file with remote

        project = Project(
            id=uuid4().hex,
            name="no-remote",
            local_path=str(repo_path),
            source_type="local",
        )
        db.add(project)
        db.commit()

        result = match_project_to_github(project, db)

        assert result is False


def test_match_project_to_github_non_github_remote(db):
    """Test returns False when remote is not GitHub."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "gitlab-repo"
        repo_path.mkdir()
        git_dir = repo_path / ".git"
        git_dir.mkdir()
        config = git_dir / "config"
        config.write_text("""
[remote "origin"]
    url = git@gitlab.com:user/repo.git
""")

        project = Project(
            id=uuid4().hex,
            name="gitlab-repo",
            local_path=str(repo_path),
            source_type="local",
        )
        db.add(project)
        db.commit()

        result = match_project_to_github(project, db)

        assert result is False


def test_match_project_to_github_no_match_found(db):
    """Test returns False when no matching GitHub repo exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "unmatched"
        repo_path.mkdir()
        git_dir = repo_path / ".git"
        git_dir.mkdir()
        config = git_dir / "config"
        config.write_text("""
[remote "origin"]
    url = git@github.com:other-org/other-repo.git
""")

        project = Project(
            id=uuid4().hex,
            name="unmatched",
            local_path=str(repo_path),
            source_type="local",
        )
        db.add(project)
        db.commit()

        # No GithubRepo for other-org/other-repo
        result = match_project_to_github(project, db)

        assert result is False
