"""On-demand Git clone service for GitHub repositories.

Provides shallow clone and pull functionality for analysis preparation.
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
import shutil
import time
from pathlib import Path

from .config import settings

logger = logging.getLogger(__name__)

# Lock file directory for clone operations
_LOCK_DIR: Path | None = None


def _get_lock_dir() -> Path:
    """Get or create the lock directory."""
    global _LOCK_DIR
    if _LOCK_DIR is None:
        _LOCK_DIR = settings.github_clone_base_dir / ".locks"
        _LOCK_DIR.mkdir(parents=True, exist_ok=True)
    return _LOCK_DIR


class CloneLock:
    """File-based lock for clone operations to prevent race conditions."""

    def __init__(self, full_name: str):
        self.lock_path = _get_lock_dir() / f"{full_name.replace('/', '_')}.lock"
        self.lock_file = None

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_file = open(self.lock_path, "w")
        fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lock_file:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
            self.lock_file.close()
        return False


async def shallow_clone(clone_url: str, target_path: Path, branch: str = "main") -> None:
    """Perform a shallow clone of a repository.

    Args:
        clone_url: Git clone URL.
        target_path: Target directory for the clone.
        branch: Branch to clone (default: main).

    Raises:
        RuntimeError: If clone fails.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "git", "clone",
        "--depth", "1",
        "--single-branch",
        "--branch", branch,
        clone_url,
        str(target_path),
    ]

    logger.info("Cloning %s to %s", clone_url, target_path)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        error_msg = stderr.decode()[:500] if stderr else "Unknown error"
        logger.error("Clone failed: %s", error_msg)
        raise RuntimeError(f"Clone failed: {error_msg}")

    logger.info("Successfully cloned %s", clone_url)


async def git_pull(repo_path: Path) -> bool:
    """Pull latest changes for an existing repository.

    Args:
        repo_path: Path to the repository.

    Returns:
        True if pull was successful.
    """
    if not (repo_path / ".git").exists():
        logger.warning("Not a git repository: %s", repo_path)
        return False

    cmd = ["git", "pull", "--ff-only"]

    logger.info("Pulling updates for %s", repo_path)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(repo_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.warning("Pull failed for %s: %s", repo_path, stderr.decode()[:200])
        return False

    logger.info("Successfully pulled %s", repo_path)
    return True


async def ensure_local_clone(
    clone_url: str,
    full_name: str,
    branch: str = "main",
    force_pull: bool = False,
) -> Path:
    """Ensure a repository is cloned locally, clone if needed.

    Uses file locking to prevent race conditions when multiple requests
    try to clone the same repository simultaneously.

    Args:
        clone_url: Git clone URL.
        full_name: Repository full name (owner/repo).
        branch: Branch to clone/pull.
        force_pull: If True, pull updates even if already cloned.

    Returns:
        Path to the local clone.

    Raises:
        RuntimeError: If clone fails.
    """
    clone_dir = settings.github_clone_base_dir / full_name

    # Use file lock to prevent race condition
    with CloneLock(full_name):
        # Re-check after acquiring lock (another process may have cloned)
        if clone_dir.exists() and (clone_dir / ".git").exists():
            if force_pull:
                await git_pull(clone_dir)
            return clone_dir

        # Clone to temp directory first, then rename atomically
        temp_dir = clone_dir.parent / f".{clone_dir.name}.tmp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

        try:
            await shallow_clone(clone_url, temp_dir, branch)
            # Atomic rename (on same filesystem)
            if clone_dir.exists():
                shutil.rmtree(clone_dir)
            temp_dir.rename(clone_dir)
        except Exception:
            # Cleanup temp on failure
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
            raise

    return clone_dir


def cleanup_old_clones(max_age_days: int = 7) -> int:
    """Remove clones that haven't been accessed recently.

    Args:
        max_age_days: Maximum age in days before removal.

    Returns:
        Number of directories removed.
    """
    clone_base = settings.github_clone_base_dir
    if not clone_base.exists():
        return 0

    cutoff = time.time() - (max_age_days * 86400)
    removed = 0

    # Iterate through owner directories
    for owner_dir in clone_base.iterdir():
        if not owner_dir.is_dir():
            continue

        # Iterate through repo directories
        for repo_dir in owner_dir.iterdir():
            if not repo_dir.is_dir():
                continue

            try:
                # Check last access time
                stat = repo_dir.stat()
                if stat.st_atime < cutoff:
                    logger.info("Removing old clone: %s", repo_dir)
                    shutil.rmtree(repo_dir)
                    removed += 1
            except (OSError, PermissionError) as e:
                logger.warning("Failed to check/remove %s: %s", repo_dir, e)

        # Remove empty owner directories
        try:
            if owner_dir.is_dir() and not any(owner_dir.iterdir()):
                owner_dir.rmdir()
        except OSError:
            pass

    logger.info("Cleaned up %d old clones", removed)
    return removed


def get_clone_path(full_name: str) -> Path:
    """Get the local path for a repository clone.

    Args:
        full_name: Repository full name (owner/repo).

    Returns:
        Path where the clone would be/is located.
    """
    return settings.github_clone_base_dir / full_name


def is_cloned(full_name: str) -> bool:
    """Check if a repository is already cloned locally.

    Args:
        full_name: Repository full name (owner/repo).

    Returns:
        True if the clone exists.
    """
    clone_path = get_clone_path(full_name)
    return clone_path.exists() and (clone_path / ".git").exists()
