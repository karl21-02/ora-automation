"""Tests for on-demand clone service."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ora_automation_api.clone_service import (
    cleanup_old_clones,
    get_clone_path,
    is_cloned,
)


# ── Helper Function Tests ──────────────────────────────────────────────


def test_get_clone_path():
    """Test get_clone_path returns correct path."""
    with patch("ora_automation_api.clone_service.settings") as mock_settings:
        mock_settings.github_clone_base_dir = Path("/tmp/ora-clones")
        path = get_clone_path("owner/repo")
        assert path == Path("/tmp/ora-clones/owner/repo")


def test_is_cloned_true():
    """Test is_cloned returns True for existing clone."""
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_path = Path(tmpdir) / "owner" / "repo"
        clone_path.mkdir(parents=True)
        (clone_path / ".git").mkdir()

        with patch("ora_automation_api.clone_service.settings") as mock_settings:
            mock_settings.github_clone_base_dir = Path(tmpdir)
            assert is_cloned("owner/repo") is True


def test_is_cloned_false_no_dir():
    """Test is_cloned returns False when directory doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("ora_automation_api.clone_service.settings") as mock_settings:
            mock_settings.github_clone_base_dir = Path(tmpdir)
            assert is_cloned("owner/repo") is False


def test_is_cloned_false_no_git():
    """Test is_cloned returns False when .git doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        clone_path = Path(tmpdir) / "owner" / "repo"
        clone_path.mkdir(parents=True)
        # No .git directory

        with patch("ora_automation_api.clone_service.settings") as mock_settings:
            mock_settings.github_clone_base_dir = Path(tmpdir)
            assert is_cloned("owner/repo") is False


# ── Cleanup Tests ──────────────────────────────────────────────────────


def test_cleanup_old_clones_empty():
    """Test cleanup with no clones."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("ora_automation_api.clone_service.settings") as mock_settings:
            mock_settings.github_clone_base_dir = Path(tmpdir)
            removed = cleanup_old_clones(max_age_days=7)
            assert removed == 0


def test_cleanup_old_clones_nonexistent():
    """Test cleanup when base dir doesn't exist."""
    with patch("ora_automation_api.clone_service.settings") as mock_settings:
        mock_settings.github_clone_base_dir = Path("/nonexistent/path")
        removed = cleanup_old_clones(max_age_days=7)
        assert removed == 0


# ── Async Clone Tests ──────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="function")
async def test_shallow_clone_success():
    """Test shallow_clone with mocked subprocess."""
    from ora_automation_api.clone_service import shallow_clone

    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "owner" / "repo"

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            await shallow_clone("https://github.com/owner/repo.git", target)

        # Verify subprocess was called
        mock_proc.communicate.assert_called_once()


@pytest.mark.asyncio(loop_scope="function")
async def test_shallow_clone_failure():
    """Test shallow_clone raises on failure."""
    from ora_automation_api.clone_service import shallow_clone

    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "owner" / "repo"

        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"Clone failed"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="Clone failed"):
                await shallow_clone("https://github.com/owner/repo.git", target)


@pytest.mark.asyncio(loop_scope="function")
async def test_git_pull_success():
    """Test git_pull with mocked subprocess."""
    from ora_automation_api.clone_service import git_pull

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        (repo_path / ".git").mkdir()

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await git_pull(repo_path)

        assert result is True


@pytest.mark.asyncio(loop_scope="function")
async def test_git_pull_not_git_repo():
    """Test git_pull returns False for non-git directory."""
    from ora_automation_api.clone_service import git_pull

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        # No .git directory

        result = await git_pull(repo_path)
        assert result is False


@pytest.mark.asyncio(loop_scope="function")
async def test_ensure_local_clone_new():
    """Test ensure_local_clone clones new repo."""
    from ora_automation_api.clone_service import ensure_local_clone

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("ora_automation_api.clone_service.settings") as mock_settings:
            mock_settings.github_clone_base_dir = Path(tmpdir)

            # Mock shallow_clone to create the temp directory (simulating git clone)
            async def mock_shallow_clone(clone_url, target_path, branch="main"):
                target_path.mkdir(parents=True, exist_ok=True)
                (target_path / ".git").mkdir()

            with patch("ora_automation_api.clone_service.shallow_clone", side_effect=mock_shallow_clone):
                path = await ensure_local_clone(
                    "https://github.com/owner/repo.git",
                    "owner/repo",
                )

            assert path == Path(tmpdir) / "owner" / "repo"
            assert (path / ".git").exists()


@pytest.mark.asyncio(loop_scope="function")
async def test_ensure_local_clone_existing():
    """Test ensure_local_clone returns existing clone."""
    from ora_automation_api.clone_service import ensure_local_clone

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create existing clone
        clone_path = Path(tmpdir) / "owner" / "repo"
        clone_path.mkdir(parents=True)
        (clone_path / ".git").mkdir()

        with patch("ora_automation_api.clone_service.settings") as mock_settings:
            mock_settings.github_clone_base_dir = Path(tmpdir)

            # Should not call subprocess
            with patch("asyncio.create_subprocess_exec") as mock_exec:
                path = await ensure_local_clone(
                    "https://github.com/owner/repo.git",
                    "owner/repo",
                )

                mock_exec.assert_not_called()

            assert path == clone_path
