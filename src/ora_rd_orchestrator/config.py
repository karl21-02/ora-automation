"""Orchestrator configuration: constants, environment variables, and pipeline settings."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Project file / noise filters (true configuration, not hardcoded rules)
# ---------------------------------------------------------------------------

PROJECT_FILES = {
    "README.md",
    "RULE.md",
    "CLAUDE.md",
    "PROJECT_OVERVIEW.md",
    "GEMINI_CONTEXT.md",
}

_NOISY_FILENAMES = {
    "package-lock.json",
    "yarn.lock",
    "package.json",
    "pnpm-lock.yaml",
    "gradle.lockfile",
    "gradlew",
    "build.gradle",
    "build.gradle.kts",
    "pom.xml",
}

# ---------------------------------------------------------------------------
# Service alias map
# ---------------------------------------------------------------------------

SERVICE_ALIAS_MAP: dict[str, list[str]] = {
    "b2b": ["orab2bserver", "orab2bserver", "ora-b2b", "b2bserver"],
    "b2b-android": ["orab2bandroid", "ora-b2b-android", "mobile", "android"],
    "b2c": [
        "orawebappfrontend",
        "orawebappserver",
        "oramainfrontend",
        "orab2c",
        "ora-admin-frontend",
        "oraadminfrontend",
    ],
    "ai": ["oraaiserver", "oraiserver", "ai", "llm_server", "tts_server"],
    "telecom": ["oraserver", "oraserver", "telecom", "callserver"],
    "docs": ["oradocs", "ora-docs", "docs", "readme"],
}
SERVICE_SCOPE_LABELS = {service: service for service in SERVICE_ALIAS_MAP}
SERVICE_SCOPE_DEFAULT: tuple[str, ...] = ("b2b", "b2c", "ai", "telecom", "b2b-android")

# Pre-built reverse lookup: normalized alias → canonical scope name
_ALIAS_REVERSE_MAP: dict[str, str] = {}
for _scope, _aliases in SERVICE_ALIAS_MAP.items():
    _scope_key = _scope.strip().lower().replace("-", "")
    _ALIAS_REVERSE_MAP[_scope_key] = _scope
    for _alias in _aliases:
        _alias_key = _alias.strip().lower().replace("-", "")
        if _alias_key:
            _ALIAS_REVERSE_MAP[_alias_key] = _scope

# ---------------------------------------------------------------------------
# Research API URLs and defaults
# ---------------------------------------------------------------------------

ARXIV_SEARCH_API_URL = "https://export.arxiv.org/api/query"
ARXIV_ABS_PREFIX = "https://arxiv.org/abs/"
ARXIV_SEARCH_PROVIDER = "arXiv API"
ARXIV_SEARCH_TIMEOUT_SECONDS = 8.0
ARXIV_SEARCH_DEFAULT_MAX_RESULTS = 10
ARXIV_SEARCH_ENABLED_ENV = "ORA_RD_RESEARCH_ARXIV_SEARCH"
ARXIV_SEARCH_ENABLED_ENV_OLD = "ORA_RD_ARXIV_SEARCH_ENABLED"

CROSSREF_SEARCH_API_URL = "https://api.crossref.org/works"
CROSSREF_SEARCH_PROVIDER = "Crossref API"
CROSSREF_SEARCH_TIMEOUT_SECONDS = 8.0
CROSSREF_SEARCH_DEFAULT_MAX_RESULTS = 6
CROSSREF_SEARCH_ENABLED_ENV = "ORA_RD_RESEARCH_CROSSREF_SEARCH"

OPENALEX_SEARCH_API_URL = "https://api.openalex.org/works"
OPENALEX_SEARCH_PROVIDER = "OpenAlex API"
OPENALEX_SEARCH_TIMEOUT_SECONDS = 8.0
OPENALEX_SEARCH_DEFAULT_MAX_RESULTS = 6
OPENALEX_SEARCH_ENABLED_ENV = "ORA_RD_RESEARCH_OPENALEX_SEARCH"
OPENALEX_SEARCH_EMAIL = "research@ora.ai"

# Semantic Scholar API (free, no auth, reliable JSON)
SEMANTIC_SCHOLAR_SEARCH_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
SEMANTIC_SCHOLAR_SEARCH_PROVIDER = "Semantic Scholar API"
SEMANTIC_SCHOLAR_SEARCH_TIMEOUT_SECONDS = 10.0
SEMANTIC_SCHOLAR_SEARCH_DEFAULT_MAX_RESULTS = 5
SEMANTIC_SCHOLAR_SEARCH_ENABLED_ENV = "ORA_RD_RESEARCH_SEMANTIC_SCHOLAR_SEARCH"

# Web search (Google Scholar via Scrapling)
WEB_SEARCH_ENABLED_ENV = "ORA_RD_RESEARCH_WEB_SEARCH"
WEB_SEARCH_PROVIDER = "Google Scholar"
WEB_SEARCH_TIMEOUT_SECONDS = 10.0
WEB_SEARCH_DEFAULT_MAX_RESULTS = 3
WEB_SEARCH_BASE_URL = "https://scholar.google.com/scholar"

WEB_FALLBACK_SEARCH_QUERY_PREFIX = "site:arxiv.org"

# ---------------------------------------------------------------------------
# Orchestration profile / stages
# ---------------------------------------------------------------------------

ORCHESTRATION_PROFILE_DEFAULT = "standard"
ORCHESTRATION_PROFILE_STRICT = "strict"
ORCHESTRATION_STAGE_ANALYSIS = "analysis"
ORCHESTRATION_STAGE_DELIBERATION = "deliberation"
ORCHESTRATION_STAGE_EXECUTION = "execution"
ORCHESTRATION_STAGES_DEFAULT = [
    ORCHESTRATION_STAGE_ANALYSIS,
    ORCHESTRATION_STAGE_DELIBERATION,
    ORCHESTRATION_STAGE_EXECUTION,
]
ORCHESTRATION_STAGES_SET = {ORCHESTRATION_STAGE_ANALYSIS, ORCHESTRATION_STAGE_DELIBERATION, ORCHESTRATION_STAGE_EXECUTION}
ORCHESTRATION_PROFILE_LABELS = {ORCHESTRATION_PROFILE_DEFAULT, ORCHESTRATION_PROFILE_STRICT}
ORCHESTRATION_PROFILE_ROUND_LIMITS = {
    ORCHESTRATION_PROFILE_DEFAULT: 999,
    ORCHESTRATION_PROFILE_STRICT: 999,
}

# ---------------------------------------------------------------------------
# Pipeline labels
# ---------------------------------------------------------------------------

PIPELINE_FAIL_LABEL_SKIP = "SKIP"
PIPELINE_FAIL_LABEL_RETRY = "RETRY"
PIPELINE_FAIL_LABEL_STOP = "STOP"
PIPELINE_RETRY_LIMIT_DEFAULT = 2
PIPELINE_RETRY_DELAY_SECONDS = 1.2
DECISION_DUE_DEFAULT_DAYS = 14

LLM_DELIBERATION_FAIL_LABEL_LOW_RISK = PIPELINE_FAIL_LABEL_SKIP
LLM_DELIBERATION_FAIL_LABEL_MEDIUM_RISK = PIPELINE_FAIL_LABEL_RETRY
LLM_DELIBERATION_FAIL_LABEL_HIGH_RISK = PIPELINE_FAIL_LABEL_STOP

# ---------------------------------------------------------------------------
# LLM command env vars
# ---------------------------------------------------------------------------

LLM_DELIBERATION_CMD_ENV = "ORA_RD_LLM_DELIBERATION_CMD"
LLM_DELIBERATION_TIMEOUT_SECONDS = 8.0
LLM_DELIBERATION_FALLBACK_MIN_ROUND = 1
LLM_CONSENSUS_CMD_ENV = "ORA_RD_LLM_CONSENSUS_CMD"
LLM_CONSENSUS_TIMEOUT_SECONDS = 8.0
LLM_CONSENSUS_MIN_EVIDENCE = 2
LLM_CONSENSUS_MIN_CODE_DOC_SIGNAL = 2
LLM_CONSENSUS_MAX_RISK = 8.0

# New: LLM topic discovery and scoring
LLM_TOPIC_DISCOVERY_CMD_ENV = "ORA_RD_LLM_TOPIC_DISCOVERY_CMD"
LLM_SCORING_CMD_ENV = "ORA_RD_LLM_SCORING_CMD"

# LLM provider configuration
LLM_PREFER_SUBPROCESS_ENV = "ORA_RD_LLM_PREFER_SUBPROCESS"
GEMINI_MODEL_LITE_ENV = "ORA_RD_GEMINI_MODEL_LITE"
GEMINI_MODEL_FLASH_ENV = "ORA_RD_GEMINI_MODEL_FLASH"
GEMINI_MODEL_PRO_ENV = "ORA_RD_GEMINI_MODEL_PRO"

# LLM report section generation
LLM_REPORT_SECTION_TIMEOUT_SECONDS = 45.0
LLM_REPORT_SECTION_CMD_ENV = "ORA_RD_LLM_REPORT_CMD"

# ---------------------------------------------------------------------------
# Persona directory
# ---------------------------------------------------------------------------

PERSONA_DIR_ENV = "ORA_RD_PERSONA_DIR"

def default_persona_dir() -> Path:
    """Return the default persona YAML directory (package-internal personas/)."""
    env = os.getenv(PERSONA_DIR_ENV, "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).parent / "personas"

# ---------------------------------------------------------------------------
# Debate constants
# ---------------------------------------------------------------------------

DEBATE_ROUNDS_DEFAULT = 2
DEBATE_TOPIC_WINDOW = 4
DEBATE_MESSAGE_COUNT_PER_AGENT = 3
DEBATE_MAX_MESSAGES_PER_ROUND = 12
DEBATE_INFLUENCE_SELF = 0.22
DEBATE_INFLUENCE_OTHER = 0.28
DEBATE_SUPPORT_DELTA = 0.68
DEBATE_CHALLENGE_DELTA = -0.76
DEBATE_STABLE_TOP3_GAP = 0.18
DEBATE_STABLE_OVERLAP = 2
DEBATE_CONVERGENCE_ROUNDS = 2

# ---------------------------------------------------------------------------
# Hierarchical pipeline constants
# ---------------------------------------------------------------------------

SUBORDINATE_BLEND_DEFAULT = 0.60
QA_GATE_THRESHOLD_DEFAULT = 3.5
QA_GATE_PENALTY = 0.10

# Legacy flat-mode agent set
FLAT_MODE_AGENTS = {"CEO", "Planner", "Developer", "Researcher", "PM", "Ops", "QA"}

# Legacy flat-mode final weights
AGENT_FINAL_WEIGHTS = {
    "CEO": 0.25,
    "Planner": 0.17,
    "Developer": 0.16,
    "Researcher": 0.15,
    "PM": 0.12,
    "Ops": 0.10,
    "QA": 0.05,
}

# Hierarchical final weights
HIERARCHICAL_FINAL_WEIGHTS: dict[str, object] = {
    "tier4_weight": 0.30,
    "tier3_weight": 0.35,
    "tier2_weight": 0.25,
    "tier1_weight": 0.10,
    "tier2_lead_weights": {
        "Planner": 0.30,
        "PM": 0.25,
        "Ops": 0.25,
        "QALead": 0.20,
    },
}

# Hierarchical trust map
HIERARCHICAL_TRUST: dict[str, dict[str, float]] = {
    "CEO": {"Planner": 0.85, "PM": 0.88, "Ops": 0.82, "QALead": 0.80},
    "Planner": {"Researcher": 0.88, "DataScientist": 0.82},
    "PM": {"ProductDesigner": 0.85, "MarketAnalyst": 0.82},
    "Ops": {"Developer": 0.85, "DevOpsSRE": 0.88, "FinanceAnalyst": 0.78},
    "QALead": {"SecuritySpecialist": 0.90, "Linguist": 0.82, "QA": 0.85},
}

# Tier 2 domain map
TIER_2_DOMAIN_MAP: dict[str, dict[str, object]] = {
    "Planner": {
        "tier1_agents": ["Researcher", "DataScientist"],
        "intra_weights": {"Researcher": 0.55, "DataScientist": 0.45},
        "aggregation": "weighted_mean",
    },
    "PM": {
        "tier1_agents": ["ProductDesigner", "MarketAnalyst"],
        "intra_weights": {"ProductDesigner": 0.50, "MarketAnalyst": 0.50},
        "aggregation": "weighted_mean",
    },
    "Ops": {
        "tier1_agents": ["Developer", "DevOpsSRE", "FinanceAnalyst"],
        "intra_weights": {"Developer": 0.40, "DevOpsSRE": 0.35, "FinanceAnalyst": 0.25},
        "aggregation": "weighted_mean",
    },
    "QALead": {
        "tier1_agents": ["SecuritySpecialist", "Linguist", "QA"],
        "intra_weights": {"SecuritySpecialist": 0.45, "Linguist": 0.35, "QA": 0.20},
        "aggregation": "min_gated_mean",
        "gate_threshold": 3.5,
    },
}

# ---------------------------------------------------------------------------
# Environment variable helpers
# ---------------------------------------------------------------------------

def _bool_env(name: str, default: bool = True) -> bool:
    value = os.getenv(name, str(int(default))).strip().lower()
    return value not in {"0", "false", "no", "off"}


def _read_bool_env(name: str, default: bool, aliases: tuple[str, ...] = ()) -> bool:
    candidates = (name, *aliases)
    for key in candidates:
        if key in os.environ:
            return _bool_env(key, default=default)
    return default


def _read_int_env(name: str, default: int, aliases: tuple[str, ...] = ()) -> int:
    candidates = (name, *aliases)
    for key in candidates:
        if key not in os.environ:
            continue
        try:
            return max(1, int(os.getenv(key, str(default)).strip()))
        except ValueError:
            continue
    return default


def _read_float_env(name: str, default: float, aliases: tuple[str, ...] = ()) -> float:
    candidates = (name, *aliases)
    for key in candidates:
        if key not in os.environ:
            continue
        try:
            return max(1.0, float(os.getenv(key, str(default)).strip()))
        except ValueError:
            continue
    return default


# ---------------------------------------------------------------------------
# Orchestration stage / scope helpers
# ---------------------------------------------------------------------------

def _normalize_text_token(value: str) -> str:
    return value.strip().lower().replace("-", "")


def _parse_service_scopes(value: str | Iterable[str] | None) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        raw_tokens = [token.strip() for token in value.split(",") if token.strip()]
    else:
        raw_tokens = [str(token).strip() for token in value if str(token).strip()]
    scope: set[str] = set()
    for item in raw_tokens:
        key = _normalize_text_token(item)
        if key:
            scope.add(key)
    return scope


def _normalize_services(value: Iterable[str] | None, fallback: set[str] | None = None) -> list[str]:
    if not value:
        return sorted(set(fallback or set()))
    normalized: set[str] = set()
    for item in value:
        key = _normalize_text_token(str(item))
        if key:
            normalized.add(key)
    return sorted(normalized)


def _service_alias_to_scope(service: str) -> str:
    key = _normalize_text_token(service)
    if not key:
        return ""
    return _ALIAS_REVERSE_MAP.get(key, key)


def _build_service_scope(service_scope: set[str] | list[str] | None) -> list[str]:
    normalized = _parse_service_scopes(service_scope)
    if not normalized:
        return sorted(set(SERVICE_SCOPE_DEFAULT))
    expanded: set[str] = set()
    for scope in normalized:
        resolved = _service_alias_to_scope(scope)
        if resolved:
            expanded.add(resolved)
    expanded.add("global")
    return sorted(expanded)


def _parse_orchestration_stages(value: str | Iterable[str] | None) -> list[str]:
    if value is None:
        return list(ORCHESTRATION_STAGES_DEFAULT)
    if isinstance(value, str):
        tokens = [token.strip() for token in value.split(",") if token.strip()]
    else:
        tokens = [str(token).strip() for token in value if str(token).strip()]

    stages: list[str] = []
    for token in tokens:
        normalized = token.lower().replace("_", "-")
        if normalized in ORCHESTRATION_STAGES_SET:
            stages.append(normalized)
    if not stages:
        return list(ORCHESTRATION_STAGES_DEFAULT)
    # de-dup preserve order
    seen = set[str]()
    ordered: list[str] = []
    for stage in stages:
        if stage in seen:
            continue
        ordered.append(stage)
        seen.add(stage)
    return ordered


def _parse_service_scope_tokens(value: str | Iterable[str] | None) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",") if item.strip()]
    else:
        items = [str(item).strip() for item in value if str(item).strip()]
    return {_normalize_text_token(item) for item in items}


def _normalize_stages(value: Iterable[str] | None, fallback: Iterable[str]) -> list[str]:
    fallback_set = [str(item).strip() for item in fallback if str(item).strip()]
    if value is None:
        return fallback_set
    parsed = _parse_orchestration_stages(value)
    if not parsed:
        return fallback_set
    return parsed
