"""LLM-driven autonomous topic discovery.

Replaces the hardcoded ``TOPICS`` dict in engine.py with LLM-based
topic discovery.  When the LLM command is not configured, falls back
to a seed JSON file or built-in legacy topics.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .config import LLM_TOPIC_DISCOVERY_CMD_ENV
from .llm_client import run_llm_command
from .types import LLMResult, TopicDiscovery, WorkspaceSummary

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Legacy seed topics (kept as fallback when LLM is unavailable)
# ---------------------------------------------------------------------------

LEGACY_TOPICS: dict[str, dict[str, Any]] = {
    "turn_taking": {
        "name": "대화 턴테이킹/백채널 최적화",
        "keywords": [
            "turn", "turn-taking", "턴", "인터럽트", "interrupt", "backchannel", "백채널",
            "mid-turn", "end of turn", "eos", "premature", "음성", "vad", "silero",
            "말 끊김", "pausing", "pause", "중단", "말 끊기",
        ],
    },
    "proactive_dialogue": {
        "name": "선제적/예측형 대화 시스템",
        "keywords": [
            "pre", "prefetch", "prefetch", "예측", "선제", "대화 예측", "중간", "interim",
            "의도", "intent", "trajectory", "빠른 응답", "latency", "지연", "체감",
        ],
    },
    "tool_use": {
        "name": "음성 네이티브 업무 실행 도구",
        "keywords": [
            "tool", "도구", "함수", "function calling", "tool use", "예약", "결제",
            "업무", "task", "workflow", "실행", "액션", "slot", "calendar", "api",
        ],
    },
    "summarization": {
        "name": "실시간 대화 요약 및 액션 추출",
        "keywords": [
            "summariz", "요약", "summary", "action", "액션", "리포트", "기록",
            "회의록", "요약", "transcript", "정리", "메모", "핵심",
        ],
    },
    "hallucination": {
        "name": "응답 근거 검증/환각 탐지",
        "keywords": [
            "halluc", "환각", "grounding", "근거", "검증", "fact", "factoid",
            "nli", "신뢰성", "안전", "정합", "근거 기반",
        ],
    },
    "empathy": {
        "name": "감정 인식 및 공감형 응답",
        "keywords": [
            "emotion", "감정", "공감", "empath", "tone", "mood",
            "감성", "sarcasm", "voice style", "스타일", "표현", "톤",
        ],
    },
    "topic_routing": {
        "name": "대화 주제 추적 및 에이전트 라우팅",
        "keywords": [
            "topic", "주제", "routing", "router", "supervisor", "멀티에이전트",
            "worker", "도메인", "분기", "전환", "라투라", "supervisor",
        ],
    },
    "aesc_preprocessing": {
        "name": "서버 사이드 오디오 전처리/노이즈 제거",
        "keywords": [
            "aec", "noise", "denoise", "enhance", "preprocess", "전처리", "에코", "echo",
            "g.711", "bwe", "agc", "audio", "tts", "stt", "녹음", "신호",
        ],
    },
    "disfluency": {
        "name": "비유창성 인식 및 인지 적응 대화",
        "keywords": [
            "disfluency", "비유창", "발화", "말더듬", "filler", "stutter", "반복",
            "재시도", "자기수정", "재귀", "인지", "cognitive", "인지 부하", "적응",
        ],
    },
    "foundation": {
        "name": "한국어 노인 음성 기반 모델/파운데이션 AI",
        "keywords": [
            "foundation", "SSL", "wav2vec", "hubert", "wavlm", "fine-tune", "파운데이션",
            "elder", "senior", "노인", "frailty", "인지", "투입", "fine tuning", "온보",
            "onnx", "로컬",
        ],
    },
    "deepfake": {
        "name": "딥페이크 탐지 및 보이스피싱 방지",
        "keywords": [
            "deepfake", "spoof", "liveness", "사칭", "피싱", "음성 인증",
            "ASV", "anti-spoof", "Pindrop", "피해", "fraud", "보안",
        ],
    },
    "voice_cloning": {
        "name": "개인화/음성 클로닝 및 보이스 보존",
        "keywords": [
            "clone", "cloning", "voice cloning", "개인화", "브랜드", "프로파일", "화자",
            "identity", "speaker", "cosy", "tts", "style", "유사도", "워터마크",
        ],
    },
    "context_biasing": {
        "name": "도메인 적응 ASR/컨텍스트 바이어싱",
        "keywords": [
            "biasing", "keyterm", "도메인", "context", "특화", "전문용어", "ASR", "단어사전",
            "tcpgen", "stream", "speech recognition", "정합", "recognition",
        ],
    },
}


# ---------------------------------------------------------------------------
# LLM topic discovery payload
# ---------------------------------------------------------------------------

_TOPIC_DISCOVERY_SYSTEM_PROMPT = """\
당신은 음성 AI R&D 프로젝트의 연구 주제 탐색 전문가입니다.

## 역할
주어진 워크스페이스 구조, 코드 스니펫, README/문서 발췌, 이전 보고서 이력을 분석하여
가장 유망한 R&D 연구 주제를 자율적으로 발견합니다.

## 출력 요구사항
반드시 아래 JSON 스키마를 따르세요:
{
  "topics": [
    {
      "topic_id": "snake_case 식별자",
      "topic_name": "한국어 토픽 이름",
      "description": "2-3문장 설명",
      "suggested_keywords": ["keyword1", "keyword2", ...],
      "search_terms": {
        "arxiv": "arXiv 검색 쿼리",
        "crossref": "Crossref 검색 쿼리",
        "web": "일반 웹 검색 쿼리"
      },
      "rationale": "이 주제를 선정한 이유",
      "confidence": 0.0~1.0
    }
  ]
}

## 제약 조건
- 토픽 수: {min_topics}~{max_topics}개
- 도메인: {domain}
- 각 토픽에 10~20개의 키워드를 포함 (한국어/영어 혼용 가능)
- confidence는 워크스페이스 증거 기반 (코드/문서에 증거 많을수록 높음)

## 근거 기반 규칙 (CRITICAL)
- 모든 토픽은 제공된 workspace_summary (코드 스니펫, README, 프로젝트 구조) 또는 history_context에서 근거를 찾을 수 있어야 합니다
- 워크스페이스에 근거가 없는 토픽은 confidence를 0.3 이하로 설정하세요
- rationale에 반드시 근거 출처를 명시하세요 (예: "프로젝트 OraAIServer의 코드 스니펫에서 embedding 관련 코드 확인")
- 제공된 데이터에 없는 프로젝트명이나 파일명을 만들어내지 마세요
"""


def _build_discovery_payload(
    workspace_summary: WorkspaceSummary,
    history_context: list[dict[str, Any]] | None = None,
    min_topics: int = 6,
    max_topics: int = 14,
    domain: str = "voice AI",
) -> dict[str, Any]:
    """Build the JSON payload for the LLM topic discovery call."""
    return {
        "version": "llm-topic-discovery-v1",
        "workspace_summary": {
            "projects": workspace_summary.projects,
            "file_types": workspace_summary.file_types,
            "total_files": workspace_summary.total_files,
            "representative_snippets": workspace_summary.representative_snippets,
            "readme_excerpts": workspace_summary.readme_excerpts,
        },
        "history_context": history_context or [],
        "constraints": {
            "min_topics": min_topics,
            "max_topics": max_topics,
            "domain": domain,
        },
    }


def _parse_discovery_result(result: LLMResult) -> list[TopicDiscovery]:
    """Parse LLM response into TopicDiscovery list."""
    if result.status != "ok":
        logger.warning("LLM topic discovery failed: %s", result.parsed)
        return []

    topics_raw = result.parsed.get("topics", [])
    if not isinstance(topics_raw, list):
        logger.warning("LLM returned non-list 'topics': %s", type(topics_raw).__name__)
        return []

    discoveries: list[TopicDiscovery] = []
    for item in topics_raw:
        if not isinstance(item, dict):
            continue
        topic_id = item.get("topic_id", "").strip()
        if not topic_id:
            continue

        search_terms = item.get("search_terms", {})
        if not isinstance(search_terms, dict):
            search_terms = {}

        discoveries.append(TopicDiscovery(
            topic_id=topic_id,
            topic_name=item.get("topic_name", topic_id),
            description=item.get("description", ""),
            suggested_keywords=item.get("suggested_keywords", []),
            search_terms=search_terms,
            rationale=item.get("rationale", ""),
            confidence=float(item.get("confidence", 0.5)),
            discovered_by="llm",
        ))

    return discoveries


# ---------------------------------------------------------------------------
# Seed JSON loader
# ---------------------------------------------------------------------------

def _load_seed_json(seed_path: Path) -> list[TopicDiscovery]:
    """Load topics from a seed JSON file (optional user-provided override)."""
    if not seed_path.is_file():
        return []
    try:
        with seed_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read seed JSON %s: %s", seed_path, exc)
        return []

    if not isinstance(data, dict):
        return []

    topics_raw = data.get("topics", data)
    if isinstance(topics_raw, dict):
        # Handle {topic_id: {name, keywords}} format
        discoveries: list[TopicDiscovery] = []
        for topic_id, details in topics_raw.items():
            if not isinstance(details, dict):
                continue
            discoveries.append(TopicDiscovery(
                topic_id=topic_id,
                topic_name=details.get("name", topic_id),
                description=details.get("description", ""),
                suggested_keywords=details.get("keywords", []),
                search_terms=details.get("search_terms", {}),
                rationale="seed JSON",
                confidence=0.5,
                discovered_by="seed_json",
            ))
        return discoveries

    if isinstance(topics_raw, list):
        return _parse_discovery_result(
            LLMResult(status="ok", parsed={"topics": topics_raw})
        )

    return []


# ---------------------------------------------------------------------------
# Legacy fallback
# ---------------------------------------------------------------------------

def _legacy_topics_as_discoveries(domain: str = "voice AI") -> list[TopicDiscovery]:
    """Convert built-in LEGACY_TOPICS to TopicDiscovery list.

    When the requested *domain* differs from the built-in "voice AI" focus,
    lower the confidence so downstream ranking prefers LLM-discovered topics
    when they become available.
    """
    is_default_domain = domain.strip().lower() in ("voice ai", "voice", "")
    base_confidence = 0.7 if is_default_domain else 0.3
    discoveries: list[TopicDiscovery] = []
    for topic_id, details in LEGACY_TOPICS.items():
        discoveries.append(TopicDiscovery(
            topic_id=topic_id,
            topic_name=details["name"],
            description="",
            suggested_keywords=details.get("keywords", []),
            search_terms={},
            rationale="legacy hardcoded fallback",
            confidence=base_confidence,
            discovered_by="legacy_fallback",
        ))
    return discoveries


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def discover_topics(
    workspace_summary: WorkspaceSummary | None = None,
    llm_command: str | None = None,
    llm_timeout: float = 12.0,
    history_context: list[dict[str, Any]] | None = None,
    seed_json_path: Path | None = None,
    min_topics: int = 6,
    max_topics: int = 14,
    domain: str = "voice AI",
) -> list[TopicDiscovery]:
    """Discover R&D topics using LLM, seed JSON, or legacy fallback.

    Priority order:
    1. LLM command (if configured and workspace_summary provided)
    2. Seed JSON file (if provided and exists)
    3. Legacy hardcoded topics

    Returns a list of TopicDiscovery objects.
    """
    # 1. Try LLM discovery
    resolved_cmd = llm_command
    if not resolved_cmd:
        resolved_cmd = os.getenv(LLM_TOPIC_DISCOVERY_CMD_ENV, "").strip() or None

    if resolved_cmd and workspace_summary is not None:
        logger.info("Attempting LLM topic discovery via: %s", resolved_cmd)

        system_prompt = _TOPIC_DISCOVERY_SYSTEM_PROMPT.format(
            min_topics=min_topics,
            max_topics=max_topics,
            domain=domain,
        )
        payload = _build_discovery_payload(
            workspace_summary=workspace_summary,
            history_context=history_context,
            min_topics=min_topics,
            max_topics=max_topics,
            domain=domain,
        )

        result = run_llm_command(
            payload=payload,
            command=resolved_cmd,
            timeout=llm_timeout,
            system_prompt=system_prompt,
        )

        discoveries = _parse_discovery_result(result)
        if discoveries:
            logger.info("LLM discovered %d topics", len(discoveries))
            return discoveries
        logger.warning("LLM topic discovery returned no topics; falling back")

    # 2. Try seed JSON
    if seed_json_path:
        discoveries = _load_seed_json(seed_json_path)
        if discoveries:
            logger.info("Loaded %d topics from seed JSON: %s", len(discoveries), seed_json_path)
            return discoveries

    # 3. Legacy fallback
    logger.info("Using legacy hardcoded topics as fallback (domain=%s)", domain)
    return _legacy_topics_as_discoveries(domain=domain)


def topics_to_dict(discoveries: list[TopicDiscovery]) -> dict[str, dict[str, Any]]:
    """Convert TopicDiscovery list to legacy TOPICS dict format.

    Useful for backward compatibility with code that expects
    ``{topic_id: {"name": ..., "keywords": [...]}}`` format.
    """
    return {
        td.topic_id: {
            "name": td.topic_name,
            "keywords": td.suggested_keywords,
        }
        for td in discoveries
    }


def topics_to_keywords(discoveries: list[TopicDiscovery]) -> dict[str, list[str]]:
    """Convert TopicDiscovery list to ``{topic_id: [keywords]}`` map."""
    return {
        td.topic_id: td.suggested_keywords
        for td in discoveries
    }
