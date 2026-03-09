"""Tests for GitHub App integration (DB models, client, webhook verification)."""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ora_automation_api.database import Base, get_db
from ora_automation_api.models import GithubInstallation, GithubRepo, Project

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def db_session():
    """Create an in-memory SQLite database with all tables and FK enforcement."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    # Enable foreign key enforcement in SQLite
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
def mock_settings():
    """Mock settings with GitHub App config."""
    settings = MagicMock()
    settings.github_app_id = "123456"
    # Using a fake RSA key for testing JWT generation
    settings.github_app_private_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0Z3VS5JJcds3xfn/ygWyF8PbnGy0AHB7MnXmZb5hnax6GJmX
Lg7p1TLynSIvS85TFptCKP9vGVNOhkPfKdYXc8SB+q0IM1PHdqvKQfhP5qPxxeNb
4MHkHoUGJdV0yCfq/qX8LNBG9MUv8z4BKXX0Fc2GBTmQnk8lvn6XLf2BN7tqfYtV
w5r2RJTA6RYl3k4J8bqfXB9w4oDbVkc3Y3M/dmQxB5L+e8MgS5AgLHJ0PLBHqQpd
oH5c2KDYKxZrqaA7TJgQyCVTgo0AxY1TiF0A8YYXO5kSE7xPJzPHsB8EgKRwCpTV
nqWXiE3xYYgF8aRV0YrTBhx7x3KMvKqAE4xXrQIDAQABAoIBAF1W6g4aVELNjNdz
rES8MD9Ub1e6TtWWrCWfXQKL7r1FO5HQsRlNkHswQRQAoV1Sb3rSpWmZYlBD1Pf7
M0Pv7EdMNFFqTdNTIkHNjl5f5bVnm4FnUBK/L7DDhCwV1a8j8M8N7bPvR7YdGNlD
dPvQ3pvTZvGNl5ontGUrNMzffHbC3MBIa6M1HNoRPGx4bKy5SXxzPT7FzCLdCP0N
ot1SMLDCRhRKnIkF4nkuxLz2gLbNSvEMpX/P0EX/lr5Gg2TkrDPLX0tCx8vMWXpr
sJJ0z7Z6RqKgP1tVMZqWcTEb8rF+hewu7K0+q1A2Q9MnFFfQRPrOe5MvFKB89qAl
KxUq74ECgYEA7rp39Iww/RoMPE1L0P8e1sD+mU9N8x4DOZsLK0V8xTwB+qB+BzEM
qs7DdsWLs1ze2G4B0xBRtRHF8xD2Vqf0GPHnr8xM+qYHXvC9x3D7LM1s7ZQd5o0M
q6B7aoJP/YqXhfWPjD7b0c8wx6SZxISbP9sN1qYr7YEq6b3zNWLy7m0CgYEA4E1I
lYODm4nidjXPyT6VV1Aj6hsH4rP5O0grVm1Yv7lqyqEQuVxCP6LN9qj5O7gkHLmY
lPDK/w1OdvN0E7J7K0EFrP1E2nPRo/qKMfISvlCHCgJbN+LLSxPJYMGE3sCJ+6FN
eG+bNxxvb+zMr1C4XdS5B6fJ0AvCIyfWbvzFRoECgYEAqwKvnXddJNiQm8qU7Pnf
tbqPl9HJtl9YCe+9fNWXE0OkVD8aDzwAPH1TnPjWQxoYJfM8LT+ki4g5R5k8U9he
uqvvKVxufE1CsNq0yCNSAJL9z0bHnLZ0vP2V7e8XgHT6VVb0I3J5SvGOh8zNHVpN
n3l6g3C+qNGb9d1tYVtLXL0CgYAZCX3Y2sDSSQVfNXOcZgPa9K/xAFPFHgPevmLl
PFM3A+LfWOSDKm3H/prcRF0R0yK8Bt0oN0I5f8R8YOJ1VYv7PBcqY/L2h5UGqLoC
hA7RJM0KhB8LmSBM8PhnvL6Fb4Q5hNnGkBZ7Vy1K2H4Y5e1H6Jhk0t5U1CJ/TDSz
FnzRAQKBgQCQV7/3YXOIgHOEr8RNCiQgZgN3YpxJ6R2jTNqobP7kPfCCB5N2BYEX
gm3dWLPzgD5E0vv+2VyudVJ0A7E2AQNnWyTi6NxiH3TQ5dCi0PBs/YbBCfvGk3Bv
YRqM8sYI+KBaE1Uxz0jL1Q8gvR8BQh3XM0k7O5a4CQk4C9xL0vY7YA==
-----END RSA PRIVATE KEY-----"""
    settings.github_api_base_url = "https://api.github.com"
    settings.github_webhook_secret = "test_webhook_secret"
    settings.github_clone_base_dir = "/tmp/ora-clones"
    return settings


# ── DB Model Tests ──────────────────────────────────────────────────────


def test_github_installation_model(db_session):
    """Test GithubInstallation model CRUD."""
    installation = GithubInstallation(
        id="inst-001",
        installation_id=12345,
        account_type="Organization",
        account_login="test-org",
        account_id=67890,
        avatar_url="https://avatars.githubusercontent.com/u/67890",
        status="active",
    )
    db_session.add(installation)
    db_session.commit()

    # Query
    result = db_session.query(GithubInstallation).filter_by(installation_id=12345).first()
    assert result is not None
    assert result.account_login == "test-org"
    assert result.account_type == "Organization"
    assert result.status == "active"


def test_github_repo_model(db_session):
    """Test GithubRepo model with FK to GithubInstallation."""
    # Create installation first
    installation = GithubInstallation(
        id="inst-001",
        installation_id=12345,
        account_type="Organization",
        account_login="test-org",
        account_id=67890,
    )
    db_session.add(installation)
    db_session.commit()

    # Create repo
    repo = GithubRepo(
        id="repo-001",
        installation_id="inst-001",
        repo_id=999,
        name="my-repo",
        full_name="test-org/my-repo",
        description="Test repository",
        html_url="https://github.com/test-org/my-repo",
        clone_url="https://github.com/test-org/my-repo.git",
        default_branch="main",
        language="Python",
        stars=42,
        is_private=False,
    )
    db_session.add(repo)
    db_session.commit()

    # Query
    result = db_session.query(GithubRepo).filter_by(repo_id=999).first()
    assert result is not None
    assert result.full_name == "test-org/my-repo"
    assert result.language == "Python"
    assert result.stars == 42


def test_project_model_source_types(db_session):
    """Test Project model with different source types."""
    # Local-only project
    local_project = Project(
        id="proj-001",
        name="LocalProject",
        source_type="local",
        local_path="/workspace/LocalProject",
        enabled=True,
    )

    # GitHub-only project (needs clone)
    github_only_project = Project(
        id="proj-002",
        name="GitHubOnlyProject",
        source_type="github_only",
        enabled=True,
    )

    db_session.add_all([local_project, github_only_project])
    db_session.commit()

    # Query
    local_result = db_session.query(Project).filter_by(source_type="local").first()
    assert local_result is not None
    assert local_result.local_path == "/workspace/LocalProject"

    github_result = db_session.query(Project).filter_by(source_type="github_only").first()
    assert github_result is not None
    assert github_result.local_path is None


def test_project_with_github_repo_link(db_session):
    """Test Project linked to GithubRepo."""
    # Setup installation + repo
    installation = GithubInstallation(
        id="inst-001",
        installation_id=12345,
        account_type="Organization",
        account_login="test-org",
        account_id=67890,
    )
    repo = GithubRepo(
        id="repo-001",
        installation_id="inst-001",
        repo_id=999,
        name="linked-repo",
        full_name="test-org/linked-repo",
        html_url="https://github.com/test-org/linked-repo",
        clone_url="https://github.com/test-org/linked-repo.git",
    )
    db_session.add_all([installation, repo])
    db_session.commit()

    # Create linked project
    project = Project(
        id="proj-003",
        name="linked-repo",
        source_type="github",
        local_path="/workspace/linked-repo",
        github_repo_id="repo-001",
        enabled=True,
    )
    db_session.add(project)
    db_session.commit()

    # Query
    result = db_session.query(Project).filter_by(source_type="github").first()
    assert result is not None
    assert result.github_repo_id == "repo-001"
    assert result.local_path is not None


# ── GitHub Client Tests ──────────────────────────────────────────────────


def test_github_client_init_validation():
    """Test GitHubAppClient requires app_id and private_key."""
    from ora_automation_api.github_client import GitHubAppClient

    settings = MagicMock()
    settings.github_app_id = ""
    settings.github_app_private_key = ""
    settings.github_api_base_url = "https://api.github.com"

    with pytest.raises(ValueError, match="GITHUB_APP_ID is required"):
        GitHubAppClient(settings)


def test_github_client_jwt_generation(mock_settings):
    """Test JWT generation for GitHub App authentication."""
    from ora_automation_api.github_client import GitHubAppClient

    client = GitHubAppClient(mock_settings)

    # Mock jwt.encode since we don't have a real RSA key
    with patch("ora_automation_api.github_client.jwt.encode") as mock_encode:
        mock_encode.return_value = "header.payload.signature"
        jwt_token = client._generate_jwt()

        # JWT should be a string with 3 parts separated by dots
        assert isinstance(jwt_token, str)
        parts = jwt_token.split(".")
        assert len(parts) == 3

        # Verify the call was made with correct params
        mock_encode.assert_called_once()
        call_args = mock_encode.call_args
        payload = call_args[0][0]
        assert "iat" in payload
        assert "exp" in payload
        assert payload["iss"] == "123456"


def test_webhook_signature_verification():
    """Test GitHub webhook signature verification."""
    from ora_automation_api.github_client import verify_webhook_signature

    secret = "test_secret"
    payload = b'{"action": "created"}'

    # Generate valid signature
    sig = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    valid_signature = f"sha256={sig}"

    # Test valid signature
    assert verify_webhook_signature(payload, valid_signature, secret) is True

    # Test invalid signature
    assert verify_webhook_signature(payload, "sha256=invalid", secret) is False

    # Test missing prefix
    assert verify_webhook_signature(payload, sig, secret) is False


@pytest.mark.asyncio(loop_scope="function")
async def test_github_client_list_repos(mock_settings):
    """Test listing repositories with mocked HTTP client."""
    from ora_automation_api.github_client import GitHubAppClient

    client = GitHubAppClient(mock_settings)

    # Mock HTTP responses
    mock_token_response = MagicMock()
    mock_token_response.json.return_value = {"token": "ghs_test_token"}
    mock_token_response.raise_for_status = MagicMock()

    mock_repos_response = MagicMock()
    mock_repos_response.json.return_value = {
        "repositories": [
            {
                "id": 123,
                "name": "test-repo",
                "full_name": "org/test-repo",
                "description": "A test repo",
                "html_url": "https://github.com/org/test-repo",
                "clone_url": "https://github.com/org/test-repo.git",
                "default_branch": "main",
                "language": "Python",
                "stargazers_count": 10,
                "private": False,
            }
        ]
    }
    mock_repos_response.raise_for_status = MagicMock()

    # Mock both jwt.encode and httpx.AsyncClient
    with patch("ora_automation_api.github_client.jwt.encode", return_value="mock.jwt.token"):
        with patch("ora_automation_api.github_client.httpx.AsyncClient") as MockAsyncClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_token_response
            mock_client_instance.get.return_value = mock_repos_response
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.__aexit__.return_value = None
            MockAsyncClient.return_value = mock_client_instance

            repos = await client.list_installation_repos(12345)

            assert len(repos) == 1
            assert repos[0].name == "test-repo"
            assert repos[0].full_name == "org/test-repo"
            assert repos[0].language == "Python"
            assert repos[0].stars == 10


# ── Cascade Delete Test ──────────────────────────────────────────────────


def test_installation_cascade_delete(db_session):
    """Test that deleting installation cascades to repos."""
    # Setup
    installation = GithubInstallation(
        id="inst-001",
        installation_id=12345,
        account_type="Organization",
        account_login="test-org",
        account_id=67890,
    )
    repo = GithubRepo(
        id="repo-001",
        installation_id="inst-001",
        repo_id=999,
        name="cascade-test",
        full_name="test-org/cascade-test",
        html_url="https://github.com/test-org/cascade-test",
        clone_url="https://github.com/test-org/cascade-test.git",
    )
    db_session.add_all([installation, repo])
    db_session.commit()

    # Verify repo exists
    assert db_session.query(GithubRepo).filter_by(id="repo-001").first() is not None

    # Delete installation
    db_session.delete(installation)
    db_session.commit()

    # Repo should be deleted due to CASCADE
    assert db_session.query(GithubRepo).filter_by(id="repo-001").first() is None


def test_project_github_repo_set_null(db_session):
    """Test that deleting GithubRepo sets Project.github_repo_id to NULL."""
    # Setup
    installation = GithubInstallation(
        id="inst-001",
        installation_id=12345,
        account_type="Organization",
        account_login="test-org",
        account_id=67890,
    )
    repo = GithubRepo(
        id="repo-001",
        installation_id="inst-001",
        repo_id=999,
        name="set-null-test",
        full_name="test-org/set-null-test",
        html_url="https://github.com/test-org/set-null-test",
        clone_url="https://github.com/test-org/set-null-test.git",
    )
    project = Project(
        id="proj-001",
        name="set-null-test",
        source_type="github",
        local_path="/workspace/set-null-test",
        github_repo_id="repo-001",
    )
    db_session.add_all([installation, repo, project])
    db_session.commit()

    # Verify project has repo link
    p = db_session.query(Project).filter_by(id="proj-001").first()
    assert p.github_repo_id == "repo-001"

    # Delete repo
    db_session.delete(repo)
    db_session.commit()

    # Refresh and check project still exists but github_repo_id is NULL
    db_session.expire_all()
    p = db_session.query(Project).filter_by(id="proj-001").first()
    assert p is not None
    assert p.github_repo_id is None
