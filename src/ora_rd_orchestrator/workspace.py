"""Workspace scanning and evidence collection."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List

from .config import (
    PROJECT_FILES,
    SERVICE_ALIAS_MAP,
    _NOISY_FILENAMES,
    _normalize_text_token,
    _service_alias_to_scope,
)
from .types import Evidence, TopicDiscovery, TopicState, WorkspaceSummary


# ---------------------------------------------------------------------------
# File iteration helpers
# ---------------------------------------------------------------------------

def _iter_files(
    workspace: Path,
    extensions: set[str],
    ignore_dirs: set[str],
    max_files: int,
) -> Iterable[Path]:
    candidates: List[Path] = []
    for root, dirs, files in os.walk(workspace):
        current = Path(root)
        dirs[:] = [
            d for d in dirs
            if d not in ignore_dirs
            and not d.startswith(".")
            and d.lower() not in {"out", "tmp", "cache", "target", "build"}
        ]
        for file_name in files:
            if file_name in _NOISY_FILENAMES:
                continue
            if file_name.endswith(".lock"):
                continue
            file_path = current / file_name
            if any(part in ignore_dirs for part in file_path.parts):
                continue
            ext = file_path.suffix.lower().lstrip(".")
            if not ext and file_name in PROJECT_FILES:
                candidates.append(file_path)
                continue
            if ext not in extensions:
                continue
            if file_path.stat().st_size > 1_200_000:
                continue
            candidates.append(file_path)
    if not candidates:
        return []

    project_groups: dict[str, list[Path]] = {}
    for file_path in candidates:
        project = _infer_project_name(workspace, file_path)
        project_groups.setdefault(project, []).append(file_path)

    for key in project_groups:
        project_groups[key] = sorted(project_groups[key])

    project_keys = sorted(project_groups.keys())
    balanced: list[Path] = []
    depth = 0
    while len(balanced) < max_files:
        progressed = False
        for key in project_keys:
            files = project_groups[key]
            if depth < len(files):
                balanced.append(files[depth])
                progressed = True
                if len(balanced) >= max_files:
                    break
        if not progressed:
            break
        depth += 1
    return balanced


def _infer_project_name(workspace: Path, file_path: Path) -> str:
    try:
        relative = file_path.relative_to(workspace)
    except ValueError:
        return "external"
    if len(relative.parts) == 0:
        return "root"
    return relative.parts[0]


def _matches(text: str, keys: Iterable[str]) -> list[str]:
    lowered = text.lower()
    return [k for k in keys if k.lower() in lowered]


def _read_lines(file_path: Path) -> list[tuple[int, str]]:
    try:
        with file_path.open("r", encoding="utf-8", errors="ignore") as f:
            return [(i + 1, line.rstrip()) for i, line in enumerate(f)]
    except OSError:
        return []


def _safe_snippet(line: str) -> str:
    text = line.strip()
    if len(text) <= 170:
        return text
    return text[:167] + "..."


def _update_topic_hits(
    topic_state: TopicState,
    match: str,
    project_name: str,
    is_code: bool,
    is_history: bool,
) -> None:
    topic_state.keyword_hits += 1
    topic_state.project_hits[project_name] = topic_state.project_hits.get(project_name, 0) + 1
    if is_code:
        topic_state.code_hits += 1
    else:
        topic_state.doc_hits += 1
    if is_history:
        topic_state.history_hits += 1


# ---------------------------------------------------------------------------
# Legacy hardcoded word lists (kept for backward compat, will be removed
# when LLM scoring fully replaces rule-based scoring)
# ---------------------------------------------------------------------------

BUSINESS_WORDS = [
    "roi", "시장", "비용", "수익", "매출", "고객", "과제", "지원",
    "정부", "B2B", "과금", "투자", "수주", "규모", "서비스", "사업",
]

NOVELTY_WORDS = [
    "novel", "first", "new", "독자", "차별", "독보", "미존재", "처음",
    "최초", "세계", "유일", "논문", "arxiv", "interspeech", "ICASSP",
    "ACL", "EMNLP", "NeurIPS",
]


# ---------------------------------------------------------------------------
# Main workspace analysis
# ---------------------------------------------------------------------------

def analyze_workspace(
    workspace: Path,
    extensions: List[str],
    ignore_dirs: set[str],
    max_files: int,
    history_files: list[Path],
    topics: dict[str, dict] | None = None,
    topic_discoveries: list[TopicDiscovery] | None = None,
    service_scope: set[str] | None = None,
) -> dict[str, TopicState]:
    """Scan workspace and build topic states.

    Accepts either legacy ``topics`` dict (TOPICS format from engine.py) or
    new ``topic_discoveries`` list. If both are ``None`` an empty dict is
    returned.
    """
    # Build internal topic+keyword map
    topic_map: dict[str, dict[str, list[str]]] = {}
    if topic_discoveries:
        for td in topic_discoveries:
            topic_map[td.topic_id] = {
                "name": td.topic_name,
                "keywords": td.suggested_keywords,
            }
    elif topics:
        topic_map = {k: {"name": v["name"], "keywords": v.get("keywords", [])} for k, v in topics.items()}
    else:
        return {}

    canonical_scopes: set[str] = set()
    for item in (service_scope or set()):
        resolved = _service_alias_to_scope(str(item))
        if resolved:
            canonical_scopes.add(resolved)

    include_docs = "docs" in canonical_scopes or "global" in canonical_scopes or not canonical_scopes
    allowed_projects: set[str] = set()
    if canonical_scopes:
        for scope_name in canonical_scopes:
            aliases = [scope_name]
            aliases.extend(SERVICE_ALIAS_MAP.get(scope_name, []))
            allowed_projects.update({_normalize_text_token(alias) for alias in aliases if alias})

    states: dict[str, TopicState] = {
        topic_id: TopicState(topic_id=topic_id, topic_name=details["name"])
        for topic_id, details in topic_map.items()
    }

    ext_set = {item.lower().lstrip(".") for item in extensions}
    file_paths = _iter_files(workspace, ext_set, set(ignore_dirs), max_files)

    for file_path in file_paths:
        project_name = _infer_project_name(workspace, file_path)
        project_name_norm = _normalize_text_token(project_name)
        if canonical_scopes and project_name_norm != "root":
            if project_name_norm not in allowed_projects:
                continue
        if project_name_norm == "root" and not include_docs:
            continue
        lines = _read_lines(file_path)
        if not lines:
            continue

        is_code_file = file_path.suffix.lower() in {".java", ".kt", ".py", ".ts", ".tsx"}

        for line_no, line in lines:
            lowered = line.lower()
            matched_topics: list[TopicState] = []
            for topic_id, topic in topic_map.items():
                hits = _matches(lowered, topic["keywords"])
                if not hits:
                    continue
                state = states[topic_id]
                _update_topic_hits(state, ",".join(hits), project_name, is_code_file, is_history=False)
                matched_topics.append(state)
                if len(state.evidence) < 6:
                    state.evidence.append(
                        Evidence(
                            file=str(file_path.relative_to(workspace)),
                            line_no=line_no,
                            snippet=_safe_snippet(line),
                            topic_hit=hits[0],
                        )
                    )
            if matched_topics:
                business_count = len(_matches(lowered, BUSINESS_WORDS))
                novelty_count = len(_matches(lowered, NOVELTY_WORDS))
                if business_count:
                    for state in matched_topics:
                        state.business_hits += business_count
                if novelty_count:
                    for state in matched_topics:
                        state.novelty_hits += novelty_count

    # History documents
    for history_file in history_files:
        if not history_file.exists():
            continue
        project_name = "history"
        for line_no, line in _read_lines(history_file):
            lowered = line.lower()
            matched_topics: list[TopicState] = []
            for topic_id, topic in topic_map.items():
                hits = _matches(lowered, topic["keywords"])
                if not hits:
                    continue
                state = states[topic_id]
                _update_topic_hits(state, ",".join(hits), project_name, is_code=False, is_history=True)
                matched_topics.append(state)
                if len(state.evidence) < 6:
                    state.evidence.append(
                        Evidence(
                            file=f"{history_file.name}",
                            line_no=line_no,
                            snippet=_safe_snippet(line),
                            topic_hit=hits[0],
                        )
                    )
            if matched_topics:
                business_count = len(_matches(lowered, BUSINESS_WORDS))
                novelty_count = len(_matches(lowered, NOVELTY_WORDS))
                if business_count:
                    for state in matched_topics:
                        state.business_hits += business_count
                if novelty_count:
                    for state in matched_topics:
                        state.novelty_hits += novelty_count

    for state in states.values():
        state.project_count = len(state.project_hits)

    return states


# ---------------------------------------------------------------------------
# Workspace summary for LLM topic discovery
# ---------------------------------------------------------------------------

def collect_workspace_summary(
    workspace: Path,
    extensions: List[str],
    ignore_dirs: set[str],
    max_files: int = 200,
) -> WorkspaceSummary:
    """Build a concise workspace summary suitable for LLM topic discovery input."""
    ext_set = {item.lower().lstrip(".") for item in extensions}
    file_paths = list(_iter_files(workspace, ext_set, set(ignore_dirs), max_files))

    projects: dict[str, int] = {}
    file_types: dict[str, int] = {}
    snippets: list[dict] = []
    readme_excerpts: list[str] = []

    for fp in file_paths:
        project = _infer_project_name(workspace, fp)
        projects[project] = projects.get(project, 0) + 1
        ext = fp.suffix.lower().lstrip(".")
        if ext:
            file_types[ext] = file_types.get(ext, 0) + 1

        # Collect README excerpts
        if fp.name.upper() in {"README.MD", "PROJECT_OVERVIEW.MD", "CLAUDE.MD"}:
            lines = _read_lines(fp)
            excerpt_lines = [line for _, line in lines[:30] if line.strip()]
            if excerpt_lines:
                readme_excerpts.append("\n".join(excerpt_lines[:15]))

        # Collect representative snippets (first few meaningful lines)
        if len(snippets) < 20 and fp.suffix.lower() in {".py", ".ts", ".java", ".kt", ".tsx"}:
            lines = _read_lines(fp)
            meaningful = [line for _, line in lines[:20] if line.strip() and not line.strip().startswith("#")]
            if meaningful:
                snippets.append({
                    "file": str(fp.relative_to(workspace)),
                    "project": project,
                    "lines": meaningful[:5],
                })

    return WorkspaceSummary(
        projects=projects,
        file_types=file_types,
        representative_snippets=snippets,
        readme_excerpts=readme_excerpts[:5],
        total_files=len(file_paths),
    )
