#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import time
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import quote


ARXIV_QUERY_RE = re.compile(r"https?://arxiv\.org/abs/(?P<arxiv_id>[0-9]{4}\.[0-9]{4,5}(v[0-9]+)?)", re.IGNORECASE)
DOI_RE = re.compile(r"10\.[0-9]{4,9}/[\w\-._;()/:+~%]+", re.IGNORECASE)
ARXIV_API_URL = "https://export.arxiv.org/api/query?id_list={arxiv_id}"
CROSSREF_WORK_API_URL = "https://api.crossref.org/works/{doi}"
OPENALEX_DOI_API_URL = "https://api.openalex.org/works/https://doi.org/{doi}"
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def _build_ssl_context() -> ssl.SSLContext:
    env_ca = os.getenv("ORA_RD_CA_BUNDLE", "").strip()
    if env_ca:
        try:
            return ssl.create_default_context(cafile=env_ca)
        except Exception:
            pass

    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify source URLs and refresh research_sources.json status values."
    )
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        help="Path to source JSON (can be repeated).",
    )
    parser.add_argument(
        "--output",
        help="Output path for single source input. If omitted, updates in place.",
    )
    parser.add_argument("--in-place", action="store_true", help="Overwrite each --source file")
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="Per-request timeout in seconds (default: 8)",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=2,
        help="Retry rounds for unresolved records (default: 2)",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=1.2,
        help="Delay between rounds in seconds (default: 1.2)",
    )
    return parser.parse_args()


def _extract_title(html: str) -> str:
    match = TITLE_RE.search(html)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _extract_arxiv_id(url: str) -> str | None:
    match = ARXIV_QUERY_RE.search(url)
    if not match:
        return None
    return str(match.group("arxiv_id")).lower()


def _extract_doi(url_or_text: str) -> str | None:
    match = DOI_RE.search(url_or_text)
    if not match:
        return None
    doi = match.group(0).strip().rstrip(").,;")
    return doi


def _request_url(url: str, timeout: float, max_bytes: int = 65536) -> tuple[str, int | None, str, float]:
    req = request.Request(
        url=url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; OraResearchVerifier/1.0)",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        },
    )
    start = time.perf_counter()
    ctx = _build_ssl_context()
    with request.urlopen(req, timeout=timeout, context=ctx) as resp:
        status = int(resp.getcode())
        final_url = resp.geturl()
        body = resp.read(max_bytes)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    text = body.decode("utf-8", errors="ignore")
    return final_url, status, text, elapsed_ms


def _request_json(url: str, timeout: float, max_bytes: int = 65536) -> tuple[str, int | None, dict, float]:
    req = request.Request(
        url=url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; OraResearchVerifier/1.0)",
            "Accept": "application/json,*/*;q=0.8",
        },
    )
    start = time.perf_counter()
    ctx = _build_ssl_context()
    with request.urlopen(req, timeout=timeout, context=ctx) as resp:
        status = int(resp.getcode())
        final_url = str(resp.geturl())
        payload_bytes = resp.read(max_bytes)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    text = payload_bytes.decode("utf-8", errors="ignore")
    if not text:
        return final_url, status, {}, elapsed_ms
    try:
        payload: dict = json.loads(text)
    except json.JSONDecodeError:
        payload = {}
    return final_url, status, payload, elapsed_ms


def _classify_status(status_code: int | None, exception_text: str | None = None) -> str:
    if status_code is None:
        if not exception_text:
            return "not_verified_error"

        lowered = exception_text.lower()
        if "timed out" in lowered:
            return "not_verified_timeout"
        if "name or service not known" in lowered or "temporary failure in name resolution" in lowered:
            return "not_verified_dns"
        if "ssl" in lowered:
            return "not_verified_tls"
        return "not_verified_error"

    if 200 <= status_code < 300:
        return "verified_by_web_search"
    if status_code == 404:
        return "not_verified_missing"
    if status_code in (403, 429):
        return "not_verified_blocked"
    if 300 <= status_code < 400:
        return "not_verified_redirect"
    if status_code >= 500:
        return "not_verified_server_error"
    return f"not_verified_http_{status_code}"


def _check_arxiv_api(arxiv_id: str, timeout: float) -> dict[str, Any]:
    url = ARXIV_API_URL.format(arxiv_id=arxiv_id)
    checks: dict[str, Any] = {
        "arxiv_id": arxiv_id,
        "api_url": url,
    }

    try:
        final_url, status_code, body, elapsed_ms = _request_url(url, timeout=timeout, max_bytes=262144)
        checks.update(
            {
                "api_status": status_code,
                "api_final_url": final_url,
                "api_response_ms": elapsed_ms,
            }
        )

        normalized = body.lower()
        has_entry = (
            status_code == 200
            and "<entry>" in normalized
            and arxiv_id.lower().replace(".", "") in normalized.replace(".", "")
        )
        checks["api_available"] = bool(has_entry)
        if has_entry:
            return checks | {"verified": True, "status": "verified_by_arxiv_api"}

        checks["api_title"] = _extract_title(body)
        return checks | {"verified": False, "status": "not_verified_missing"}
    except error.HTTPError as exc:
        checks.update(
            {
                "api_status": exc.getcode(),
                "api_final_url": str(exc.geturl()),
                "api_response_ms": 0,
                "api_available": False,
            }
        )
        return checks | {"verified": False, "status": _classify_status(exc.getcode())}
    except error.URLError as exc:
        checks.update({"api_available": False, "api_error": str(exc.reason), "api_response_ms": 0})
        return checks | {"verified": False, "status": _classify_status(None, str(exc.reason))}
    except Exception as exc:
        checks.update({"api_available": False, "api_error": str(exc), "api_response_ms": 0})
        return checks | {"verified": False, "status": _classify_status(None, str(exc))}


def _check_crossref_doi(doi: str, timeout: float) -> dict[str, Any]:
    safe_doi = quote(doi)
    url = CROSSREF_WORK_API_URL.format(doi=safe_doi)
    checks: dict[str, Any] = {
        "doi": doi,
        "crossref_api_url": url,
    }
    try:
        final_url, status_code, payload, elapsed_ms = _request_json(url, timeout=timeout, max_bytes=262144)
        checks.update(
            {
                "crossref_status": status_code,
                "crossref_final_url": final_url,
                "crossref_response_ms": elapsed_ms,
            }
        )
        checks["crossref_has_payload"] = bool(payload.get("message")) if isinstance(payload, dict) else False
        verified = status_code == 200
        return checks | {"verified": verified, "status": "verified_by_crossref_doi" if verified else _classify_status(status_code)}
    except error.HTTPError as exc:
        checks.update({"crossref_status": exc.getcode(), "crossref_final_url": str(exc.geturl())})
        return checks | {"verified": False, "status": _classify_status(exc.getcode())}
    except error.URLError as exc:
        checks.update({"crossref_error": str(exc.reason)})
        return checks | {"verified": False, "status": _classify_status(None, str(exc.reason))}
    except Exception as exc:
        checks.update({"crossref_error": str(exc)})
        return checks | {"verified": False, "status": _classify_status(None, str(exc))}


def _check_openalex_doi(doi: str, timeout: float) -> dict[str, Any]:
    safe_doi = quote(doi)
    url = OPENALEX_DOI_API_URL.format(doi=safe_doi)
    checks: dict[str, Any] = {
        "doi": doi,
        "openalex_api_url": url,
    }
    try:
        final_url, status_code, payload, elapsed_ms = _request_json(url, timeout=timeout, max_bytes=262144)
        checks.update(
            {
                "openalex_status": status_code,
                "openalex_final_url": final_url,
                "openalex_response_ms": elapsed_ms,
            }
        )
        checks["openalex_has_payload"] = bool(payload.get("id")) if isinstance(payload, dict) else False
        verified = status_code == 200
        return checks | {"verified": verified, "status": "verified_by_openalex" if verified else _classify_status(status_code)}
    except error.HTTPError as exc:
        checks.update({"openalex_status": exc.getcode(), "openalex_final_url": str(exc.geturl())})
        return checks | {"verified": False, "status": _classify_status(exc.getcode())}
    except error.URLError as exc:
        checks.update({"openalex_error": str(exc.reason)})
        return checks | {"verified": False, "status": _classify_status(None, str(exc.reason))}
    except Exception as exc:
        checks.update({"openalex_error": str(exc)})
        return checks | {"verified": False, "status": _classify_status(None, str(exc))}


def _needs_verification(status: str | None) -> bool:
    if status is None:
        return True
    normalized = str(status)
    return normalized == "search_listed" or normalized.startswith("not_verified")


def _is_verified(status: str) -> bool:
    return str(status).startswith("verified")


def verify_record(record: dict[str, Any], timeout: float) -> dict[str, Any]:
    url = str(record.get("url", "")).strip()
    result: dict[str, Any] = dict(record)

    if not url:
        result.update(
            {
                "status": "not_verified_no_url",
                "verified_at": _now_iso(),
                "checks": result.get("checks", {}),
            }
        )
        return result

    arxiv_id = _extract_arxiv_id(url)
    doi = _extract_doi(url)
    checks = dict(result.get("checks", {}))
    arxiv_check = None
    crossref_check = None
    openalex_check = None

    if arxiv_id:
        arxiv_check = _check_arxiv_api(arxiv_id, timeout=timeout)
        checks["arxiv"] = {
            k: v for k, v in arxiv_check.items() if k not in {"verified", "status", "api_available"}
        }
    elif doi and "arxiv.org/abs" not in url.lower():
        crossref_check = _check_crossref_doi(doi, timeout=timeout)
        checks["crossref"] = {
            k: v for k, v in crossref_check.items() if k not in {"verified", "status"}
        }
        if not crossref_check.get("verified"):
            openalex_check = _check_openalex_doi(doi, timeout=timeout)
            checks["openalex"] = {
                k: v for k, v in openalex_check.items() if k not in {"verified", "status"}
            }

    try:
        final_url, status_code, html, elapsed_ms = _request_url(url, timeout=timeout)
        title = _extract_title(html)
        status = _classify_status(status_code, None)
    except error.HTTPError as exc:
        status_code = exc.getcode()
        status = _classify_status(status_code, None)
        final_url = str(exc.geturl())
        elapsed_ms = 0.0
        title = ""
    except error.URLError as exc:
        status = _classify_status(None, str(exc.reason))
        status_code = None
        final_url = url
        elapsed_ms = 0.0
        title = ""
    except Exception as exc:  # defensive
        status = _classify_status(None, str(exc))
        status_code = None
        final_url = url
        elapsed_ms = 0.0
        title = ""

    checks.update(
        {
            "http_status": status_code,
            "final_url": final_url,
            "response_ms": elapsed_ms,
            "page_title": title,
            "checked_with": "urllib",
        }
    )

    if arxiv_check and arxiv_check.get("verified"):
        status = "verified_by_arxiv_api"
    elif crossref_check and crossref_check.get("verified"):
        status = "verified_by_crossref_doi"
    elif openalex_check and openalex_check.get("verified"):
        status = "verified_by_openalex"
    elif arxiv_check and str(arxiv_check.get("status", "")).startswith("not_verified"):
        status = arxiv_check.get("status", status)

    if status == "search_listed":
        status = "not_verified_error"

    if status.startswith("verified") and str(result.get("status", "")).startswith("search_"):
        status = "verified_by_title_search"

    result.update(
        {
            "status": status,
            "verified_at": _now_iso(),
            "checks": checks,
        }
    )
    return result


def _load_source_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _extract_sources(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("sources"), list):
        return payload["sources"]
    return []


def _dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _summarize(sources: list[dict[str, Any]]) -> tuple[int, int, int]:
    total = len(sources)
    verified = len([s for s in sources if _is_verified(str(s.get("status", "")))])
    needs_action = total - verified
    return total, verified, needs_action


def main() -> int:
    args = _parse_args()
    source_paths = [Path(p).expanduser().resolve() for p in args.source]

    if not args.in_place and args.output:
        if len(source_paths) != 1:
            raise ValueError("--output can only be used with one --source")
        output_path = Path(args.output).expanduser().resolve()
    else:
        output_path = None

    all_ok = True

    for source_path in source_paths:
        payload = _load_source_file(source_path)
        sources = _extract_sources(payload)

        if not sources:
            print(f"[warn] no sources field in {source_path}")
            continue

        for round_no in range(1, max(1, args.rounds) + 1):
            for source in sources:
                if source.get("status") and not _needs_verification(str(source.get("status"))):
                    continue
                source.update(verify_record(source, timeout=args.timeout))

            total, verified, needs_action = _summarize(sources)
            print(
                f"[round {round_no}] {source_path.name}: verified={verified}/{total}, pending={needs_action}/{total}"
            )

            if needs_action == 0:
                break
            if round_no < args.rounds:
                time.sleep(args.retry_delay)

        total, verified, needs_action = _summarize(sources)
        all_ok = all_ok and needs_action == 0

        payload["sources"] = sources
        payload["validation"] = {
            "generated_at": _now_iso(),
            "total": total,
            "verified": verified,
            "needs_action": needs_action,
            "rounds": args.rounds,
            "status": "pass" if needs_action == 0 else "pending",
        }

        target = output_path if (output_path and source_path == source_paths[0]) else source_path
        if args.in_place or output_path is None:
            target = source_path
        _dump(target, payload)

        print(f"[done] source validation: {target}")

    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
