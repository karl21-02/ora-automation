"""Notion REST API client with retry and error handling."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .config import settings

logger = logging.getLogger(__name__)

NOTION_BASE_URL = "https://api.notion.com/v1"


class NotionAPIError(Exception):
    """Raised when the Notion API returns an error."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        super().__init__(f"Notion API {status_code} ({code}): {message}")


class NotionClient:
    """Low-level Notion REST API wrapper with automatic retry.

    Supports use as a context manager to ensure the HTTP session is closed::

        with NotionClient() as client:
            client.create_page(...)
    """

    def __init__(
        self,
        token: str | None = None,
        api_version: str | None = None,
    ) -> None:
        self.token = token or settings.notion_api_token
        self.api_version = api_version or settings.notion_api_version
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": self.api_version,
                "Content-Type": "application/json",
            }
        )

    def __enter__(self) -> "NotionClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()

    def _request(
        self,
        method: str,
        path: str,
        json_body: dict | None = None,
        max_retries: int = 3,
    ) -> dict:
        url = f"{NOTION_BASE_URL}{path}"
        last_exc: Exception | None = None

        for attempt in range(max_retries):
            try:
                resp = self._session.request(method, url, json=json_body, timeout=30)
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise NotionAPIError(0, "connection_error", str(exc)) from exc

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 1))
                logger.warning("Notion 429 rate-limited, retrying after %.1fs", retry_after)
                if attempt < max_retries - 1:
                    time.sleep(retry_after)
                    continue

            if resp.status_code >= 500:
                logger.warning("Notion %d server error, retrying (attempt %d)", resp.status_code, attempt + 1)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue

            if resp.status_code >= 400:
                body = resp.json() if resp.content else {}
                raise NotionAPIError(
                    resp.status_code,
                    body.get("code", "unknown"),
                    body.get("message", resp.text),
                )

            return resp.json()

        if last_exc:
            raise NotionAPIError(0, "max_retries", str(last_exc)) from last_exc
        raise NotionAPIError(0, "max_retries", "max retries exceeded")

    # ── High-level methods ────────────────────────────────────────────

    def create_page(
        self,
        parent: dict[str, Any],
        properties: dict[str, Any],
        children: list[dict] | None = None,
        icon: dict | None = None,
    ) -> dict:
        body: dict[str, Any] = {"parent": parent, "properties": properties}
        if children:
            body["children"] = children[:100]
        if icon:
            body["icon"] = icon
        return self._request("POST", "/pages", body)

    def update_page(self, page_id: str, properties: dict[str, Any]) -> dict:
        return self._request("PATCH", f"/pages/{page_id}", {"properties": properties})

    def append_blocks(self, block_id: str, children: list[dict]) -> dict:
        return self._request("PATCH", f"/blocks/{block_id}/children", {"children": children[:100]})

    def create_database(
        self,
        parent: dict[str, Any],
        title: list[dict],
        properties: dict[str, Any],
        icon: dict | None = None,
    ) -> dict:
        body: dict[str, Any] = {
            "parent": parent,
            "title": title,
            "properties": properties,
        }
        if icon:
            body["icon"] = icon
        return self._request("POST", "/databases", body)

    def query_database(
        self,
        database_id: str,
        filter_obj: dict | None = None,
        sorts: list[dict] | None = None,
    ) -> dict:
        body: dict[str, Any] = {}
        if filter_obj:
            body["filter"] = filter_obj
        if sorts:
            body["sorts"] = sorts
        return self._request("POST", f"/databases/{database_id}/query", body)

    def check_connection(self) -> dict:
        return self._request("GET", "/users/me")
