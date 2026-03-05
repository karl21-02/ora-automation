"""Research search clients: ArXiv, Crossref, OpenAlex."""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
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
    SEMANTIC_SCHOLAR_SEARCH_API_URL,
    SEMANTIC_SCHOLAR_SEARCH_DEFAULT_MAX_RESULTS,
    SEMANTIC_SCHOLAR_SEARCH_ENABLED_ENV,
    SEMANTIC_SCHOLAR_SEARCH_PROVIDER,
    SEMANTIC_SCHOLAR_SEARCH_TIMEOUT_SECONDS,
    WEB_SEARCH_DEFAULT_MAX_RESULTS,
    _read_bool_env,
    _read_float_env,
    _read_int_env,
)
from .web_sources import _search_web_candidates

logger = logging.getLogger(__name__)


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

# Cached env var reads (read once per process, env doesn't change mid-run)
_cached_env: dict[str, int | float] = {}


def _arxiv_search_limit() -> int:
    key = "arxiv_limit"
    if key not in _cached_env:
        _cached_env[key] = _read_int_env(
            "ORA_RD_RESEARCH_ARXIV_SEARCH_MAX_RESULTS",
            ARXIV_SEARCH_DEFAULT_MAX_RESULTS,
            aliases=("ORA_RD_ARXIV_SEARCH_MAX_RESULTS",),
        )
    return _cached_env[key]


def _arxiv_search_timeout() -> float:
    key = "arxiv_timeout"
    if key not in _cached_env:
        _cached_env[key] = _read_float_env(
            "ORA_RD_RESEARCH_SEARCH_TIMEOUT",
            ARXIV_SEARCH_TIMEOUT_SECONDS,
            aliases=("ORA_RD_ARXIV_SEARCH_TIMEOUT",),
        )
    return _cached_env[key]


def _crossref_search_limit() -> int:
    key = "crossref_limit"
    if key not in _cached_env:
        _cached_env[key] = _read_int_env(
            "ORA_RD_RESEARCH_CROSSREF_SEARCH_MAX_RESULTS",
            CROSSREF_SEARCH_DEFAULT_MAX_RESULTS,
            aliases=("ORA_RD_CROSSREF_SEARCH_MAX_RESULTS",),
        )
    return _cached_env[key]


def _crossref_search_timeout() -> float:
    key = "crossref_timeout"
    if key not in _cached_env:
        _cached_env[key] = _read_float_env(
            "ORA_RD_CROSSREF_SEARCH_TIMEOUT",
            CROSSREF_SEARCH_TIMEOUT_SECONDS,
            aliases=("ORA_RD_RESEARCH_CROSSREF_SEARCH_TIMEOUT", "ORA_RD_RESEARCH_SEARCH_TIMEOUT"),
        )
    return _cached_env[key]


def _openalex_search_limit() -> int:
    key = "openalex_limit"
    if key not in _cached_env:
        _cached_env[key] = _read_int_env(
            "ORA_RD_RESEARCH_OPENALEX_SEARCH_MAX_RESULTS",
            OPENALEX_SEARCH_DEFAULT_MAX_RESULTS,
            aliases=("ORA_RD_OPENALEX_SEARCH_MAX_RESULTS",),
        )
    return _cached_env[key]


def _openalex_search_timeout() -> float:
    key = "openalex_timeout"
    if key not in _cached_env:
        _cached_env[key] = _read_float_env(
            "ORA_RD_OPENALEX_SEARCH_TIMEOUT",
            OPENALEX_SEARCH_TIMEOUT_SECONDS,
            aliases=("ORA_RD_RESEARCH_OPENALEX_SEARCH_TIMEOUT", "ORA_RD_RESEARCH_SEARCH_TIMEOUT"),
        )
    return _cached_env[key]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_RETRY_STATUS_CODES = {429, 503}
_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY = 0.5  # seconds; doubles each retry (0.5, 1.0, 2.0)


def _request_url_bytes(url: str, timeout: float, max_bytes: int = 262144) -> bytes:
    last_exc: Exception | None = None
    for attempt in range(_RETRY_MAX_ATTEMPTS):
        try:
            req = Request(
                url=url,
                headers={
                    "User-Agent": "OraResearchOrchestrator/1.0 (+https://github.com/ora)",
                    "Accept": "application/atom+xml,application/xml,text/xml,*/*;q=0.8",
                },
            )
            with urlopen(req, timeout=timeout) as response:
                return response.read(max_bytes)
        except HTTPError as exc:
            last_exc = exc
            if exc.code in _RETRY_STATUS_CODES and attempt < _RETRY_MAX_ATTEMPTS - 1:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.info("HTTP %d for %s, retrying in %.1fs (attempt %d)", exc.code, url[:80], delay, attempt + 1)
                time.sleep(delay)
                continue
            raise
        except URLError:
            raise
    raise last_exc  # type: ignore[misc]


def _request_json(url: str, timeout: float, max_bytes: int = 262144) -> dict:
    last_exc: Exception | None = None
    for attempt in range(_RETRY_MAX_ATTEMPTS):
        try:
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
        except HTTPError as exc:
            last_exc = exc
            if exc.code in _RETRY_STATUS_CODES and attempt < _RETRY_MAX_ATTEMPTS - 1:
                delay = _RETRY_BASE_DELAY * (2 ** attempt)
                logger.info("HTTP %d for %s, retrying in %.1fs (attempt %d)", exc.code, url[:80], delay, attempt + 1)
                time.sleep(delay)
                continue
            raise
        except URLError:
            raise
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ArXiv
# ---------------------------------------------------------------------------

def _arxiv_query_expression(topic_id: str, topic_name: str, keywords: list[str]) -> str:
    """Build ArXiv query from topic name + keywords.

    Uses topic tokens directly — no mandatory domain filter.
    RESEARCH_QUERY_TAGS are added as soft boost terms (OR) rather than
    a hard AND gate, so papers outside voice/speech AI are not excluded.
    """
    topic_tokens = [topic_name]
    topic_tokens.extend(keywords[:6])
    clean_tokens = [t for t in topic_tokens[:8] if t]
    if not clean_tokens:
        return ""
    topic_expr = " OR ".join(f'all:"{token}"' for token in clean_tokens)
    # Add domain tags as soft boost (OR into the topic expression)
    # rather than the old AND gate that filtered out relevant papers
    boost_tags = [tag for tag in RESEARCH_QUERY_TAGS if tag.lower() not in topic_name.lower()][:2]
    if boost_tags:
        boost_expr = " OR ".join(f'all:"{tag}"' for tag in boost_tags)
        return f"({topic_expr}) OR ({boost_expr})"
    return topic_expr


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
# Semantic Scholar
# ---------------------------------------------------------------------------

def _semantic_scholar_search_limit() -> int:
    key = "semscholar_limit"
    if key not in _cached_env:
        _cached_env[key] = _read_int_env(
            "ORA_RD_RESEARCH_SEMANTIC_SCHOLAR_MAX_RESULTS",
            SEMANTIC_SCHOLAR_SEARCH_DEFAULT_MAX_RESULTS,
        )
    return _cached_env[key]


def _semantic_scholar_search_timeout() -> float:
    key = "semscholar_timeout"
    if key not in _cached_env:
        _cached_env[key] = _read_float_env(
            "ORA_RD_RESEARCH_SEMANTIC_SCHOLAR_TIMEOUT",
            SEMANTIC_SCHOLAR_SEARCH_TIMEOUT_SECONDS,
        )
    return _cached_env[key]


def _search_semantic_scholar_candidates(
    topic_id: str,
    topic_name: str,
    keywords: list[str],
    max_results: int,
) -> list[dict[str, str]]:
    """Search Semantic Scholar API. Free, no auth required."""
    if not _read_bool_env(SEMANTIC_SCHOLAR_SEARCH_ENABLED_ENV, default=True):
        return []

    terms = [topic_name] + keywords[:4]
    query = " ".join(t.strip() for t in terms if isinstance(t, str) and t.strip())
    if not query:
        return []

    params = urlencode({
        "query": query,
        "limit": str(max(1, max_results)),
        "fields": "title,authors,year,abstract,externalIds,url",
    })
    url = f"{SEMANTIC_SCHOLAR_SEARCH_API_URL}?{params}"

    try:
        payload = _request_json(url, timeout=_semantic_scholar_search_timeout())
    except (HTTPError, URLError) as exc:
        return [
            {
                "topic_id": topic_id,
                "topic": topic_name,
                "title": f"{SEMANTIC_SCHOLAR_SEARCH_PROVIDER} 검색 조회 실패",
                "url": SEMANTIC_SCHOLAR_SEARCH_API_URL,
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
                "title": f"{SEMANTIC_SCHOLAR_SEARCH_PROVIDER} 검색 처리 실패",
                "url": SEMANTIC_SCHOLAR_SEARCH_API_URL,
                "status": "not_verified_error",
                "search_query": query,
                "search_error": str(exc),
            }
        ]

    data = payload.get("data", [])
    if not isinstance(data, list):
        return []

    candidates: list[dict[str, str]] = []
    for item in data[:max_results]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or "").strip() or "(untitled)"
        paper_url = str(item.get("url", "") or "").strip()
        external_ids = item.get("externalIds") or {}
        arxiv_id = external_ids.get("ArXiv", "")
        doi = external_ids.get("DOI", "")
        if not paper_url:
            if arxiv_id:
                paper_url = f"{ARXIV_ABS_PREFIX}{arxiv_id}"
            elif doi:
                paper_url = f"https://doi.org/{quote(doi)}"
        year = item.get("year")
        published = str(year) if year else ""
        authors_raw = item.get("authors", [])
        authors = ", ".join(
            str(a.get("name", "")).strip()
            for a in (authors_raw if isinstance(authors_raw, list) else [])
            if isinstance(a, dict) and a.get("name")
        )[:300]
        abstract = str(item.get("abstract", "") or "").strip()[:500]

        candidates.append({
            "topic_id": topic_id,
            "topic": topic_name,
            "id": arxiv_id or doi or "",
            "title": title,
            "summary": abstract or "Semantic Scholar result",
            "published": published,
            "authors": authors,
            "url": paper_url,
            "status": "search_verified",
            "provider": SEMANTIC_SCHOLAR_SEARCH_PROVIDER,
            "source_type": "semantic_scholar_api",
            "search_query": query,
        })
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
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Collect seed + API search sources for the given topics.

    Returns (sources, search_warnings) where search_warnings contains
    error entries from failed API calls so callers can surface them.
    """
    sources: list[dict[str, str]] = []
    search_warnings: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    arxiv_limit = _arxiv_search_limit()
    crossref_limit = _crossref_search_limit()
    openalex_limit = _openalex_search_limit()
    semscholar_limit = _semantic_scholar_search_limit()
    web_limit = WEB_SEARCH_DEFAULT_MAX_RESULTS

    def _add_candidates(candidate_list: list[dict[str, str]]) -> None:
        for candidate in candidate_list:
            # Separate error entries from real results
            status = candidate.get("status", "")
            if status in ("not_verified_network", "not_verified_error"):
                search_warnings.append(candidate)
                continue
            norm_url = _normalize_source_url(candidate.get("url", ""))
            if norm_url in seen_urls:
                continue
            sources.append(candidate)
            seen_urls.add(norm_url)

    # Submit all API searches across all topics into a single pool
    topics_meta: list[dict] = []
    for item in top_topics[:top_k]:
        topics_meta.append({
            "topic_id": item["topic_id"],
            "topic_name": item["topic_name"],
            "ref_candidates": DEFAULT_TOPIC_SOURCES.get(item["topic_id"], []),
            "kw": (topic_keywords or {}).get(item["topic_id"], []),
        })

    with ThreadPoolExecutor(max_workers=min(20, len(topics_meta) * 5)) as executor:
        # {topic_id: {provider: future}}
        topic_futures: dict[str, dict[str, object]] = {}
        for meta in topics_meta:
            tid, tname, kw = meta["topic_id"], meta["topic_name"], meta["kw"]
            topic_futures[tid] = {
                "arxiv": executor.submit(
                    _search_arxiv_candidates,
                    topic_id=tid, topic_name=tname,
                    keywords=kw, max_results=arxiv_limit,
                ),
                "crossref": executor.submit(
                    _search_crossref_candidates,
                    topic_id=tid, topic_name=tname,
                    keywords=kw, max_results=crossref_limit,
                ),
                "openalex": executor.submit(
                    _search_openalex_candidates,
                    topic_id=tid, topic_name=tname,
                    keywords=kw, max_results=openalex_limit,
                ),
                "semantic_scholar": executor.submit(
                    _search_semantic_scholar_candidates,
                    topic_id=tid, topic_name=tname,
                    keywords=kw, max_results=semscholar_limit,
                ),
                "web": executor.submit(
                    _search_web_candidates,
                    topic_id=tid, topic_name=tname,
                    keywords=kw, max_results=web_limit,
                ),
            }

    # Collect results sequentially per topic (preserves ordering, deduplication)
    for meta in topics_meta:
        tid = meta["topic_id"]
        topic_name = meta["topic_name"]
        ref_candidates = meta["ref_candidates"]
        futs = topic_futures[tid]

        search_candidates = futs["arxiv"].result()
        crossref_candidates = futs["crossref"].result()
        openalex_candidates = futs["openalex"].result()
        semscholar_candidates = futs["semantic_scholar"].result()
        web_candidates = futs["web"].result()

        if not ref_candidates:
            fallback_query = quote_plus(f"{topic_name} speech AI")
            fallback_candidates = [
                {
                    "topic": topic_name,
                    "topic_id": tid,
                    "title": "ArXiv Search",
                    "url": f"https://arxiv.org/search/?query={fallback_query}&searchtype=all",
                    "status": "search_listed",
                    "provider": "arxiv_web",
                    "source_type": "search_portal",
                },
                {
                    "topic": topic_name,
                    "topic_id": tid,
                    "title": "Crossref Search",
                    "url": f"https://search.crossref.org/?q={fallback_query}",
                    "status": "search_listed",
                    "provider": "crossref_web",
                    "source_type": "search_portal",
                },
                {
                    "topic": topic_name,
                    "topic_id": tid,
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
            _add_candidates(semscholar_candidates)
            _add_candidates(web_candidates)
            continue

        for entry in ref_candidates:
            source = {
                "topic": topic_name,
                "topic_id": tid,
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
        _add_candidates(semscholar_candidates)
        _add_candidates(web_candidates)

    if search_warnings:
        logger.warning(
            "Research search had %d warning(s): %s",
            len(search_warnings),
            "; ".join(
                f"{w.get('provider', w.get('topic', '?'))}: {w.get('search_error', w.get('title', '?'))}"
                for w in search_warnings[:5]
            ),
        )
    return sources[:max(1, top_k * 8)], search_warnings


def build_sources_file(
    output_dir: Path,
    version_tag: str,
    report_focus: str,
    top_topics: list[dict],
    topic_keywords: dict[str, list[str]] | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Build and write research sources file.

    Returns (sources, search_warnings).
    """
    scope = (
        f"{version_tag} 확장 영역(또는 V10 이후 미탐색 영역) 기반 다중 에이전트 분석"
        if report_focus
        else "V1~V10 미탐색 영역"
    )
    generated_sources, search_warnings = build_default_sources(
        top_topics, topic_keywords=topic_keywords,
    )
    payload = {
        "report_version": version_tag,
        "report_focus": report_focus,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "scope": scope,
        "sources": generated_sources,
        "search_warnings": search_warnings,
        "summary": {
            "top_topics": [item["topic_name"] for item in top_topics[:6]],
            "total_sources": len(generated_sources),
            "failed_searches": len(search_warnings),
        },
    }

    source_path = output_dir / "research_sources.json"
    source_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return generated_sources, search_warnings
