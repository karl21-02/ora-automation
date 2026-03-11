"""Extended research sources - GitHub, HuggingFace, Tech Blogs.

All relevance filtering and deduplication is done by LLM (no hardcoded rules).
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlencode
from urllib.request import Request, urlopen

from .config import LLM_DELIBERATION_TIMEOUT_SECONDS
from .llm_client import run_llm_command

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Environment variables
GITHUB_SEARCH_ENABLED_ENV = "ORA_RD_GITHUB_SEARCH_ENABLED"
GITHUB_TOKEN_ENV = "GITHUB_TOKEN"
HUGGINGFACE_SEARCH_ENABLED_ENV = "ORA_RD_HUGGINGFACE_SEARCH_ENABLED"
HUGGINGFACE_TOKEN_ENV = "HUGGINGFACE_TOKEN"

# API endpoints
GITHUB_SEARCH_API_URL = "https://api.github.com/search/repositories"
GITHUB_CODE_SEARCH_API_URL = "https://api.github.com/search/code"
HUGGINGFACE_MODELS_API_URL = "https://huggingface.co/api/models"
HUGGINGFACE_DATASETS_API_URL = "https://huggingface.co/api/datasets"

# Defaults
DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_RESULTS = 10

# LLM command for source integration
LLM_RESEARCH_INTEGRATION_CMD_ENV = "ORA_LLM_RESEARCH_INTEGRATION_CMD"


def _read_bool_env(key: str, default: bool = True) -> bool:
    """Read boolean from environment."""
    val = os.getenv(key, "").strip().lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_RETRY_STATUS_CODES = {429, 503}
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY = 0.5


def _request_json(
    url: str,
    timeout: float = DEFAULT_TIMEOUT,
    headers: dict[str, str] | None = None,
    max_bytes: int = 524288,
) -> dict:
    """Make HTTP request and parse JSON response."""
    default_headers = {
        "User-Agent": "OraResearchOrchestrator/1.0",
        "Accept": "application/json",
    }
    if headers:
        default_headers.update(headers)

    last_exc: Exception | None = None
    for attempt in range(_RETRY_MAX_ATTEMPTS):
        try:
            req = Request(url=url, headers=default_headers)
            with urlopen(req, timeout=timeout) as response:
                data = response.read(max_bytes)
                return json.loads(data)
        except HTTPError as exc:
            last_exc = exc
            if exc.code in _RETRY_STATUS_CODES and attempt < _RETRY_MAX_ATTEMPTS - 1:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.info("HTTP %d, retrying in %.1fs", exc.code, delay)
                time.sleep(delay)
                continue
            raise
        except (URLError, json.JSONDecodeError) as exc:
            last_exc = exc
            raise
    raise last_exc  # type: ignore


# ---------------------------------------------------------------------------
# GitHub Search
# ---------------------------------------------------------------------------

def search_github_repos(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """Search GitHub repositories.

    Args:
        query: Search query
        max_results: Maximum results to return
        timeout: Request timeout

    Returns:
        List of repo info dicts
    """
    if not _read_bool_env(GITHUB_SEARCH_ENABLED_ENV, default=True):
        return []

    token = os.getenv(GITHUB_TOKEN_ENV, "").strip()
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    params = urlencode({
        "q": query,
        "sort": "stars",
        "order": "desc",
        "per_page": str(min(max_results, 30)),
    })
    url = f"{GITHUB_SEARCH_API_URL}?{params}"

    try:
        response = _request_json(url, timeout=timeout, headers=headers)
    except Exception as exc:
        logger.warning("GitHub search failed: %s", exc)
        return [{
            "source": "github",
            "error": str(exc),
            "query": query,
        }]

    results: list[dict[str, Any]] = []
    items = response.get("items", [])

    for item in items[:max_results]:
        results.append({
            "source": "github",
            "source_type": "repository",
            "id": item.get("full_name", ""),
            "title": item.get("name", ""),
            "description": (item.get("description") or "")[:500],
            "url": item.get("html_url", ""),
            "stars": item.get("stargazers_count", 0),
            "forks": item.get("forks_count", 0),
            "language": item.get("language", ""),
            "updated_at": item.get("updated_at", ""),
            "topics": item.get("topics", []),
        })

    return results


def search_github_trending(
    language: str | None = None,
    since: str = "weekly",
) -> list[dict[str, Any]]:
    """Get trending GitHub repositories.

    Note: GitHub doesn't have official trending API, so we use search
    with recent activity and high stars.
    """
    if not _read_bool_env(GITHUB_SEARCH_ENABLED_ENV, default=True):
        return []

    # Build query for recently active, highly starred repos
    query_parts = ["stars:>100", "pushed:>2024-01-01"]
    if language:
        query_parts.append(f"language:{language}")

    query = " ".join(query_parts)
    return search_github_repos(query, max_results=10)


# ---------------------------------------------------------------------------
# HuggingFace Search
# ---------------------------------------------------------------------------

def search_huggingface_models(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """Search HuggingFace models.

    Args:
        query: Search query
        max_results: Maximum results
        timeout: Request timeout

    Returns:
        List of model info dicts
    """
    if not _read_bool_env(HUGGINGFACE_SEARCH_ENABLED_ENV, default=True):
        return []

    token = os.getenv(HUGGINGFACE_TOKEN_ENV, "").strip()
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params = urlencode({
        "search": query,
        "limit": str(min(max_results, 50)),
        "sort": "downloads",
        "direction": "-1",
    })
    url = f"{HUGGINGFACE_MODELS_API_URL}?{params}"

    try:
        response = _request_json(url, timeout=timeout, headers=headers)
    except Exception as exc:
        logger.warning("HuggingFace model search failed: %s", exc)
        return [{
            "source": "huggingface",
            "source_type": "model",
            "error": str(exc),
            "query": query,
        }]

    results: list[dict[str, Any]] = []

    # Response is a list directly
    items = response if isinstance(response, list) else []

    for item in items[:max_results]:
        model_id = item.get("modelId", item.get("id", ""))
        results.append({
            "source": "huggingface",
            "source_type": "model",
            "id": model_id,
            "title": model_id.split("/")[-1] if "/" in model_id else model_id,
            "author": model_id.split("/")[0] if "/" in model_id else "",
            "url": f"https://huggingface.co/{model_id}",
            "downloads": item.get("downloads", 0),
            "likes": item.get("likes", 0),
            "pipeline_tag": item.get("pipeline_tag", ""),
            "tags": item.get("tags", [])[:10],
            "updated_at": item.get("lastModified", ""),
        })

    return results


def search_huggingface_datasets(
    query: str,
    max_results: int = DEFAULT_MAX_RESULTS,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    """Search HuggingFace datasets."""
    if not _read_bool_env(HUGGINGFACE_SEARCH_ENABLED_ENV, default=True):
        return []

    token = os.getenv(HUGGINGFACE_TOKEN_ENV, "").strip()
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    params = urlencode({
        "search": query,
        "limit": str(min(max_results, 50)),
        "sort": "downloads",
        "direction": "-1",
    })
    url = f"{HUGGINGFACE_DATASETS_API_URL}?{params}"

    try:
        response = _request_json(url, timeout=timeout, headers=headers)
    except Exception as exc:
        logger.warning("HuggingFace dataset search failed: %s", exc)
        return [{
            "source": "huggingface",
            "source_type": "dataset",
            "error": str(exc),
        }]

    results: list[dict[str, Any]] = []
    items = response if isinstance(response, list) else []

    for item in items[:max_results]:
        dataset_id = item.get("id", "")
        results.append({
            "source": "huggingface",
            "source_type": "dataset",
            "id": dataset_id,
            "title": dataset_id.split("/")[-1] if "/" in dataset_id else dataset_id,
            "author": dataset_id.split("/")[0] if "/" in dataset_id else "",
            "url": f"https://huggingface.co/datasets/{dataset_id}",
            "downloads": item.get("downloads", 0),
            "likes": item.get("likes", 0),
            "tags": item.get("tags", [])[:10],
        })

    return results


# ---------------------------------------------------------------------------
# Combined Search
# ---------------------------------------------------------------------------

def search_all_extended_sources(
    query: str,
    max_results_per_source: int = 5,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, list[dict[str, Any]]]:
    """Search all extended sources (GitHub, HuggingFace).

    Args:
        query: Search query
        max_results_per_source: Max results per source
        timeout: Request timeout

    Returns:
        Dict mapping source name to results list
    """
    results: dict[str, list[dict[str, Any]]] = {}

    # GitHub repos
    results["github_repos"] = search_github_repos(
        query=query,
        max_results=max_results_per_source,
        timeout=timeout,
    )

    # HuggingFace models
    results["huggingface_models"] = search_huggingface_models(
        query=query,
        max_results=max_results_per_source,
        timeout=timeout,
    )

    # HuggingFace datasets
    results["huggingface_datasets"] = search_huggingface_datasets(
        query=query,
        max_results=max_results_per_source,
        timeout=timeout,
    )

    return results


# ---------------------------------------------------------------------------
# LLM-based Source Integration (No hardcoded rules)
# ---------------------------------------------------------------------------

def integrate_research_sources(
    academic_sources: list[dict[str, Any]],
    extended_sources: dict[str, list[dict[str, Any]]],
    topic_name: str,
    command: str | None = None,
    timeout: float = LLM_DELIBERATION_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Use LLM to integrate and deduplicate research sources.

    All relevance scoring and deduplication is done by LLM.
    No hardcoded rules.

    Args:
        academic_sources: ArXiv, Crossref, etc. results
        extended_sources: GitHub, HuggingFace results
        topic_name: Topic being researched
        command: LLM command override
        timeout: LLM timeout

    Returns:
        Integrated results with LLM-assigned relevance scores
    """
    resolved_cmd = command
    if not resolved_cmd:
        resolved_cmd = os.getenv(LLM_RESEARCH_INTEGRATION_CMD_ENV, "").strip() or None

    # Flatten extended sources for payload
    extended_flat: list[dict] = []
    for source_name, items in extended_sources.items():
        for item in items:
            item["source_category"] = source_name
            extended_flat.append(item)

    payload = {
        "version": "research-integration-v1",
        "instructions": {
            "task": (
                "연구 소스들을 분석하고 통합하세요. "
                "학술 논문과 실용적 구현체(GitHub, HuggingFace)를 연결하세요."
            ),
            "deduplication": (
                "같은 연구/프로젝트를 다른 소스에서 발견한 경우 하나로 통합하세요. "
                "예: ArXiv 논문과 해당 논문의 GitHub 구현체"
            ),
            "relevance_scoring": (
                "각 소스의 토픽 관련성을 0.0~1.0으로 평가하세요. "
                "기준: 직접 관련(0.8+), 간접 관련(0.5-0.8), 낮은 관련(0.5 미만)"
            ),
            "insights": (
                "소스들을 종합한 핵심 인사이트를 3-5개 도출하세요. "
                "학술 트렌드 + 실무 적용 현황을 연결하세요."
            ),
        },
        "output_contract": {
            "integrated_sources": [
                {
                    "id": "unique identifier",
                    "title": "string",
                    "url": "string",
                    "source_type": "arxiv|github|huggingface|crossref|...",
                    "relevance_score": "0.0~1.0",
                    "related_sources": ["ids of related items"],
                    "summary": "brief description",
                }
            ],
            "duplicates_merged": [
                {"kept": "id", "merged": ["ids"]}
            ],
            "insights": [
                {"insight": "string", "supporting_sources": ["ids"]}
            ],
            "topic_coverage": {
                "academic": "0.0~1.0 how well academic sources cover topic",
                "practical": "0.0~1.0 how well practical sources cover topic",
                "gap_analysis": "string describing gaps",
            },
        },
        "topic": topic_name,
        "academic_sources": academic_sources[:20],  # Limit for prompt size
        "extended_sources": extended_flat[:20],
    }

    result = run_llm_command(
        payload=payload,
        command=resolved_cmd,
        timeout=timeout,
    )

    if result.status != "ok":
        # Return raw sources without integration
        return {
            "integrated_sources": academic_sources + extended_flat,
            "duplicates_merged": [],
            "insights": [],
            "topic_coverage": {
                "academic": 0.5,
                "practical": 0.5,
                "gap_analysis": "LLM integration failed, showing raw results",
            },
            "integration_status": "fallback",
        }

    response = result.parsed
    response["integration_status"] = "ok"
    return response


def build_comprehensive_research(
    topic_name: str,
    keywords: list[str],
    academic_sources: list[dict[str, Any]],
    max_extended_per_source: int = 5,
    command: str | None = None,
    timeout: float = LLM_DELIBERATION_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Build comprehensive research combining academic + extended sources.

    Args:
        topic_name: Topic being researched
        keywords: Search keywords
        academic_sources: Already-fetched academic sources
        max_extended_per_source: Max results per extended source
        command: LLM command override
        timeout: LLM timeout

    Returns:
        Comprehensive research results with LLM integration
    """
    # Build search query from topic and keywords
    query_parts = [topic_name] + keywords[:5]
    search_query = " ".join(query_parts)

    # Fetch extended sources
    extended_sources = search_all_extended_sources(
        query=search_query,
        max_results_per_source=max_extended_per_source,
    )

    # Integrate with LLM
    integrated = integrate_research_sources(
        academic_sources=academic_sources,
        extended_sources=extended_sources,
        topic_name=topic_name,
        command=command,
        timeout=timeout,
    )

    return {
        "topic": topic_name,
        "keywords": keywords,
        "raw_academic_count": len(academic_sources),
        "raw_extended_counts": {
            k: len(v) for k, v in extended_sources.items()
        },
        "integration": integrated,
    }
