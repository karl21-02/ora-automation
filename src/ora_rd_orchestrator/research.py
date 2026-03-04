"""Research search clients: ArXiv, Crossref, OpenAlex."""
from __future__ import annotations

import datetime as dt
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, quote_plus, urlencode
from urllib.request import Request, urlopen

from .config import (
    ARXIV_ABS_PREFIX,
    ARXIV_SEARCH_API_URL,
    ARXIV_SEARCH_DEFAULT_MAX_RESULTS,
    ARXIV_SEARCH_ENABLED_ENV,
    ARXIV_SEARCH_ENABLED_ENV_OLD,
    ARXIV_SEARCH_PROVIDER,
    ARXIV_SEARCH_TIMEOUT_SECONDS,
    CROSSREF_SEARCH_API_URL,
    CROSSREF_SEARCH_DEFAULT_MAX_RESULTS,
    CROSSREF_SEARCH_ENABLED_ENV,
    CROSSREF_SEARCH_PROVIDER,
    CROSSREF_SEARCH_TIMEOUT_SECONDS,
    OPENALEX_SEARCH_API_URL,
    OPENALEX_SEARCH_DEFAULT_MAX_RESULTS,
    OPENALEX_SEARCH_EMAIL,
    OPENALEX_SEARCH_ENABLED_ENV,
    OPENALEX_SEARCH_PROVIDER,
    OPENALEX_SEARCH_TIMEOUT_SECONDS,
    _read_bool_env,
    _read_float_env,
    _read_int_env,
)


# ---------------------------------------------------------------------------
# Legacy seed data (kept for backward compat, will be replaced by LLM)
# ---------------------------------------------------------------------------

RESEARCH_QUERY_TAGS = [
    "voice AI",
    "speech AI",
    "telephony",
    "real-time dialogue",
    "speech recognition",
    "TTS",
]

DEFAULT_TOPIC_SOURCES: dict[str, list[dict[str, str]]] = {
    "turn_taking": [
        {"id": "2401.04868", "title": "VAP - Real-time Turn-taking Prediction", "url": "https://arxiv.org/abs/2401.04868"},
        {"id": "2403.06487", "title": "Multilingual VAP", "url": "https://arxiv.org/abs/2403.06487"},
        {"id": "2505.12654", "title": "Predicting Turn-Taking in Human-Machine Conversations", "url": "https://arxiv.org/abs/2505.12654"},
        {"id": "2401.14717", "title": "Acoustic + LLM Fusion for Turn-Taking", "url": "https://arxiv.org/abs/2401.14717"},
    ],
    "proactive_dialogue": [
        {"id": "2508.04403", "title": "Dialogue Response Prefetching", "url": "https://arxiv.org/abs/2508.04403"},
        {"id": "2601.09713", "title": "ProUtt", "url": "https://arxiv.org/abs/2601.09713"},
        {"id": "2509.01051", "title": "Chronicled Turn-Taking in Dialogues", "url": "https://arxiv.org/abs/2509.01051"},
        {"title": "Proactive Conversational AI Survey", "url": "https://dl.acm.org/doi/10.1145/3715097"},
    ],
    "tool_use": [
        {"id": "2510.07978", "title": "VoiceAgentBench", "url": "https://arxiv.org/abs/2510.07978"},
        {"id": "2410.17196", "title": "VoiceBench", "url": "https://arxiv.org/abs/2410.17196"},
        {"id": "2510.14453", "title": "Natural Language Tools", "url": "https://arxiv.org/abs/2510.14453"},
    ],
    "summarization": [
        {"id": "2510.06677", "title": "Incremental Summarization", "url": "https://arxiv.org/abs/2510.06677"},
        {"id": "2308.15022", "title": "Recursively Summarizing", "url": "https://arxiv.org/abs/2308.15022"},
        {"id": "2410.18624", "title": "Length-Controllable Call Summarization", "url": "https://arxiv.org/abs/2410.18624"},
        {"id": "2307.15793", "title": "LLM Meeting Recap", "url": "https://arxiv.org/abs/2307.15793"},
    ],
    "hallucination": [
        {"id": "2509.09360", "title": "MetaRAG", "url": "https://arxiv.org/abs/2509.09360"},
        {"id": "2410.03461", "title": "Auto-GDA", "url": "https://arxiv.org/abs/2410.03461"},
        {"id": "2510.24476", "title": "Hallucination Survey", "url": "https://arxiv.org/abs/2510.24476"},
    ],
    "empathy": [
        {"id": "2508.18655", "title": "Empathy Omni", "url": "https://arxiv.org/abs/2508.18655"},
        {"id": "2602.21900", "title": "EmoOmni", "url": "https://arxiv.org/abs/2602.21900"},
        {"id": "2507.05177", "title": "OpenS2S", "url": "https://arxiv.org/abs/2507.05177"},
    ],
    "topic_routing": [
        {"id": "2509.01051", "title": "Chronotome", "url": "https://arxiv.org/abs/2509.01051"},
        {"id": "2505.12654", "title": "Predicting Turn-Taking in Human-Machine Conversations", "url": "https://arxiv.org/abs/2505.12654"},
    ],
    "aesc_preprocessing": [
        {"id": "2508.06271", "title": "EchoFree", "url": "https://arxiv.org/abs/2508.06271"},
        {"id": "2305.08227", "title": "DeepFilterNet3", "url": "https://arxiv.org/abs/2305.08227"},
        {"id": "2409.03377", "title": "aTENNuate", "url": "https://arxiv.org/abs/2409.03377"},
    ],
    "disfluency": [
        {"id": "2505.21551", "title": "WhisperD", "url": "https://arxiv.org/abs/2505.21551"},
        {"id": "2409.10177", "title": "Augmenting ASR with Disfluency Detection", "url": "https://arxiv.org/abs/2409.10177"},
        {"id": "2407.13782", "title": "Self-supervised ASR for Elderly Speech", "url": "https://arxiv.org/abs/2407.13782"},
    ],
    "foundation": [
        {"id": "2110.13900", "title": "WavLM", "url": "https://arxiv.org/abs/2110.13900"},
        {"id": "2308.00100", "title": "VOTE400 Dataset", "url": "https://arxiv.org/abs/2308.00100"},
    ],
    "deepfake": [
        {"id": "2408.08739", "title": "ASVspoof 5", "url": "https://arxiv.org/abs/2408.08739"},
        {"id": "2309.08279", "title": "AASIST2", "url": "https://arxiv.org/abs/2309.08279"},
        {"title": "ASVspoof", "url": "https://www.asvspoof.org/"},
    ],
    "voice_cloning": [
        {"id": "2505.17589", "title": "CosyVoice 2", "url": "https://arxiv.org/abs/2505.17589"},
        {"id": "2502.05512", "title": "IndexTTS-2", "url": "https://arxiv.org/abs/2502.05512"},
        {"id": "2509.14579", "title": "Cross-Lingual F5-TTS", "url": "https://arxiv.org/abs/2509.14579"},
    ],
    "context_biasing": [
        {"id": "2109.00627", "title": "TCPGen", "url": "https://arxiv.org/abs/2109.00627"},
        {"id": "2503.02707", "title": "Voila", "url": "https://arxiv.org/abs/2503.02707"},
        {"title": "Deepgram Keyterms", "url": "https://developers.deepgram.com/docs/keyterms"},
    ],
}


# ---------------------------------------------------------------------------
# Env-based limits / timeouts
# ---------------------------------------------------------------------------

def _arxiv_search_limit() -> int:
    return _read_int_env(
        "ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS",
        ARXIV_SEARCH_DEFAULT_MAX_RESULTS,
        aliases=("ORA_RD_ARXIV_SEARCH_MAX_RESULTS",),
    )


def _arxiv_search_timeout() -> float:
    return _read_float_env(
        "ORA_RD_RESEARCH_SEARCH_TIMEOUT",
        ARXIV_SEARCH_TIMEOUT_SECONDS,
        aliases=("ORA_RD_ARXIV_SEARCH_TIMEOUT",),
    )


def _crossref_search_limit() -> int:
    return _read_int_env(
        "ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS",
        CROSSREF_SEARCH_DEFAULT_MAX_RESULTS,
        aliases=("ORA_RD_CROSSREF_SEARCH_MAX_RESULTS",),
    )


def _crossref_search_timeout() -> float:
    return _read_float_env(
        "ORA_RD_CROSSREF_SEARCH_TIMEOUT",
        CROSSREF_SEARCH_TIMEOUT_SECONDS,
        aliases=("ORA_RD_RESEARCH_CROSSREF_SEARCH_TIMEOUT", "ORA_RD_RESEARCH_SEARCH_TIMEOUT"),
    )


def _openalex_search_limit() -> int:
    return _read_int_env(
        "ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS",
        OPENALEX_SEARCH_DEFAULT_MAX_RESULTS,
        aliases=("ORA_RD_OPENALEX_SEARCH_MAX_RESULTS",),
    )


def _openalex_search_timeout() -> float:
    return _read_float_env(
        "ORA_RD_OPENALEX_SEARCH_TIMEOUT",
        OPENALEX_SEARCH_TIMEOUT_SECONDS,
        aliases=("ORA_RD_RESEARCH_OPENALEX_SEARCH_TIMEOUT", "ORA_RD_RESEARCH_SEARCH_TIMEOUT"),
    )


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _request_url_bytes(url: str, timeout: float, max_bytes: int = 262144) -> bytes:
    req = Request(
        url=url,
        headers={
            "User-Agent": "OraResearchOrchestrator/1.0 (+https://github.com/ora)",
            "Accept": "application/atom+xml,application/xml,text/xml,*/*;q=0.8",
        },
    )
    with urlopen(req, timeout=timeout) as response:
        return response.read(max_bytes)


def _request_json(url: str, timeout: float, max_bytes: int = 262144) -> dict:
    req = Request(
        url=url,
        headers={
            "User-Agent": "OraResearchOrchestrator/1.0 (+https://github.com/ora)",
            "Accept": "application/json,*/*;q=0.8",
        },
    )
    with urlopen(req, timeout=timeout) as response:
        payload = response.read(max_bytes).decode("utf-8", errors="ignore")
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# ArXiv
# ---------------------------------------------------------------------------

def _arxiv_query_expression(topic_id: str, topic_name: str, keywords: list[str]) -> str:
    topic_tokens = [topic_name]
    topic_tokens.extend(keywords[:6])
    topic_expr = " OR ".join(
        [f'all:"{token}"' for token in topic_tokens[:8] if token]
    )
    domain_expr = " OR ".join([f'all:"{tag}"' for tag in RESEARCH_QUERY_TAGS])
    if topic_expr and domain_expr:
        return f"({topic_expr}) AND ({domain_expr})"
    return topic_expr or domain_expr


def _parse_arxiv_feed(feed_bytes: bytes) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    try:
        root = ET.fromstring(feed_bytes)
    except ET.ParseError:
        return entries

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("atom:entry", ns):
        entry_id = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
        if not entry_id:
            continue
        arxiv_id = entry_id.rsplit("/abs/", 1)[-1].lower()
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip().replace("\n", " ")
        summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip().replace("\n", " ")
        published = (entry.findtext("atom:published", default="", namespaces=ns) or "").strip()
        updated = (entry.findtext("atom:updated", default="", namespaces=ns) or "").strip()
        authors = []
        for author in entry.findall("atom:author", ns):
            name = (author.findtext("atom:name", default="", namespaces=ns) or "").strip()
            if name:
                authors.append(name)

        entries.append(
            {
                "id": arxiv_id,
                "title": title or "(untitled)",
                "summary": summary[:1000],
                "published": published,
                "updated": updated,
                "authors": ", ".join(authors[:8]),
                "url": f"{ARXIV_ABS_PREFIX}{arxiv_id}",
            }
        )
    return entries


def _search_arxiv_candidates(
    topic_id: str,
    topic_name: str,
    keywords: list[str],
    max_results: int,
) -> list[dict[str, str]]:
    if not _read_bool_env(
        ARXIV_SEARCH_ENABLED_ENV,
        default=True,
        aliases=(ARXIV_SEARCH_ENABLED_ENV_OLD,),
    ):
        return []

    query = _arxiv_query_expression(topic_id, topic_name, keywords)
    if not query:
        return []

    params = urlencode(
        {
            "search_query": query,
            "start": "0",
            "max_results": str(max(1, max_results)),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    url = f"{ARXIV_SEARCH_API_URL}?{params}"
    try:
        feed_bytes = _request_url_bytes(url=url, timeout=_arxiv_search_timeout())
    except (HTTPError, URLError) as exc:
        return [
            {
                "topic_id": topic_id,
                "topic": topic_name,
                "title": f"{ARXIV_SEARCH_PROVIDER} 검색 조회 실패",
                "url": f"{ARXIV_ABS_PREFIX}",
                "status": "not_verified_network",
                "search_query": query,
                "search_error": str(exc),
            }
        ]
    except Exception as exc:
        return [
            {
                "topic_id": topic_id,
                "topic": topic_name,
                "title": f"{ARXIV_SEARCH_PROVIDER} 검색 처리 실패",
                "url": f"{ARXIV_ABS_PREFIX}",
                "status": "not_verified_error",
                "search_query": query,
                "search_error": str(exc),
            }
        ]

    raw_entries = _parse_arxiv_feed(feed_bytes)
    if not raw_entries:
        return []

    candidates: list[dict[str, str]] = []
    for entry in raw_entries[: max(1, max_results)]:
        entry["topic_id"] = topic_id
        entry["topic"] = topic_name
        entry["status"] = "search_verified"
        entry["provider"] = ARXIV_SEARCH_PROVIDER
        entry["source_type"] = "arxiv_api"
        entry["search_query"] = query
        candidates.append(entry)
    return candidates


# ---------------------------------------------------------------------------
# Crossref
# ---------------------------------------------------------------------------

def _crossref_query_expression(topic_id: str, topic_name: str, keywords: list[str]) -> str:
    del topic_id
    terms = [topic_name]
    terms.extend(keywords[:6])
    return " ".join([t.strip() for t in terms if isinstance(t, str) and t.strip()][:10])


def _parse_crossref_response(payload: dict, topic_id: str, topic_name: str) -> list[dict[str, str]]:
    del topic_id
    del topic_name
    entries: list[dict[str, str]] = []
    items = payload.get("message", {}).get("items", [])
    if not isinstance(items, list):
        return entries

    for item in items:
        if not isinstance(item, dict):
            continue
        doi = (item.get("DOI") or item.get("doi") or "").strip()
        title = ""
        raw_title = item.get("title")
        if isinstance(raw_title, list) and raw_title:
            title = str(raw_title[0]).strip()
        elif isinstance(raw_title, str):
            title = raw_title.strip()
        if not title:
            title = "(untitled)"

        published = ""
        issued = item.get("issued", {})
        if isinstance(issued, dict):
            date_parts = issued.get("date-parts")
            if isinstance(date_parts, list) and date_parts and isinstance(date_parts[0], list) and date_parts[0]:
                year = date_parts[0][0]
                if year:
                    published = str(year)

        authors = []
        for author in item.get("author", []) if isinstance(item.get("author"), list) else []:
            if not isinstance(author, dict):
                continue
            family = str(author.get("family", "") or "").strip()
            given = str(author.get("given", "") or "").strip()
            if family and given:
                authors.append(f"{family} {given}")
            elif family:
                authors.append(family)
            elif given:
                authors.append(given)

        summary = ""
        abstract = item.get("abstract")
        if isinstance(abstract, str):
            summary = abstract[:300]

        entries.append(
            {
                "id": doi,
                "title": title,
                "summary": summary or "Crossref result",
                "published": published,
                "authors": ", ".join(authors[:8]),
                "url": f"https://doi.org/{quote(doi)}" if doi else "",
            }
        )
    return entries


def _search_crossref_candidates(
    topic_id: str,
    topic_name: str,
    keywords: list[str],
    max_results: int,
) -> list[dict[str, str]]:
    if not _read_bool_env(CROSSREF_SEARCH_ENABLED_ENV, default=True):
        return []

    query = _crossref_query_expression(topic_id, topic_name, keywords)
    if not query:
        return []
    params = urlencode(
        {
            "query.bibliographic": query,
            "rows": str(max(1, max_results)),
            "select": "DOI,title,issued,author,URL",
        }
    )
    url = f"{CROSSREF_SEARCH_API_URL}?{params}"
    try:
        payload = _request_json(url, timeout=_crossref_search_timeout())
    except (HTTPError, URLError) as exc:
        return [
            {
                "topic_id": topic_id,
                "topic": topic_name,
                "title": f"{CROSSREF_SEARCH_PROVIDER} 검색 조회 실패",
                "url": "https://api.crossref.org/works",
                "status": "not_verified_network",
                "search_query": query,
                "search_error": str(exc),
            }
        ]
    except Exception as exc:
        return [
            {
                "topic_id": topic_id,
                "topic": topic_name,
                "title": f"{CROSSREF_SEARCH_PROVIDER} 검색 처리 실패",
                "url": "https://api.crossref.org/works",
                "status": "not_verified_error",
                "search_query": query,
                "search_error": str(exc),
            }
        ]

    candidates: list[dict[str, str]] = []
    for entry in _parse_crossref_response(payload, topic_id=topic_id, topic_name=topic_name)[: max(1, max_results)]:
        entry["topic_id"] = topic_id
        entry["topic"] = topic_name
        entry["status"] = "search_verified"
        entry["provider"] = CROSSREF_SEARCH_PROVIDER
        entry["source_type"] = "crossref_api"
        entry["search_query"] = query
        candidates.append(entry)
    return candidates


# ---------------------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------------------

def _openalex_query_expression(topic_id: str, topic_name: str, keywords: list[str]) -> str:
    del topic_id
    terms = [topic_name]
    terms.extend(keywords[:6])
    return " ".join([t.strip() for t in terms if isinstance(t, str) and t.strip()][:10])


def _parse_openalex_response(payload: dict, topic_id: str, topic_name: str) -> list[dict[str, str]]:
    del topic_id
    del topic_name
    entries: list[dict[str, str]] = []
    results = payload.get("results", [])
    if not isinstance(results, list):
        return entries

    for item in results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("display_name", "") or "").strip() or "(untitled)"
        doi = str(item.get("doi", "") or "").strip()
        url = str(item.get("id", "") or "").strip()
        if doi:
            url = f"https://doi.org/{quote(doi)}"

        publication_year = item.get("publication_year")
        published = str(publication_year) if publication_year else ""

        authors = []
        for author in item.get("authorships", []) if isinstance(item.get("authorships"), list) else []:
            if not isinstance(author, dict):
                continue
            author_name = str(author.get("author", {}).get("display_name", "") or "").strip()
            if author_name:
                authors.append(author_name)

        summary = str(item.get("abstract_inverted_index", "") or "").strip()

        entries.append(
            {
                "id": doi if doi else str(item.get("id", "")).rsplit("/", 1)[-1],
                "title": title,
                "summary": summary or "OpenAlex result",
                "published": published,
                "authors": ", ".join(authors[:8]),
                "url": url,
            }
        )
    return entries


def _search_openalex_candidates(
    topic_id: str,
    topic_name: str,
    keywords: list[str],
    max_results: int,
) -> list[dict[str, str]]:
    if not _read_bool_env(OPENALEX_SEARCH_ENABLED_ENV, default=True):
        return []

    query = _openalex_query_expression(topic_id, topic_name, keywords)
    if not query:
        return []
    params = urlencode(
        {
            "search": query,
            "per-page": str(max(1, max_results)),
            "filter": "type:conference-paper,type:journal-article",
            "mailto": OPENALEX_SEARCH_EMAIL,
        }
    )
    url = f"{OPENALEX_SEARCH_API_URL}?{params}"
    try:
        payload = _request_json(url, timeout=_openalex_search_timeout())
    except (HTTPError, URLError) as exc:
        return [
            {
                "topic_id": topic_id,
                "topic": topic_name,
                "title": f"{OPENALEX_SEARCH_PROVIDER} 검색 조회 실패",
                "url": "https://api.openalex.org/works",
                "status": "not_verified_network",
                "search_query": query,
                "search_error": str(exc),
            }
        ]
    except Exception as exc:
        return [
            {
                "topic_id": topic_id,
                "topic": topic_name,
                "title": f"{OPENALEX_SEARCH_PROVIDER} 검색 처리 실패",
                "url": "https://api.openalex.org/works",
                "status": "not_verified_error",
                "search_query": query,
                "search_error": str(exc),
            }
        ]

    candidates: list[dict[str, str]] = []
    for entry in _parse_openalex_response(payload, topic_id=topic_id, topic_name=topic_name)[: max(1, max_results)]:
        entry["topic_id"] = topic_id
        entry["topic"] = topic_name
        entry["status"] = "search_verified"
        entry["provider"] = OPENALEX_SEARCH_PROVIDER
        entry["source_type"] = "openalex_api"
        entry["search_query"] = query
        candidates.append(entry)
    return candidates


# ---------------------------------------------------------------------------
# Aggregated research query / source builders
# ---------------------------------------------------------------------------

def _normalize_source_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def build_research_queries(
    top_topics: list[dict],
    topic_keywords: dict[str, list[str]] | None = None,
    top_k: int = 5,
) -> list[dict[str, object]]:
    """Build research query descriptors for top topics.

    Parameters
    ----------
    topic_keywords:
        Mapping of topic_id -> keyword list. When ``None``, falls back to
        an empty list for each topic.
    """
    queries: list[dict[str, object]] = []
    for item in top_topics[:top_k]:
        topic_id = item["topic_id"]
        topic_name = item["topic_name"]
        keywords = (topic_keywords or {}).get(topic_id, [])
        query_keywords = ", ".join(keywords[:6]) if keywords else topic_name
        core_terms = ", ".join(keywords[:4]) if keywords else topic_name
        queries.append(
            {
                "topic_id": topic_id,
                "topic_name": topic_name,
                "web_query": f"{topic_name} recent method paper 2024~2026 ({query_keywords})",
                "query_hint": (
                    f"site:arxiv.org {query_keywords} | "
                    f"{core_terms} site:crossref.org | "
                    f"{core_terms} site:openalex.org"
                ),
                "provider_queries": {
                    ARXIV_SEARCH_PROVIDER: f"site:arxiv.org {core_terms} speech AI 2024 2025",
                    CROSSREF_SEARCH_PROVIDER: f"{core_terms} Crossref 2024 2025",
                    OPENALEX_SEARCH_PROVIDER: f"{core_terms} OpenAlex dialogue speech",
                },
            }
        )
    return queries


def build_default_sources(
    top_topics: list[dict],
    topic_keywords: dict[str, list[str]] | None = None,
    top_k: int = 12,
) -> list[dict[str, str]]:
    """Collect seed + API search sources for the given topics."""
    sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    arxiv_limit = _arxiv_search_limit()
    crossref_limit = _crossref_search_limit()
    openalex_limit = _openalex_search_limit()

    def _add_candidates(candidate_list: list[dict[str, str]]) -> None:
        for candidate in candidate_list:
            norm_url = _normalize_source_url(candidate.get("url", ""))
            if norm_url in seen_urls:
                continue
            sources.append(candidate)
            seen_urls.add(norm_url)

    for item in top_topics[:top_k]:
        topic_id = item["topic_id"]
        topic_name = item["topic_name"]
        ref_candidates = DEFAULT_TOPIC_SOURCES.get(topic_id, [])
        kw = (topic_keywords or {}).get(topic_id, [])
        search_candidates = _search_arxiv_candidates(
            topic_id=topic_id,
            topic_name=topic_name,
            keywords=kw,
            max_results=min(3, arxiv_limit),
        )
        crossref_candidates = _search_crossref_candidates(
            topic_id=topic_id,
            topic_name=topic_name,
            keywords=kw,
            max_results=min(2, crossref_limit),
        )
        openalex_candidates = _search_openalex_candidates(
            topic_id=topic_id,
            topic_name=topic_name,
            keywords=kw,
            max_results=min(2, openalex_limit),
        )

        if not ref_candidates:
            fallback_query = quote_plus(f"{topic_name} speech AI")
            fallback_candidates = [
                {
                    "topic": topic_name,
                    "topic_id": topic_id,
                    "title": "ArXiv Search",
                    "url": f"https://arxiv.org/search/?query={fallback_query}&searchtype=all",
                    "status": "search_listed",
                    "provider": "arxiv_web",
                    "source_type": "search_portal",
                },
                {
                    "topic": topic_name,
                    "topic_id": topic_id,
                    "title": "Crossref Search",
                    "url": f"https://search.crossref.org/?q={fallback_query}",
                    "status": "search_listed",
                    "provider": "crossref_web",
                    "source_type": "search_portal",
                },
                {
                    "topic": topic_name,
                    "topic_id": topic_id,
                    "title": "OpenAlex Search",
                    "url": f"https://openalex.org/search?q={fallback_query}",
                    "status": "search_listed",
                    "provider": "openalex_web",
                    "source_type": "search_portal",
                },
            ]
            _add_candidates(fallback_candidates)
            _add_candidates(search_candidates)
            _add_candidates(crossref_candidates)
            _add_candidates(openalex_candidates)
            continue

        for entry in ref_candidates:
            source = {
                "topic": topic_name,
                "topic_id": topic_id,
                "title": entry["title"],
                "url": entry["url"],
                "status": "search_listed",
                "provider": "seed",
                "source_type": "seed",
            }
            arxiv_id = entry.get("id", "").strip()
            if arxiv_id:
                source["id"] = arxiv_id
            norm_url = _normalize_source_url(source["url"])
            if norm_url in seen_urls:
                continue
            sources.append(source)
            seen_urls.add(norm_url)
        _add_candidates(search_candidates)
        _add_candidates(crossref_candidates)
        _add_candidates(openalex_candidates)

    return sources[:max(1, top_k * 4)]


def build_sources_file(
    output_dir: Path,
    version_tag: str,
    report_focus: str,
    top_topics: list[dict],
    topic_keywords: dict[str, list[str]] | None = None,
) -> list[dict[str, str]]:
    scope = (
        f"{version_tag} 확장 영역(또는 V10 이후 미탐색 영역) 기반 다중 에이전트 분석"
        if report_focus
        else "V1~V10 미탐색 영역"
    )
    generated_sources = build_default_sources(top_topics, topic_keywords=topic_keywords)
    payload = {
        "report_version": version_tag,
        "report_focus": report_focus,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "scope": scope,
        "sources": generated_sources,
        "summary": {
            "top_topics": [item["topic_name"] for item in top_topics[:6]],
            "total_sources": len(generated_sources),
        },
    }

    source_path = output_dir / "research_sources.json"
    source_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return generated_sources
