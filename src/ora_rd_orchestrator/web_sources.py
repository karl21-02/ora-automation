"""Web search client: Google Scholar via Scrapling."""
from __future__ import annotations

import re
from urllib.parse import quote_plus, urlencode

from .config import (
    WEB_SEARCH_BASE_URL,
    WEB_SEARCH_DEFAULT_MAX_RESULTS,
    WEB_SEARCH_ENABLED_ENV,
    WEB_SEARCH_PROVIDER,
    WEB_SEARCH_TIMEOUT_SECONDS,
    _read_bool_env,
    _read_float_env,
    _read_int_env,
)


_cached_web_env: dict[str, object] = {}


def _web_search_enabled() -> bool:
    key = "enabled"
    if key not in _cached_web_env:
        _cached_web_env[key] = _read_bool_env(WEB_SEARCH_ENABLED_ENV, default=False)
    return _cached_web_env[key]


def _web_search_limit() -> int:
    key = "limit"
    if key not in _cached_web_env:
        _cached_web_env[key] = _read_int_env(
            "ORA_RD_RESEARCH_WEB_SEARCH_MAX_RESULTS",
            WEB_SEARCH_DEFAULT_MAX_RESULTS,
        )
    return _cached_web_env[key]


def _web_search_timeout() -> float:
    key = "timeout"
    if key not in _cached_web_env:
        _cached_web_env[key] = _read_float_env(
            "ORA_RD_RESEARCH_WEB_SEARCH_TIMEOUT",
            WEB_SEARCH_TIMEOUT_SECONDS,
        )
    return _cached_web_env[key]


def _scholar_query_expression(topic_name: str, keywords: list[str]) -> str:
    terms = [topic_name]
    terms.extend(keywords[:4])
    return " ".join(t.strip() for t in terms if isinstance(t, str) and t.strip())


_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _parse_scholar_results(page: object, max_results: int) -> list[dict[str, str]]:
    """Parse Google Scholar results from a Scrapling page object."""
    entries: list[dict[str, str]] = []
    blocks = page.css(".gs_r.gs_or.gs_scl")
    for block in blocks[:max_results]:
        title_el = block.css_first(".gs_rt a")
        if title_el is None:
            continue
        title = (title_el.text or "").strip()
        url = (title_el.attrib.get("href") or "").strip()
        if not title or not url:
            continue

        snippet = ""
        snippet_el = block.css_first(".gs_rs")
        if snippet_el is not None:
            snippet = (snippet_el.text or "").strip()[:300]

        published = ""
        meta_el = block.css_first(".gs_a")
        if meta_el is not None:
            meta_text = meta_el.text or ""
            year_match = _YEAR_RE.search(meta_text)
            if year_match:
                published = year_match.group(0)

        entries.append({
            "title": title,
            "url": url,
            "summary": snippet or "Google Scholar result",
            "published": published,
        })
    return entries


def _search_web_candidates(
    topic_id: str,
    topic_name: str,
    keywords: list[str],
    max_results: int,
) -> list[dict[str, str]]:
    """Search Google Scholar. Returns [] if scrapling is not installed or disabled."""
    if not _web_search_enabled():
        return []

    try:
        from scrapling.fetchers import Fetcher  # type: ignore[import-untyped]
    except ImportError:
        return []

    query = _scholar_query_expression(topic_name, keywords)
    if not query:
        return []

    params = urlencode({"q": query, "hl": "en", "num": str(max(1, max_results))})
    url = f"{WEB_SEARCH_BASE_URL}?{params}"

    try:
        page = Fetcher.get(url, stealthy_headers=True, timeout=_web_search_timeout())
    except Exception as exc:
        return [
            {
                "topic_id": topic_id,
                "topic": topic_name,
                "title": f"{WEB_SEARCH_PROVIDER} 검색 조회 실패",
                "url": WEB_SEARCH_BASE_URL,
                "status": "not_verified_network",
                "search_query": query,
                "search_error": str(exc),
            }
        ]

    raw_entries = _parse_scholar_results(page, max_results)
    candidates: list[dict[str, str]] = []
    for entry in raw_entries:
        entry["topic_id"] = topic_id
        entry["topic"] = topic_name
        entry["status"] = "search_verified"
        entry["provider"] = WEB_SEARCH_PROVIDER
        entry["source_type"] = "web"
        entry["search_query"] = query
        candidates.append(entry)
    return candidates
