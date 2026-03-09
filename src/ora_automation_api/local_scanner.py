"""Local workspace scanner for Git repositories.

Scans a directory for Git repos and extracts metadata (remote URL, language).
"""

from __future__ import annotations

import configparser
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_git_remote(repo_path: Path) -> str | None:
    """Extract origin remote URL from .git/config.

    Args:
        repo_path: Path to the repository root.

    Returns:
        Remote URL string or None if not found.
    """
    config_path = repo_path / ".git" / "config"
    if not config_path.exists():
        return None

    config = configparser.ConfigParser()
    try:
        config.read(config_path)
        return config.get('remote "origin"', "url")
    except (configparser.NoSectionError, configparser.NoOptionError):
        return None
    except Exception as e:
        logger.warning("Failed to parse git config at %s: %s", config_path, e)
        return None


def detect_primary_language(repo_path: Path) -> str | None:
    """Detect the primary programming language of a repository.

    Args:
        repo_path: Path to the repository root.

    Returns:
        Language name or None if not detected.
    """
    extensions = {
        ".py": "Python",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".kt": "Kotlin",
        ".swift": "Swift",
        ".rb": "Ruby",
        ".php": "PHP",
        ".cs": "C#",
        ".cpp": "C++",
        ".c": "C",
    }

    counts: dict[str, int] = {}

    # Only scan top-level src directories to avoid node_modules, venv, etc.
    scan_dirs = [repo_path]
    for subdir in ["src", "lib", "app", "pkg", "cmd"]:
        candidate = repo_path / subdir
        if candidate.is_dir():
            scan_dirs.append(candidate)

    for scan_dir in scan_dirs:
        for ext, lang in extensions.items():
            try:
                # Use rglob but limit depth implicitly by checking patterns
                count = sum(1 for _ in scan_dir.rglob(f"*{ext}"))
                if count > 0:
                    counts[lang] = counts.get(lang, 0) + count
            except PermissionError:
                continue

    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


def normalize_github_url(url: str) -> str:
    """Normalize GitHub URL to a canonical form for comparison.

    Converts various GitHub URL formats to: github.com/owner/repo

    Examples:
        git@github.com:owner/repo.git -> github.com/owner/repo
        https://github.com/owner/repo.git -> github.com/owner/repo
        https://github.com/owner/repo -> github.com/owner/repo

    Args:
        url: Git remote URL in any format.

    Returns:
        Normalized URL string (lowercase, no protocol, no .git suffix).
    """
    if not url:
        return ""

    normalized = url.strip()

    # SSH format: git@github.com:owner/repo.git
    if normalized.startswith("git@github.com:"):
        normalized = normalized.replace("git@github.com:", "github.com/")

    # HTTPS format: https://github.com/owner/repo.git
    normalized = normalized.replace("https://github.com/", "github.com/")
    normalized = normalized.replace("http://github.com/", "github.com/")

    # Remove .git suffix
    if normalized.endswith(".git"):
        normalized = normalized[:-4]

    # Remove trailing slash
    normalized = normalized.rstrip("/")

    return normalized.lower()


def is_github_url(url: str | None) -> bool:
    """Check if a URL is a GitHub repository URL.

    Args:
        url: Git remote URL.

    Returns:
        True if the URL points to GitHub.
    """
    if not url:
        return False
    return "github.com" in url.lower()


def scan_local_workspace(workspace_path: str | Path) -> list[dict]:
    """Scan a workspace directory for Git repositories.

    Args:
        workspace_path: Path to the workspace root directory.

    Returns:
        List of dicts with repo info: name, path, remote_url, language.
    """
    workspace = Path(workspace_path)
    if not workspace.is_dir():
        logger.warning("Workspace path does not exist: %s", workspace_path)
        return []

    repos: list[dict] = []

    for item in workspace.iterdir():
        if not item.is_dir():
            continue

        # Skip hidden directories
        if item.name.startswith("."):
            continue

        git_dir = item / ".git"
        if not git_dir.exists():
            continue

        remote_url = extract_git_remote(item)
        language = detect_primary_language(item)

        repos.append({
            "name": item.name,
            "path": str(item.absolute()),
            "remote_url": remote_url,
            "language": language,
        })

    logger.info("Scanned %d repos in %s", len(repos), workspace_path)
    return repos
