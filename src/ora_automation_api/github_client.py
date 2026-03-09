"""GitHub App API client for Ora Automation.

Handles GitHub App authentication (JWT + Installation tokens) and API calls.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx
import jwt

if TYPE_CHECKING:
    from .config import Settings

logger = logging.getLogger(__name__)


@dataclass
class GitHubRepo:
    """Repository data from GitHub API."""

    repo_id: int
    name: str
    full_name: str
    description: str | None
    html_url: str
    clone_url: str
    default_branch: str
    language: str | None
    stars: int
    is_private: bool


@dataclass
class GitHubInstallationInfo:
    """Installation data from GitHub webhook or API."""

    installation_id: int
    account_type: str  # "Organization" or "User"
    account_login: str
    account_id: int
    avatar_url: str | None


class GitHubAppClient:
    """GitHub App API client.

    Usage:
        client = GitHubAppClient(settings)
        token = await client.get_installation_token(installation_id)
        repos = await client.list_installation_repos(installation_id)
    """

    def __init__(self, settings: Settings) -> None:
        self.app_id = settings.github_app_id
        self.private_key = settings.github_app_private_key
        self.base_url = settings.github_api_base_url.rstrip("/")
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate that required config is present."""
        if not self.app_id:
            raise ValueError("GITHUB_APP_ID is required")
        if not self.private_key:
            raise ValueError("GITHUB_APP_PRIVATE_KEY is required")

    def _generate_jwt(self) -> str:
        """Generate JWT for App authentication (10 minute expiry)."""
        now = int(time.time())
        payload = {
            "iat": now - 60,  # Issued 1 minute ago (clock skew tolerance)
            "exp": now + 600,  # Expires in 10 minutes
            "iss": self.app_id,
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def _app_headers(self) -> dict[str, str]:
        """Headers for App-level authentication."""
        return {
            "Authorization": f"Bearer {self._generate_jwt()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _installation_headers(self, token: str) -> dict[str, str]:
        """Headers for Installation-level authentication."""
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def get_installation_token(self, installation_id: int) -> str:
        """Get an installation access token (1 hour expiry).

        Args:
            installation_id: The GitHub App installation ID.

        Returns:
            Access token string.
        """
        url = f"{self.base_url}/app/installations/{installation_id}/access_tokens"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=self._app_headers())
            resp.raise_for_status()
            data = resp.json()
            return data["token"]

    async def list_installations(self) -> list[GitHubInstallationInfo]:
        """List all installations of this GitHub App.

        Returns:
            List of installation info.
        """
        url = f"{self.base_url}/app/installations"
        installations: list[GitHubInstallationInfo] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            page = 1
            while True:
                resp = await client.get(
                    url,
                    headers=self._app_headers(),
                    params={"per_page": 100, "page": page},
                )
                resp.raise_for_status()
                data = resp.json()

                for inst in data:
                    account = inst.get("account", {})
                    installations.append(
                        GitHubInstallationInfo(
                            installation_id=inst["id"],
                            account_type=account.get("type", "User"),
                            account_login=account.get("login", ""),
                            account_id=account.get("id", 0),
                            avatar_url=account.get("avatar_url"),
                        )
                    )

                if len(data) < 100:
                    break
                page += 1

        return installations

    async def list_installation_repos(self, installation_id: int) -> list[GitHubRepo]:
        """List all repositories accessible by an installation.

        Args:
            installation_id: The GitHub App installation ID.

        Returns:
            List of repository data.
        """
        token = await self.get_installation_token(installation_id)
        url = f"{self.base_url}/installation/repositories"
        repos: list[GitHubRepo] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            page = 1
            while True:
                resp = await client.get(
                    url,
                    headers=self._installation_headers(token),
                    params={"per_page": 100, "page": page},
                )
                resp.raise_for_status()
                data = resp.json()

                for repo in data.get("repositories", []):
                    repos.append(
                        GitHubRepo(
                            repo_id=repo["id"],
                            name=repo["name"],
                            full_name=repo["full_name"],
                            description=repo.get("description"),
                            html_url=repo["html_url"],
                            clone_url=repo["clone_url"],
                            default_branch=repo.get("default_branch", "main"),
                            language=repo.get("language"),
                            stars=repo.get("stargazers_count", 0),
                            is_private=repo.get("private", False),
                        )
                    )

                if len(data.get("repositories", [])) < 100:
                    break
                page += 1

        return repos

    async def get_repository(self, installation_id: int, owner: str, repo: str) -> GitHubRepo:
        """Get a single repository by owner/repo.

        Args:
            installation_id: The GitHub App installation ID.
            owner: Repository owner (user or org).
            repo: Repository name.

        Returns:
            Repository data.
        """
        token = await self.get_installation_token(installation_id)
        url = f"{self.base_url}/repos/{owner}/{repo}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers=self._installation_headers(token))
            resp.raise_for_status()
            data = resp.json()

            return GitHubRepo(
                repo_id=data["id"],
                name=data["name"],
                full_name=data["full_name"],
                description=data.get("description"),
                html_url=data["html_url"],
                clone_url=data["clone_url"],
                default_branch=data.get("default_branch", "main"),
                language=data.get("language"),
                stars=data.get("stargazers_count", 0),
                is_private=data.get("private", False),
            )


def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook signature.

    Args:
        payload: Raw request body bytes.
        signature: X-Hub-Signature-256 header value.
        secret: Webhook secret configured in GitHub App.

    Returns:
        True if signature is valid.
    """
    import hmac
    import hashlib

    if not signature.startswith("sha256="):
        return False

    expected_sig = signature[7:]  # Remove "sha256=" prefix
    computed_sig = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_sig, computed_sig)
