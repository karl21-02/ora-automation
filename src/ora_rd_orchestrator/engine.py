from __future__ import annotations

import datetime as dt
import json
import math
import os
import uuid
import copy
import shlex
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import quote, quote_plus, urlencode
from urllib.request import Request, urlopen
from dataclasses import dataclass, field
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Callable, Dict, Iterable, List, Tuple


PROJECT_FILES = {
    "README.md",
    "RULE.md",
    "CLAUDE.md",
    "PROJECT_OVERVIEW.md",
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

TOPIC_CAUSE_LIBRARY: dict[str, list[str]] = {
    "turn_taking": [
        "TURN/interrupt 관련 실시간 탐지 파이프라인이 파편화되어 있을 때 발화 경계 오판이 반복될 가능성이 큼",
        "음성 구간 경계 계산이 고정 임계값 중심이면 사용자 말하기 습관별 성능 편차가 커짐",
    ],
    "proactive_dialogue": [
        "지연 감소를 위해 예측 단계와 실제 호출 계층이 분리되지 않으면 오류 전파가 커질 수 있음",
        "초기 프리패치가 부정확하면 음성 UX가 오히려 떨어질 수 있어 실패 모드 제어가 필요함",
    ],
    "tool_use": [
        "음성->의도 변환 이후 구조화 실행 모듈이 약하면 실제 주문/예약/결제로 이어지지 않음",
        "확인/재질문 플로우가 없으면 도메인 작업 실패율이 높아질 수 있음",
    ],
    "summarization": [
        "콜 종료 직후 즉시 요약을 생성할 때 누적 문맥 정합이 깨지면 액션 오해가 발생할 수 있음",
        "액션 항목 추출 규칙이 미정의 상태면 현장 투입 시 책임 추적이 어려움",
    ],
    "hallucination": [
        "근거 기반 검증 지점이 응답 직후에 없어도 한 번의 잘못된 단정이 신뢰도 하락으로 전이됨",
        "실시간 확인용 폴백 채널이 없으면 사용자 불신이 누적됨",
    ],
    "empathy": [
        "감정 분류 임계값이 완화되면 잘못된 톤 적용으로 오히려 신뢰도가 떨어짐",
        "TTS 감정 반영이 응답 생성 속도와 분리되지 않으면 체감 지연 증가 가능",
    ],
    "topic_routing": [
        "에이전트 라우팅이 대화 주제 전환을 빠르게 반영하지 못하면 반복 질의가 발생",
        "도메인 키워드 갱신 시점이 늦으면 라우팅 정확도가 곧바로 하락",
    ],
    "deepfake": [
        "초기 연결 단계에서 사칭 탐지 임계가 없으면 사고 대응 비용이 선형적으로 증가",
        "보이스피싱 대응은 false positive/false negative의 사업적 비용 균형이 매우 중요",
    ],
}

TOPIC_ACTION_LIBRARY: dict[str, list[dict[str, list[str]]]] = {
    "turn_taking": [
        {"phase": "0~2개월 (PoC)", "tasks": ["VAD threshold/event 추적 로그 스키마 통합", "발화 경계 오판 케이스 200건 이상 라벨링", "mid-turn pause 실패율 기준치 정의(예: 12% 이하 목표)"]},
        {"phase": "2~4개월 (통합)", "tasks": ["VAP 추정값과 기존 VAD 점수의 앙상블 스키마 적용", "백채널 타이밍 룰셋 점진 적용(A/B) 및 롤백 가드", "사용자군별(고령/장년) 반응 시간 파라미터 분리"]},
        {"phase": "4~6개월 (검증)", "tasks": ["음성 서비스별 조기중단율/재시도율 종단 분석", "실시간 대화 이탈 비용 최소화 지표 운영", "장비 품질 열화 구간 대응 정책 고정"]}
    ],
    "proactive_dialogue": [
        {"phase": "0~1개월 (요건 정합)", "tasks": ["interim transcript 파이프라인의 의도 예측 API 호출 지점 명세", "잘못된 prefetch 케이스를 감지하는 실패 규칙 정의", "실험군/대조군 실시간 라우팅 지표 설계"]},
        {"phase": "1~3개월 (예측 정제)", "tasks": ["대화 트랙별 예측 신뢰도 임계치 큐레이션", "사전 예측 시 실패 시나리오를 대체 응답으로 즉시 완화", "사용자 발화 길이/완결성에 따른 fallback 정책"]},
        {"phase": "3~5개월 (확장)", "tasks": ["RAG 선로딩 성능 비교(응답시간/정확도)", "개인화된 예상 의도 캐시 TTL 실험", "실제 KPI와 연결되는 오탐 비용 함정 제거"]},
    ],
}

TOPIC_KPI_LIBRARY: dict[str, list[str]] = {
    "turn_taking": [
        "premature cutoff 비율 월 30% 이상 감소",
        "백채널 오검출 비율 3% 이하 유지",
        "FCR(False Cutoff Rate) 2개월 연속 개선",
    ],
    "proactive_dialogue": [
        "interim 단계에서의 응답 예측 정확도(Top-1) 65% → 80%",
        "LLM 응답 최초 음성 출력 P50 지연 25% 감소",
        "오탐 prefetch로 인한 사용자 혼란률 월 1건 이하",
    ],
    "tool_use": [
        "음성 주문/예약 작업 성공률 85% → 95%",
        "확인 플로우 미스/리트라이율 30% 이상 감소",
        "실행 지연 P95 2초 이하 유지",
    ],
    "summarization": [
        "통화당 누락 action 아이템 0건률 90% 이상",
        "요약-리포트 생성 지연 P95 10초 이하",
        "수동 보정 요청률 20% 이상 감소",
    ],
}


TOPICS: dict[str, dict[str, List[str]]] = {
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
            "emotion", "감정", "공감", "empath", "tone", "tone", "t tone", "mood",
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
            "deepfake", "spoof", "liveness", "사칭", "피싱", "피싱", "음성 인증",
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
        {"title": "ASVspoof", "url": "https://www.asvspoof.org/"}
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

ARXIV_SEARCH_API_URL = "https://export.arxiv.org/api/query"
ARXIV_ABS_PREFIX = "https://arxiv.org/abs/"
ARXIV_SEARCH_PROVIDER = "arXiv API"
ARXIV_SEARCH_TIMEOUT_SECONDS = 8.0
ARXIV_SEARCH_DEFAULT_MAX_RESULTS = 6
ARXIV_SEARCH_ENABLED_ENV = "ORA_RD_RESEARCH_ARXIV_SEARCH"
ARXIV_SEARCH_ENABLED_ENV_OLD = "ORA_RD_ARXIV_SEARCH_ENABLED"

CROSSREF_SEARCH_API_URL = "https://api.crossref.org/works"
CROSSREF_SEARCH_PROVIDER = "Crossref API"
CROSSREF_SEARCH_TIMEOUT_SECONDS = 8.0
CROSSREF_SEARCH_DEFAULT_MAX_RESULTS = 4
CROSSREF_SEARCH_ENABLED_ENV = "ORA_RD_RESEARCH_CROSSREF_SEARCH"

OPENALEX_SEARCH_API_URL = "https://api.openalex.org/works"
OPENALEX_SEARCH_PROVIDER = "OpenAlex API"
OPENALEX_SEARCH_TIMEOUT_SECONDS = 8.0
OPENALEX_SEARCH_DEFAULT_MAX_RESULTS = 3
OPENALEX_SEARCH_ENABLED_ENV = "ORA_RD_RESEARCH_OPENALEX_SEARCH"
OPENALEX_SEARCH_EMAIL = "research@ora.ai"

WEB_FALLBACK_SEARCH_QUERY_PREFIX = "site:arxiv.org"
RESEARCH_QUERY_TAGS = [
    "voice AI",
    "speech AI",
    "telephony",
    "real-time dialogue",
    "speech recognition",
    "TTS",
]
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
LLM_DELIBERATION_CMD_ENV = "ORA_RD_LLM_DELIBERATION_CMD"
LLM_DELIBERATION_TIMEOUT_SECONDS = 8.0
LLM_DELIBERATION_FALLBACK_MIN_ROUND = 1
PIPELINE_FAIL_LABEL_SKIP = "SKIP"
PIPELINE_FAIL_LABEL_RETRY = "RETRY"
PIPELINE_FAIL_LABEL_STOP = "STOP"
ORCHESTRATION_STAGES_SET = {ORCHESTRATION_STAGE_ANALYSIS, ORCHESTRATION_STAGE_DELIBERATION, ORCHESTRATION_STAGE_EXECUTION}
ORCHESTRATION_PROFILE_LABELS = {ORCHESTRATION_PROFILE_DEFAULT, ORCHESTRATION_PROFILE_STRICT}
DECISION_DUE_DEFAULT_DAYS = 14
SERVICE_SCOPE_DEFAULT: tuple[str, ...] = ("b2b", "b2c", "ai", "telecom", "b2b-android")
ORCHESTRATION_PROFILE_ROUND_LIMITS = {
    ORCHESTRATION_PROFILE_DEFAULT: 3,
    ORCHESTRATION_PROFILE_STRICT: 4,
}
PIPELINE_RETRY_LIMIT_DEFAULT = 2
PIPELINE_RETRY_DELAY_SECONDS = 1.2
LLM_DELIBERATION_FAIL_LABEL_LOW_RISK = PIPELINE_FAIL_LABEL_SKIP
LLM_DELIBERATION_FAIL_LABEL_MEDIUM_RISK = PIPELINE_FAIL_LABEL_RETRY
LLM_DELIBERATION_FAIL_LABEL_HIGH_RISK = PIPELINE_FAIL_LABEL_STOP
AGENT_FINAL_WEIGHTS = {
    "CEO": 0.25,
    "Planner": 0.17,
    "Developer": 0.16,
    "Researcher": 0.15,
    "PM": 0.12,
    "Ops": 0.10,
    "QA": 0.05,
}


def _agent_ids() -> list[str]:
    return list(AGENT_WEIGHTS.keys())


def _agent_score_key(agent: str) -> str:
    return agent.lower().replace(" ", "_")

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


SupportRule = Callable[["TopicState", dict[str, float]], bool]
ChallengeRule = Callable[["TopicState", dict[str, float]], bool]


def _supports_ceo_by_market_signal(state: "TopicState", features: dict[str, float]) -> bool:
    return state.business_hits >= 2 or state.project_count >= 2


def _supports_ceo_by_research_stability(state: "TopicState", features: dict[str, float]) -> bool:
    return state.code_hits + state.doc_hits >= 6


def _challenges_ceo_by_risk(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "risk_penalty") >= 6.8


def _challenges_ceo_by_research_gap(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "research_signal") < 4.4


def _supports_planner_by_novelty(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "novelty") >= 6.0


def _supports_planner_by_research_signal(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "research_signal") >= 6.0


def _challenges_planner_by_feasibility(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "feasibility") < 4.5


def _challenges_planner_by_code_deficit(state: "TopicState", features: dict[str, float]) -> bool:
    return state.code_hits < 2


def _supports_developer_by_feasibility(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "feasibility") >= 8.0


def _supports_developer_by_implementation_signal(state: "TopicState", features: dict[str, float]) -> bool:
    return state.code_hits >= 5


def _challenges_developer_by_feasibility(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "feasibility") < 4.0


def _challenges_developer_by_code_gap(state: "TopicState", features: dict[str, float]) -> bool:
    return state.code_hits < 1.5


# --- Researcher support/challenge (reused from Planner) ---

# --- PM support/challenge ---
def _supports_pm_by_market_signal(state: "TopicState", features: dict[str, float]) -> bool:
    return state.business_hits >= 2 or state.project_count >= 2


def _challenges_pm_by_feasibility(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "feasibility") < 4.0


# --- Ops support/challenge ---
def _supports_ops_by_stability(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "feasibility") >= 7.0 and _feature_value(features, "risk_penalty") < 4.0


def _challenges_ops_by_risk(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "risk_penalty") >= 6.0


# --- SecuritySpecialist support/challenge ---
def _supports_security_by_low_risk(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "risk_penalty") < 3.0 and state.code_hits >= 3


def _challenges_security_by_high_risk(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "risk_penalty") >= 5.5


# --- Linguist support/challenge ---
def _supports_linguist_by_novelty(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "novelty") >= 5.5 and state.doc_hits >= 2


def _challenges_linguist_by_weak_docs(state: "TopicState", features: dict[str, float]) -> bool:
    return state.doc_hits < 1 and _feature_value(features, "novelty") < 4.0


# --- MarketAnalyst support/challenge ---
def _supports_market_by_business(state: "TopicState", features: dict[str, float]) -> bool:
    return state.business_hits >= 3 and _feature_value(features, "impact") >= 6.0


def _challenges_market_by_low_impact(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "impact") < 4.5 and state.business_hits < 1


# --- FinanceAnalyst support/challenge ---
def _supports_finance_by_roi(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "feasibility") >= 6.5 and state.business_hits >= 2


def _challenges_finance_by_cost(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "feasibility") < 4.0 and _feature_value(features, "risk_penalty") >= 5.0


# --- ProductDesigner support/challenge ---
def _supports_ux_by_impact(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "impact") >= 6.0 and state.keyword_hits >= 4


def _challenges_ux_by_low_impact(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "impact") < 4.0


# --- DataScientist support/challenge ---
def _supports_data_by_research(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "research_signal") >= 5.5 and state.history_hits >= 2


def _challenges_data_by_weak_signal(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "research_signal") < 3.5 and state.history_hits < 1


# --- DevOpsSRE support/challenge ---
def _supports_devops_by_infra(state: "TopicState", features: dict[str, float]) -> bool:
    return state.code_hits >= 4 and _feature_value(features, "feasibility") >= 6.0


def _challenges_devops_by_instability(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "risk_penalty") >= 5.5 and state.code_hits < 2


# --- QALead support/challenge ---
def _supports_qalead_by_quality(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "feasibility") >= 6.0 and _feature_value(features, "risk_penalty") < 4.0


def _challenges_qalead_by_risk(state: "TopicState", features: dict[str, float]) -> bool:
    return _feature_value(features, "risk_penalty") >= 5.0 or _feature_value(features, "feasibility") < 3.5


AGENT_DEFINITIONS: dict[str, dict[str, object]] = {
    "CEO": {
        "objective": "사업성 우선. 수주/ROI/과제 파이프라인 적중률",
        "weights": {
            "impact": 0.46,
            "novelty": 0.23,
            "feasibility": 0.14,
            "research_signal": 0.12,
            "risk": -0.05,
        },
        "supports": [_supports_ceo_by_market_signal, _supports_ceo_by_research_stability],
        "challenges": [_challenges_ceo_by_risk, _challenges_ceo_by_research_gap],
        "trust": {"CEO": 1.0, "Planner": 0.78, "Developer": 0.72},
        "decision_focus": [
            "시장성-수주 적합성",
            "다중 프로젝트 재사용성",
            "리스크 대비 투자 효율성",
        ],
        "tier": 4,
        "domain": None,
    },
    "Planner": {
        "objective": "체감 품질/확장성/장기 과제화 적합성",
        "weights": {
            "impact": 0.38,
            "feasibility": 0.26,
            "novelty": 0.18,
            "research_signal": 0.16,
            "risk": -0.08,
        },
        "supports": [_supports_planner_by_novelty, _supports_planner_by_research_signal],
        "challenges": [_challenges_planner_by_feasibility, _challenges_planner_by_code_deficit],
        "trust": {"CEO": 0.82, "Planner": 1.0, "Developer": 0.75},
        "decision_focus": [
            "사용자 체감 개선 우선순위",
            "기술 차별성 축적성",
            "연구 연계성/학술 신뢰도",
        ],
        "tier": 2,
        "domain": None,
    },
    "Developer": {
        "objective": "실무 PoC 가능성/재사용성/리스크 억제",
        "weights": {
            "feasibility": 0.52,
            "impact": 0.20,
            "novelty": 0.13,
            "research_signal": 0.05,
            "risk": -0.10,
        },
        "supports": [_supports_developer_by_feasibility, _supports_developer_by_implementation_signal],
        "challenges": [_challenges_developer_by_feasibility, _challenges_developer_by_code_gap],
        "trust": {"CEO": 0.71, "Planner": 0.76, "Developer": 1.0},
        "decision_focus": [
            "구현 난이도와 회귀 영향",
            "운영 연동 비용",
            "실행 가능한 PoC 크기",
        ],
        "tier": 1,
        "domain": "Ops",
    },
    "Researcher": {
        "objective": "논문 근거성/실험 엄밀성/기술 진척 속도 동시 평가",
        "weights": {
            "impact": 0.25,
            "novelty": 0.35,
            "feasibility": 0.20,
            "research_signal": 0.18,
            "risk": -0.10,
        },
        "supports": [_supports_planner_by_research_signal, _supports_planner_by_novelty],
        "challenges": [_challenges_planner_by_feasibility, _challenges_planner_by_code_deficit],
        "trust": {"CEO": 0.76, "Planner": 0.82, "Developer": 0.74, "Researcher": 1.0, "PM": 0.72, "QA": 0.70, "Ops": 0.71},
        "decision_focus": [
            "논문/자료의 최신성 및 재현성",
            "실험 설계 타당성",
            "근거 기반 가설-검증 정합",
        ],
        "tier": 1,
        "domain": "Planner",
    },
    "PM": {
        "objective": "릴리즈/로드맵 정렬, 우선순위 충돌 완화 및 성과 가시성 확보",
        "weights": {
            "impact": 0.40,
            "feasibility": 0.40,
            "novelty": 0.10,
            "research_signal": 0.05,
            "risk": -0.05,
        },
        "supports": [_supports_pm_by_market_signal],
        "challenges": [_challenges_pm_by_feasibility, _challenges_ceo_by_risk],
        "trust": {"CEO": 0.92, "Planner": 0.86, "Developer": 0.85, "Researcher": 0.82, "PM": 1.0, "QA": 0.82, "Ops": 0.79},
        "decision_focus": [
            "단기/중기 KPI 정렬",
            "요구사항 전달 안정성",
            "의사결정 속도와 팀 부하 관리",
        ],
        "tier": 2,
        "domain": None,
    },
    "Ops": {
        "objective": "운영 안정성, 장애 복구력, 롤백 조건과 운영 리스크 통제",
        "weights": {
            "impact": 0.28,
            "feasibility": 0.32,
            "novelty": 0.05,
            "research_signal": 0.05,
            "risk": 0.30,
        },
        "supports": [_supports_ops_by_stability, _supports_ceo_by_market_signal],
        "challenges": [_challenges_ops_by_risk, _challenges_planner_by_feasibility],
        "trust": {"CEO": 0.89, "Planner": 0.82, "Developer": 0.91, "Researcher": 0.78, "PM": 0.90, "QA": 0.88, "Ops": 1.0},
        "decision_focus": [
            "배포 롤백가시성",
            "서비스 분리/영향도 통제",
            "실패 모드 및 재발 대응성",
        ],
        "tier": 2,
        "domain": None,
    },
    "QA": {
        "objective": "품질 보증, 회귀 탐지, 테스트성/재현성 보장",
        "weights": {
            "feasibility": 0.24,
            "impact": 0.20,
            "novelty": 0.10,
            "research_signal": 0.12,
            "risk": 0.34,
        },
        "supports": [_supports_developer_by_feasibility],
        "challenges": [_challenges_developer_by_feasibility, _challenges_planner_by_feasibility],
        "trust": {"CEO": 0.75, "Planner": 0.80, "Developer": 0.85, "Researcher": 0.83, "PM": 0.84, "Ops": 0.91, "QA": 1.0},
        "decision_focus": [
            "수정 가능성 높은 실패 모드 탐지",
            "회귀 리스크 관리",
            "테스트 커버리지/자동화 적재적소 배치",
        ],
        "tier": 1,
        "domain": "QALead",
    },
    # --- Hierarchical-mode agents ---
    "SecuritySpecialist": {
        "objective": "보안 취약점 탐지, 규정 준수, 위협 모델링 평가",
        "weights": {
            "impact": 0.10,
            "novelty": 0.05,
            "feasibility": 0.15,
            "research_signal": 0.20,
            "risk": 0.50,
        },
        "supports": [_supports_security_by_low_risk],
        "challenges": [_challenges_security_by_high_risk],
        "trust": {"QALead": 0.90, "Ops": 0.85, "Developer": 0.80, "SecuritySpecialist": 1.0},
        "decision_focus": [
            "OWASP/보안 취약점 식별",
            "데이터 보호 규정 준수",
            "위협 모델링 완성도",
        ],
        "tier": 1,
        "domain": "QALead",
    },
    "Linguist": {
        "objective": "프롬프트/NLP 품질, 다국어 정합성, 음성 UX 언어 평가",
        "weights": {
            "impact": 0.20,
            "novelty": 0.30,
            "feasibility": 0.15,
            "research_signal": 0.25,
            "risk": 0.10,
        },
        "supports": [_supports_linguist_by_novelty],
        "challenges": [_challenges_linguist_by_weak_docs],
        "trust": {"QALead": 0.88, "PM": 0.82, "Researcher": 0.85, "Linguist": 1.0},
        "decision_focus": [
            "프롬프트/응답 자연스러움",
            "다국어 지원 품질",
            "음성 인터페이스 언어 적합성",
        ],
        "tier": 1,
        "domain": "QALead",
    },
    "MarketAnalyst": {
        "objective": "시장 동향, 경쟁사 분석, TAM/SAM/SOM 기반 기회 평가",
        "weights": {
            "impact": 0.45,
            "novelty": 0.15,
            "feasibility": 0.20,
            "research_signal": 0.15,
            "risk": 0.05,
        },
        "supports": [_supports_market_by_business],
        "challenges": [_challenges_market_by_low_impact],
        "trust": {"PM": 0.90, "CEO": 0.88, "Planner": 0.80, "MarketAnalyst": 1.0},
        "decision_focus": [
            "시장 규모 및 성장 잠재력",
            "경쟁사 대비 차별화",
            "고객 세그먼트 적합성",
        ],
        "tier": 1,
        "domain": "PM",
    },
    "FinanceAnalyst": {
        "objective": "ROI/비용 분석, 투자 회수 기간, 재무 리스크 평가",
        "weights": {
            "impact": 0.25,
            "novelty": 0.05,
            "feasibility": 0.35,
            "research_signal": 0.05,
            "risk": 0.30,
        },
        "supports": [_supports_finance_by_roi],
        "challenges": [_challenges_finance_by_cost],
        "trust": {"Ops": 0.88, "CEO": 0.90, "PM": 0.85, "FinanceAnalyst": 1.0},
        "decision_focus": [
            "ROI 및 투자 회수 기간",
            "인력/인프라 비용 대비 효과",
            "재무 리스크 및 기회비용",
        ],
        "tier": 1,
        "domain": "Ops",
    },
    "ProductDesigner": {
        "objective": "제품 UX/UI 설계, 사용자 여정, 디자인 시스템 평가",
        "weights": {
            "impact": 0.40,
            "novelty": 0.15,
            "feasibility": 0.25,
            "research_signal": 0.10,
            "risk": 0.10,
        },
        "supports": [_supports_ux_by_impact],
        "challenges": [_challenges_ux_by_low_impact],
        "trust": {"PM": 0.92, "DeveloperFrontend": 0.88, "Developer": 0.80, "ProductDesigner": 1.0},
        "decision_focus": [
            "사용자 체감 개선도",
            "디자인 시스템 일관성",
            "접근성 및 사용성 테스트 가능성",
        ],
        "tier": 1,
        "domain": "PM",
    },
    "DataScientist": {
        "objective": "데이터 파이프라인, 모델 성능, 실험 설계 및 통계 검증 평가",
        "weights": {
            "impact": 0.20,
            "novelty": 0.25,
            "feasibility": 0.15,
            "research_signal": 0.30,
            "risk": 0.10,
        },
        "supports": [_supports_data_by_research],
        "challenges": [_challenges_data_by_weak_signal],
        "trust": {"Planner": 0.85, "Researcher": 0.90, "Developer": 0.78, "DataScientist": 1.0},
        "decision_focus": [
            "데이터 품질 및 충분성",
            "모델 아키텍처 적합성",
            "실험 설계 통계적 타당성",
        ],
        "tier": 1,
        "domain": "Planner",
    },
    "DevOpsSRE": {
        "objective": "인프라 안정성, 배포 파이프라인, SLO/SLI 기반 신뢰성 평가",
        "weights": {
            "impact": 0.15,
            "novelty": 0.05,
            "feasibility": 0.30,
            "research_signal": 0.15,
            "risk": 0.35,
        },
        "supports": [_supports_devops_by_infra],
        "challenges": [_challenges_devops_by_instability],
        "trust": {"Ops": 0.92, "Developer": 0.88, "QALead": 0.82, "DevOpsSRE": 1.0},
        "decision_focus": [
            "배포 자동화/롤백 안정성",
            "인프라 확장성 및 비용",
            "SLO 달성 가능성",
        ],
        "tier": 1,
        "domain": "Ops",
    },
    "QALead": {
        "objective": "품질 게이트 관리, 하위 에이전트 품질 종합, 출시 판정 기준 관리",
        "weights": {
            "impact": 0.15,
            "novelty": 0.05,
            "feasibility": 0.20,
            "research_signal": 0.20,
            "risk": 0.40,
        },
        "supports": [_supports_qalead_by_quality],
        "challenges": [_challenges_qalead_by_risk],
        "trust": {"CEO": 0.80, "Planner": 0.82, "Developer": 0.85, "Ops": 0.90, "QALead": 1.0},
        "decision_focus": [
            "품질 게이트 통과 여부",
            "하위 에이전트 점수 종합 판정",
            "출시/배포 품질 기준 관리",
        ],
        "tier": 2,
        "domain": None,
    },
}

FLAT_MODE_AGENTS = {"CEO", "Planner", "Developer", "Researcher", "PM", "Ops", "QA"}

AGENT_WEIGHTS = {name: data["weights"] for name, data in AGENT_DEFINITIONS.items()}
AGENT_DEBATE_RULES = {
    name: {
        "supports": data["supports"],
        "challenges": data["challenges"],
    }
    for name, data in AGENT_DEFINITIONS.items()
}
AGENT_TRUST = {
    name: data["trust"] for name, data in AGENT_DEFINITIONS.items()
}

# ---------------------------------------------------------------------------
# Hierarchical (4-Tier) pipeline data structures & constants
# ---------------------------------------------------------------------------

@dataclass
class TierResult:
    tier: int
    tier_label: str  # "practitioners"|"team_leads"|"directors"|"executives"
    agent_scores: dict[str, dict[str, float]]  # {topic_id: {agent_key: score}}
    aggregated_scores: dict[str, float] | None = None
    ranking: list[dict] = field(default_factory=list)
    debate_log: list[dict] | None = None
    flags: dict[str, list[str]] = field(default_factory=dict)  # QA gate warnings
    metadata: dict = field(default_factory=dict)


@dataclass
class HierarchicalPipelineState:
    mode: str = "hierarchical"  # "hierarchical"|"flat"
    tier_results: dict[int, TierResult] = field(default_factory=dict)
    final_ranking: list[dict] = field(default_factory=list)
    execution_log: list[dict] = field(default_factory=list)


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

HIERARCHICAL_TRUST: dict[str, dict[str, float]] = {
    "CEO": {"Planner": 0.85, "PM": 0.88, "Ops": 0.82, "QALead": 0.80},
    "Planner": {"Researcher": 0.88, "DataScientist": 0.82},
    "PM": {"ProductDesigner": 0.85, "MarketAnalyst": 0.82},
    "Ops": {"Developer": 0.85, "DevOpsSRE": 0.88, "FinanceAnalyst": 0.78},
    "QALead": {"SecuritySpecialist": 0.90, "Linguist": 0.82, "QA": 0.85},
}

SUBORDINATE_BLEND_DEFAULT = 0.60
QA_GATE_THRESHOLD_DEFAULT = 3.5
QA_GATE_PENALTY = 0.10

TIER_1_AGENTS = {
    name for name, defn in AGENT_DEFINITIONS.items() if defn.get("tier") == 1
}
TIER_2_AGENTS = {
    name for name, defn in AGENT_DEFINITIONS.items() if defn.get("tier") == 2
}

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
LLM_CONSENSUS_TIMEOUT_SECONDS = 8.0
LLM_CONSENSUS_MIN_EVIDENCE = 2
LLM_CONSENSUS_MIN_CODE_DOC_SIGNAL = 2
LLM_CONSENSUS_MAX_RISK = 8.0
LLM_CONSENSUS_CMD_ENV = "ORA_RD_LLM_CONSENSUS_CMD"


def _clamp_score(value: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, round(value, 2)))


BUSINESS_WORDS = [
    "roi",
    "시장",
    "비용",
    "수익",
    "매출",
    "고객",
    "과제",
    "지원",
    "정부",
    "B2B",
    "과금",
    "투자",
    "수주",
    "규모",
    "서비스",
    "사업",
]

NOVELTY_WORDS = [
    "novel",
    "first",
    "new",
    "독자",
    "차별",
    "독보",
    "미존재",
    "처음",
    "최초",
    "세계",
    "유일",
    "논문",
    "arxiv",
    "interspeech",
    "ICASSP",
    "ACL",
    "EMNLP",
    "NeurIPS",
]


@dataclass
class Evidence:
    file: str
    line_no: int
    snippet: str
    topic_hit: str


@dataclass
class DebateEvent:
    round: int
    speaker: str
    action: str
    topic_id: str
    topic_name: str
    delta: float
    reason: str
    target_agents: list[str]
    confidence: float
    evidence_weight: float


@dataclass
class OrchestrationDecision:
    decision_id: str
    owner: str
    rationale: str
    risk: str
    next_action: str
    due: str
    topic_id: str
    topic_name: str
    service: list[str]
    score_delta: float
    confidence: float
    fail_label: str

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "owner": self.owner,
            "rationale": self.rationale,
            "risk": self.risk,
            "next_action": self.next_action,
            "due": self.due,
            "topic_id": self.topic_id,
            "topic_name": self.topic_name,
            "service": self.service,
            "score_delta": self.score_delta,
            "confidence": self.confidence,
            "fail_label": self.fail_label,
        }


@dataclass
class TopicState:
    topic_id: str
    topic_name: str
    keyword_hits: int = 0
    business_hits: int = 0
    novelty_hits: int = 0
    code_hits: int = 0
    doc_hits: int = 0
    history_hits: int = 0
    project_hits: dict[str, int] = field(default_factory=dict)
    evidence: list[Evidence] = field(default_factory=list)
    project_count: int = 0

    def normalized_score(self, value: float) -> float:
        return max(0.0, min(10.0, round(value, 2)))

    def compute_features(self) -> dict[str, float]:
        weighted_hits = self.keyword_hits + (self.code_hits * 0.4) + (self.doc_hits * 0.25)
        project_factor = math.log1p(self.project_count)

        impact = self.normalized_score(
            2.0 + 0.9 * math.log1p(self.keyword_hits + 1)
            + 0.7 * project_factor
            + 0.08 * self.business_hits
        )

        feasibility = self.normalized_score(
            2.1 + 1.7 * math.log1p(self.code_hits + 1) + 0.8 * project_factor
        )

        novelty = self.normalized_score(
            1.5 + 1.2 * math.log1p(self.novelty_hits + 1)
            + 0.4 * self.doc_hits
        )

        research_signal = self.normalized_score(
            1.2 + 0.8 * math.log1p(self.history_hits + 1) + 0.7 * math.log1p(self.keyword_hits + 1)
        )

        risk_penalty = self.normalized_score(
            max(0.0, 5.0 - (0.9 * self.code_hits + 0.6 * self.project_count))
        )

        return {
            "impact": impact,
            "feasibility": feasibility,
            "novelty": novelty,
            "research_signal": research_signal,
            "risk_penalty": risk_penalty,
            "weighted_hits": round(weighted_hits, 2),
        }

    def to_dict(self) -> dict:
        feature = self.compute_features()
        return {
            "topic_id": self.topic_id,
            "topic_name": self.topic_name,
            "keyword_hits": self.keyword_hits,
            "business_hits": self.business_hits,
            "novelty_hits": self.novelty_hits,
            "code_hits": self.code_hits,
            "doc_hits": self.doc_hits,
            "history_hits": self.history_hits,
            "project_count": self.project_count,
            "projects": sorted(self.project_hits.keys()),
            "features": feature,
            "evidence": [
                {
                    "file": e.file,
                    "line_no": e.line_no,
                    "snippet": e.snippet,
                    "topic_hit": e.topic_hit,
                }
                for e in self.evidence[:12]
            ],
        }


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
    for scope, aliases in SERVICE_ALIAS_MAP.items():
        scope_key = _normalize_text_token(scope)
        if key == scope_key:
            return scope
        alias_keys = {scope_key}
        alias_keys.update({_normalize_text_token(token) for token in aliases})
        if key in alias_keys:
            return scope
    return key


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


def _to_decision_due(days: int = DECISION_DUE_DEFAULT_DAYS) -> str:
    return (dt.datetime.now() + dt.timedelta(days=max(1, days))).strftime("%Y-%m-%d")


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


def analyze_workspace(
    workspace: Path,
    extensions: List[str],
    ignore_dirs: set[str],
    max_files: int,
    history_files: list[Path],
    service_scope: set[str] | None = None,
) -> dict[str, TopicState]:
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
        for topic_id, details in TOPICS.items()
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
            for topic_id, topic in TOPICS.items():
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

    # History documents usually include structured decisions and are weighted high.
    for history_file in history_files:
        if not history_file.exists():
            continue
        project_name = "history"
        for line_no, line in _read_lines(history_file):
            lowered = line.lower()
            matched_topics: list[TopicState] = []
            for topic_id, topic in TOPICS.items():
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


def score_by_agents(states: dict[str, TopicState]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    for topic_id, state in states.items():
        feat = state.compute_features()
        agent_scores: dict[str, float] = {}
        for agent_id in _agent_ids():
            weights = AGENT_WEIGHTS[agent_id]
            score = (
                weights["impact"] * feat["impact"]
                + weights["novelty"] * feat["novelty"]
                + weights["feasibility"] * feat["feasibility"]
                + weights["research_signal"] * feat["research_signal"]
                + weights["risk"] * feat["risk_penalty"]
            )
            agent_scores[_agent_score_key(agent_id)] = round(score, 2)
        result[topic_id] = agent_scores
    return result


def _build_global_scores(
    scores: dict[str, dict[str, float]],
) -> list[tuple[str, float]]:
    topic_votes = _rank_from_scores(scores)
    totals: list[tuple[str, float]] = []
    for topic_id in scores:
        weighted_sum = 0.0
        for agent_id, agent_weight in AGENT_FINAL_WEIGHTS.items():
            weighted_sum += agent_weight * scores[topic_id].get(_agent_score_key(agent_id), 0.0)
        weighted_sum += 0.02 * topic_votes[topic_id]
        total = round(weighted_sum, 2)
        totals.append((topic_id, total))
    return sorted(totals, key=lambda item: item[1], reverse=True)


def _supports_candidate(agent: str, state: TopicState, features: dict[str, float]) -> bool:
    rules = AGENT_DEBATE_RULES.get(agent, {})
    return any(rule(state, features) for rule in rules.get("supports", []))


def _challenges_candidate(agent: str, state: TopicState, features: dict[str, float]) -> bool:
    rules = AGENT_DEBATE_RULES.get(agent, {})
    return any(rule(state, features) for rule in rules.get("challenges", []))


def _agent_role_profile(agent: str) -> str:
    return AGENT_DEFINITIONS.get(agent, {}).get("objective", "기술-사업 균형 평가")


def _agent_focus_points(agent: str) -> list[str]:
    return list(AGENT_DEFINITIONS.get(agent, {}).get("decision_focus", []))


def _agent_decision(agent: str, state: TopicState, features: dict[str, float]) -> tuple[str, str]:
    support = _supports_candidate(agent, state, features)
    challenge = _challenges_candidate(agent, state, features)
    if support and not challenge:
        return "support", _top_reason_for_agent(agent, state, features)
    if challenge and not support:
        return "challenge", _challenge_reason_for_agent(agent, state, features)
    if support and challenge:
        return "review", "장단점이 혼재되어 추가 검증이 선행되어야 함"
    return "hold", "현재 근거 구간은 추가 분석이 필요한 중립 구간"


def _support_evidence(agent: str, state: TopicState, features: dict[str, float]) -> tuple[float, str]:
    if agent == "CEO":
        if state.business_hits >= 4:
            return 1.0, "시장성 언급이 다수 존재하며 계약 확장 가능성이 큼"
        if state.project_count >= 3:
            return 0.9, "여러 프로젝트에서 반복되어 실증성 신호가 안정적"
    if agent == "Planner":
        if _feature_value(features, "novelty") >= 6.5:
            return 1.0, "혁신성 지표가 높아 과제화/논문화 효익이 높음"
        if _feature_value(features, "research_signal") >= 7.0:
            return 0.9, "문헌 신호가 충분히 축적되어 연구 기반이 탄탄함"
    if _feature_value(features, "feasibility") >= 8.0:
        return 0.88, "실행 난이도가 낮아 PoC 연동 속도가 빠름"
    return 0.75, "실사용 맥락과 결합 시 가치가 높을 가능성"


def _challenge_evidence(agent: str, state: TopicState, features: dict[str, float]) -> tuple[float, str]:
    if agent == "CEO":
        if _feature_value(features, "risk_penalty") >= 6.8:
            return 0.98, "리스크가 커 과잉 투자 우려가 큼"
        if state.code_hits < 2:
            return 0.89, "구현 자산이 부족해 초기 리스크가 큼"
    if agent == "Planner":
        if _feature_value(features, "feasibility") < 4.5:
            return 0.98, "실행 로드맵 신뢰도가 낮아 선행 검증이 필요함"
        if state.project_count == 0:
            return 0.84, "프로젝트 근거가 얕아 적용 난도가 큼"
    if _feature_value(features, "code_hits") < 1:
        return 0.9, "현재 코드/레퍼런스 자원이 적어 과속 실행이 위험"
    return 0.78, "추가 검증 없이 전면 확장 시 운영 부담 가능성"


def _top_reason_for_agent(agent: str, state: TopicState, features: dict[str, float]) -> str:
    if agent == "CEO":
        if state.business_hits >= 3:
            return "시장성 근거(계약/수주·사업 언급)가 강해 실행 가치가 큼"
        if state.project_count >= 2:
            return "여러 프로젝트에서 반복되며 확장성이 확인됨"
        return "실무 임팩트 기대치가 높고 단기 수익화와 연계가 용이"
    if agent == "Planner":
        if _feature_value(features, "novelty") >= 6.5:
            return "기술 novelty가 높아 연구차별화/논문화 잠재력이 큼"
        if _feature_value(features, "research_signal") >= 6.0:
            return "문헌 근거 축적이 충분해 장기 과제화가 유리함"
        return "요구사항 충족성이 좋아 프로젝트의 아키텍처 정렬에 기여"
    if _feature_value(features, "feasibility") >= 8.0:
        return "구현 난이도가 낮아 단계적 PoC 연동이 빠름"
    return "기술 난이도는 낮아 빠른 실험 설계가 가능"


def _challenge_reason_for_agent(agent: str, state: TopicState, features: dict[str, float]) -> str:
    if agent == "CEO":
        if _feature_value(features, "risk_penalty") >= 7.0:
            return "리스크가 커서 사업화 전에 통제 계획이 필요"
        return "시장성 근거가 약해 과도한 선행 투자 가능성이 큼"
    if agent == "Planner":
        if _feature_value(features, "feasibility") < 4.8:
            return "실행 리스크가 커서 단계 분해가 우선되어야 함"
        return "연구 신호가 약해 과학적 실체 검증이 선행돼야 함"
    return "구현 기반(code/doc/evidence)이 얕아 과속 구현 리스크가 큼"


def _feature_value(features: dict[str, float], key: str, default: float = 0.0) -> float:
    value = features.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _topic_score_spread(features_by_agent: dict[str, float]) -> float:
    if not features_by_agent:
        return 0.0
    vals = list(features_by_agent.values())
    if not vals:
        return 0.0
    return round(max(vals) - min(vals), 3)


def _topic_agreement_label(spread: float) -> str:
    if spread <= 1.2:
        return "강한 합의"
    if spread <= 2.6:
        return "보통 합의"
    return "의견 분열"


def _build_round_messages(
    round_no: int,
    states: dict[str, TopicState],
    scores: dict[str, dict[str, float]],
    global_ranking: list[tuple[str, float]],
) -> list[DebateEvent]:
    feature_cache = {topic_id: states[topic_id].compute_features() for topic_id in states}
    global_order = [topic_id for topic_id, _ in global_ranking]
    message_topics: set[tuple[str, str, str]] = set()
    messages: list[DebateEvent] = []

    for speaker in AGENT_WEIGHTS:
        if not states:
            continue
        per_agent_count = 0

        speaker_key = _agent_score_key(speaker)
        ranked_by_speaker = sorted(
            scores.items(),
            key=lambda item: item[1].get(speaker_key, 0.0),
            reverse=True,
        )
        preferred_topics = [topic for topic, _ in ranked_by_speaker[:DEBATE_TOPIC_WINDOW]]
        union_topics: list[str] = []
        for topic_id in preferred_topics:
            if topic_id not in union_topics:
                union_topics.append(topic_id)
        for topic_id in global_order[:DEBATE_TOPIC_WINDOW]:
            if topic_id not in union_topics:
                union_topics.append(topic_id)

        if not union_topics and ranked_by_speaker:
            union_topics = [ranked_by_speaker[0][0]]

        for topic_id in union_topics[:DEBATE_TOPIC_WINDOW]:
            if per_agent_count >= DEBATE_MESSAGE_COUNT_PER_AGENT:
                break

            state = states[topic_id]
            feat = feature_cache[topic_id]
            spread = _topic_score_spread(scores[topic_id])
            support_key = (speaker, "support", topic_id)
            challenge_key = (speaker, "challenge", topic_id)

            support_candidates = topic_id == ranked_by_speaker[0][0] or topic_id in preferred_topics[:2]
            if (
                support_candidates
                and support_key not in message_topics
                and _supports_candidate(speaker, state, feat)
                and per_agent_count < DEBATE_MESSAGE_COUNT_PER_AGENT
            ):
                evidence_weight, detail = _support_evidence(speaker, state, feat)
                confidence = _clamp_score(
                    0.42 + (evidence_weight * 0.48) + (0.1 if topic_id == ranked_by_speaker[0][0] else 0.0),
                    0.0,
                    1.0,
                )
                delta = DEBATE_SUPPORT_DELTA * confidence / max(1, round_no)
                reason = _top_reason_for_agent(speaker, state, feat)
                if spread > 2.0:
                    reason = f"{reason} / 에이전트 간 의견 분열이 커 보완 필요"
                messages.append(
                    DebateEvent(
                        round=round_no,
                        speaker=speaker,
                        action="support",
                        topic_id=topic_id,
                        topic_name=state.topic_name,
                        delta=_clamp_score(delta, -10.0, 10.0),
                        reason=f"{reason} ({detail})",
                        target_agents=[agent for agent in AGENT_WEIGHTS if agent != speaker],
                        confidence=confidence,
                        evidence_weight=evidence_weight,
                    )
                )
                message_topics.add(support_key)
                per_agent_count += 1

            challenge_candidates = topic_id in global_order[:3] and (
                _challenges_candidate(speaker, state, feat) or spread >= 2.4
            )
            if (
                challenge_candidates
                and challenge_key not in message_topics
                and per_agent_count < DEBATE_MESSAGE_COUNT_PER_AGENT
            ):
                evidence_weight, detail = _challenge_evidence(speaker, state, feat)
                confidence = _clamp_score(
                    0.4 + (evidence_weight * 0.45) + (0.15 if spread >= 2.4 else 0.0),
                    0.0,
                    1.0,
                )
                delta = DEBATE_CHALLENGE_DELTA * confidence / max(1, round_no)
                reason = _challenge_reason_for_agent(speaker, state, feat)
                if spread >= 2.8:
                    reason = f"{reason} / 에이전트 간 이견이 큰 주제라 추가 검증 필요"
                messages.append(
                    DebateEvent(
                        round=round_no,
                        speaker=speaker,
                        action="challenge",
                        topic_id=topic_id,
                        topic_name=state.topic_name,
                        delta=_clamp_score(delta, -10.0, 10.0),
                        reason=f"{reason} ({detail})",
                        target_agents=[agent for agent in AGENT_WEIGHTS if agent != speaker],
                        confidence=confidence,
                        evidence_weight=evidence_weight,
                    )
                )
                message_topics.add(challenge_key)
                per_agent_count += 1

        # 주어진 라운드에서 자기 1순위가 토론표에서 완전히 놓치지 않도록 보강 발언
        if ranked_by_speaker:
            fallback_topic = ranked_by_speaker[0][0]
            fallback_state = states[fallback_topic]
            fallback_feat = feature_cache[fallback_topic]
            fallback_key = (speaker, "support", fallback_topic)
            if (
                per_agent_count < DEBATE_MESSAGE_COUNT_PER_AGENT
                and fallback_key not in message_topics
                and _supports_candidate(speaker, fallback_state, fallback_feat)
            ):
                confidence = _clamp_score(
                    0.5 + 0.5 * (fallback_feat["feasibility"] / 10),
                    0.0,
                    1.0,
                )
                delta = DEBATE_SUPPORT_DELTA * confidence * 0.8 / max(1, round_no)
                messages.append(
                    DebateEvent(
                        round=round_no,
                        speaker=speaker,
                        action="support",
                        topic_id=fallback_topic,
                        topic_name=fallback_state.topic_name,
                        delta=_clamp_score(delta, -10.0, 10.0),
                        reason=f"라운드 우선순위 보강: {speaker} 핵심 과제 후보",
                        target_agents=[agent for agent in AGENT_WEIGHTS if agent != speaker],
                        confidence=confidence,
                        evidence_weight=0.6,
                    )
                )
                per_agent_count += 1

    messages.sort(
        key=lambda item: (item.confidence * abs(item.delta), item.speaker, item.topic_name),
        reverse=True,
    )
    if messages:
        return messages[: max(1, min(len(AGENT_WEIGHTS) * DEBATE_MESSAGE_COUNT_PER_AGENT, DEBATE_MAX_MESSAGES_PER_ROUND))]
    return []


def _global_margin(ranking: list[tuple[str, float]]) -> float:
    if len(ranking) < 2:
        return 0.0
    return round(ranking[0][1] - ranking[1][1], 3)


def simulate_roundtable_deliberation(
    states: dict[str, TopicState],
    initial_scores: dict[str, dict[str, float]],
    rounds: int,
) -> tuple[dict[str, dict[str, float]], list[dict]]:
    rounds = max(0, rounds)
    if rounds <= 0:
        return copy.deepcopy(initial_scores), []

    working_scores = copy.deepcopy(initial_scores)
    discussion_log: list[dict] = []
    consecutive_stable = 0

    for round_no in range(1, rounds + 1):
        global_ranking = _build_global_scores(working_scores)
        pre_top3 = [topic for topic, _ in global_ranking[:3]]
        pre_margin = _global_margin(global_ranking)
        pre_scores = {topic: score for topic, score in global_ranking[:6]}

        messages = _build_round_messages(round_no, states, working_scores, global_ranking)
        adjustment_map: dict[str, dict[str, float]] = {
            topic_id: {_agent_score_key(agent): 0.0 for agent in AGENT_WEIGHTS}
            for topic_id in states
        }

        for msg in messages:
            if msg.topic_id not in working_scores:
                continue
            for target in [msg.speaker] + msg.target_agents:
                target_key = _agent_score_key(target)
                if target_key not in working_scores[msg.topic_id]:
                    continue
                trust = AGENT_TRUST.get(msg.speaker, {}).get(target, 0.72)
                weight = DEBATE_INFLUENCE_SELF if target == msg.speaker else DEBATE_INFLUENCE_OTHER
                weight *= trust
                applied_delta = msg.delta * weight * max(0.45, msg.confidence)
                working_scores[msg.topic_id][target_key] = _clamp_score(
                    working_scores[msg.topic_id][target_key] + applied_delta,
                    lo=0.0,
                    hi=10.0,
                )
                adjustment_map[msg.topic_id][target_key] += applied_delta

        next_ranking = _build_global_scores(working_scores)
        post_round_ranking = [topic for topic, _ in next_ranking]
        post_top3 = post_round_ranking[:3]
        post_margin = _global_margin(next_ranking)
        post_scores = {topic: score for topic, score in next_ranking[:6]}
        overlap = len(set(pre_top3) & set(post_top3))
        if overlap >= DEBATE_STABLE_OVERLAP and pre_margin >= DEBATE_STABLE_TOP3_GAP and post_margin >= DEBATE_STABLE_TOP3_GAP:
            consecutive_stable += 1
        else:
            consecutive_stable = 0

        round_consensus = _build_consensus(
            _build_agent_rankings(working_scores, top_k=6),
            top_k=6,
        )

        discussion_log.append(
            {
                "round": round_no,
                "pre_round_top3": pre_top3,
                "pre_margin": pre_margin,
                "post_round_top3": post_top3,
                "post_margin": post_margin,
                "top_topic_shift": {
                    "pre": pre_scores,
                    "post": post_scores,
                },
                "stability": {
                    "overlap": overlap,
                    "is_stable": overlap >= DEBATE_STABLE_OVERLAP,
                },
                "agent_consensus": round_consensus[:3],
                "agreement_summary": {
                    topic_id: _topic_agreement_label(_topic_score_spread({
                        agent: score
                        for agent, score in working_scores[topic_id].items()
                    }))
                    for topic_id in post_top3
                },
                "messages": [
                    {
                        "speaker": msg.speaker,
                        "action": msg.action,
                        "topic_id": msg.topic_id,
                        "topic_name": msg.topic_name,
                        "delta": msg.delta,
                        "reason": msg.reason,
                        "target_agents": msg.target_agents,
                        "confidence": msg.confidence,
                        "evidence_weight": msg.evidence_weight,
                    }
                    for msg in messages
                ],
                "adjustments": {
                    topic_id: {
                        agent: round(delta, 4)
                        for agent, delta in per_agent.items()
                    }
                    for topic_id, per_agent in adjustment_map.items()
                    if any(abs(delta) > 0 for delta in per_agent.values())
                },
            }
        )

        if consecutive_stable >= DEBATE_CONVERGENCE_ROUNDS:
            break

    return working_scores, discussion_log


def _rank_from_scores(scores: dict[str, dict[str, float]]) -> dict[str, int]:
    by_agent = {
        agent: sorted(
            scores.items(),
            key=lambda i: i[1].get(_agent_score_key(agent), 0.0),
            reverse=True,
        )
        for agent in AGENT_WEIGHTS
    }
    rank_map = {topic_id: 0 for topic_id in scores}
    for agent_scores in by_agent.values():
        for rank, (topic_id, _) in enumerate(agent_scores, start=1):
            rank_map[topic_id] += max(0, 20 - rank)
    return rank_map


def _build_final_score(states: dict[str, TopicState], scores: dict[str, dict[str, float]]) -> list[dict]:
    topic_votes = _rank_from_scores(scores)
    output: list[dict] = []

    for topic_id, state in states.items():
        feature = state.compute_features()
        total = 0.0
        for agent_id, agent_weight in AGENT_FINAL_WEIGHTS.items():
            total += agent_weight * scores[topic_id].get(_agent_score_key(agent_id), 0.0)
        total = round(total + 0.02 * topic_votes[topic_id], 2)
        row: dict[str, object] = {
            "topic_id": topic_id,
            "topic_name": state.topic_name,
            "total_score": total,
            "features": feature,
            "project_count": state.project_count,
            "evidence_count": len(state.evidence),
            "evidence": [e.snippet for e in state.evidence[:4]],
        }
        for agent_id in _agent_ids():
            row[_agent_score_key(agent_id)] = scores[topic_id].get(_agent_score_key(agent_id), 0.0)
        output.append(row)
    output.sort(key=lambda x: x["total_score"], reverse=True)
    return output


def _build_phase_plan(
    ranked: list[dict],
    top_k: int,
) -> list[dict]:
    phases = [
        {"phase": "Month 1-2", "topics": []},
        {"phase": "Month 3-4", "topics": []},
        {"phase": "Month 5-8", "topics": []},
    ]

    for idx, item in enumerate(ranked[:top_k], start=1):
        feasibility = item["features"]["feasibility"]
        novelty = item["features"]["novelty"]
        impact = item["features"]["impact"]

        if feasibility >= 6.8 and impact >= 5.5:
            bucket = 0
        elif novelty >= 5.2 or impact >= 6.8:
            bucket = 1
        else:
            bucket = 2

        phases[bucket]["topics"].append(
            {
                "rank": idx,
                "topic_id": item["topic_id"],
                "topic": item["topic_name"],
                "score": item["total_score"],
                "goal": "Quick win + low risk" if bucket == 0 else "Pilot + integration" if bucket == 1 else "Long-term research track",
            }
        )
    return [p for p in phases if p["topics"]]


def _top_projects_summary(state: TopicState, limit: int = 5) -> str:
    if not state.project_hits:
        return "프로젝트 근거 미확인"
    items = sorted(state.project_hits.items(), key=lambda item: item[1], reverse=True)
    joined = ", ".join(f"{name}({count}회)" for name, count in items[:limit])
    rest = len(items) - min(len(items), limit)
    if rest > 0:
        joined = f"{joined}, +{rest}개"
    return joined


def _build_root_cause(topic_id: str, feature: dict[str, float], state: TopicState) -> list[str]:
    causes = []
    if state.project_count < 2:
        causes.append("적용 프로젝트가 제한적이라 실증 범위가 아직 좁음")
    elif state.project_count >= 4:
        causes.append("여러 프로젝트에서 반복되는 패턴이라 적용 타당성이 높음")

    if state.business_hits >= 8:
        causes.append("비즈니스/과제 맥락 키워드가 강해 ROI와 수주 연계 가능성이 큼")
    elif state.business_hits < 3:
        causes.append("사업화 문구 근거가 약해 과제화 논리가 별도 정리가 필요")

    if feature["research_signal"] >= 7.0:
        causes.append("문헌·의사결정 신호가 축적되어 연구타당성 검증 기반이 존재함")
    else:
        causes.append("문헌/사례 근거가 상대적으로 얕아 선행 실험으로 신호 보강 필요")

    if state.code_hits >= 8:
        causes.append("코드 자산이 충분해 PoC 착수 난이도가 낮음")
    elif state.code_hits < 3:
        causes.append("직접 코드 증거가 적어 구현 난도가 과대추정될 위험 존재")

    if feature["novelty"] >= 6.5:
        causes.append("기술 차별성 신호가 커서 정합/논문화 관점에서 우선순위가 높음")

    if feature["feasibility"] >= 8.0:
        causes.append("현재 환경에서 30~60일 내 파일럿 가능성이 높음")

    if topic_id in TOPIC_CAUSE_LIBRARY:
        for item in TOPIC_CAUSE_LIBRARY[topic_id]:
            if item not in causes:
                causes.append(item)

    return causes[:6]


def _build_action_plan_for_strategy(item: dict) -> list[dict[str, list[str]]]:
    feature = item["features"]
    feasibility = feature["feasibility"]
    novelty = feature["novelty"]
    impact = feature["impact"]
    topic_id = item["topic_id"]

    if feasibility >= 7.0 and impact >= 6.0:
        plan = [
            {
                "phase": "0~1개월 (PoC)",
                "tasks": [
                    "주요 경로 1개를 최소 범위로 고정(예: 음성 흐름 제어 1개 지표)",
                    "실험 로그 및 기준선 KPI 정의(지연, 중단율, 재시도율)",
                    "문제 탐지용 실패 사례 50개 이상 수집",
                ],
            },
            {
                "phase": "1~2개월 (Integrate)",
                "tasks": [
                    "현재 파이프라인과 결합 가능한 최소 의존성 모듈만 연결",
                    "A/B 테스트 조건과 롤백 가드 명시(서비스 영향도 최소화)",
                    "평균 지연/성공률/재시도율 지표 비교 대시보드 생성",
                ],
            },
            {
                "phase": "3~4개월 (실서비스 검증)",
                "tasks": [
                    "서비스/콜 유형 2개 이상 확장 적용",
                    "회귀 리스크 목록(음성 중첩, 과도한 지연, 잘못된 호출) 기반 개선",
                    "과제 제안서 초안 작성(목표/성공지표/리스크/예산)",
                ],
            },
        ]
    elif novelty >= 7.0:
        plan = [
            {
                "phase": "0~2개월 (탐색)",
                "tasks": [
                    "대표 시나리오 1~2개로 벤치마크 정의",
                    "선행 자료/논문에서 메트릭 정렬(정확도, 안정성, 리포트 일관성)",
                    "실증 설계서 작성: 비교군/대조군/실패 기준",
                ],
            },
            {
                "phase": "2~4개월 (파일럿)",
                "tasks": [
                    "소규모 실사용 로그 기반으로 모델/로직 미세 조정",
                    "연구 신호(문헌 근거) 대조표를 만들어 결정 근거 문서화",
                    "중간중간 실패 모드 레포트 1회 주기 공개",
                ],
            },
            {
                "phase": "5~8개월 (고도화)",
                "tasks": [
                    "성능이 안정된 항목은 서비스 탑재 후보로 이전",
                    "성능 악화 케이스 1개당 완화 가드(제한/전환 규칙) 추가",
                    "특허성/논문화 쟁점과 실사용 이득을 정리한 기술노트 작성",
                ],
            },
        ]
    else:
        plan = [
            {
                "phase": "0~1개월 (기초 정리)",
                "tasks": [
                    "핵심 정의 1개로 범위를 고정하고 용어/지표 합의",
                    "근거 파일(코드·문서) 상향 정리 및 결함 위치 맵핑",
                ],
            },
            {
                "phase": "2~3개월 (저리스크 실험)",
                "tasks": [
                    "단일 채널에서 먼저 검증(안정성 우선)",
                    "실패율, 사용자 중단율, 재시도율을 정량적으로 측정",
                ],
            },
            {
                "phase": "4~6개월 (지속 개선)",
                "tasks": [
                    "기술 난이도 높은 부분은 단계 분리해 의사결정 비용 축소",
                    "개선 성과 기반 다음 라운드 우선순위 갱신",
                ],
            },
        ]
    if topic_id in TOPIC_ACTION_LIBRARY:
        extra = TOPIC_ACTION_LIBRARY[topic_id]
        if extra:
            plan = extra

    return plan


def _build_kpi_targets(item: dict) -> list[str]:
    feature = item["features"]
    topic_id = item["topic_id"]
    if feature["feasibility"] >= 7.0 and feature["impact"] >= 6.0:
        if topic_id in TOPIC_KPI_LIBRARY:
            return TOPIC_KPI_LIBRARY[topic_id]
        return [
            "P95 응답 지연 25~35% 개선 또는 동등 유지",
            "사용자 중단율(강제 재시작/끊김) 50~70% 감소",
            "실패 케이스 해소율(회귀 건수 기준) 월 20% 개선",
        ]
    if feature["novelty"] >= 7.0:
        return [
            "실험군 대비 핵심 지표(정확성·만족도) 유의한 상승 증거 확보",
            "PoC에서 안정 구간 95% 이상 유지",
            "문헌 대비 성능 격차 정량화(베이스라인 대비 최소 10~15% 개선)",
        ]
    return [
        "실험군/대조군 동시 비교 가능(안정성, 성공률, 체감 지표)",
        "핵심 실패 케이스 1차 분류 100% 구축",
        "다음 주기 자동화 항목 3개 이상 정의",
    ]


def _build_agent_decisions(top_topics: list[dict], states: dict[str, TopicState]) -> dict[str, list[dict]]:
    decisions: dict[str, list[dict]] = {}
    for item in top_topics:
        topic_id = item["topic_id"]
        state = states.get(topic_id)
        if not state:
            continue
        feature = item["features"]
        records: list[dict] = []
        for agent in AGENT_WEIGHTS:
            score_key = _agent_score_key(agent)
            action, reason = _agent_decision(agent, state, feature)
            records.append(
                {
                    "agent": agent,
                    "objective": _agent_role_profile(agent),
                    "decision": action,
                    "reason": reason,
                    "focus": _agent_focus_points(agent),
                    "score": item[score_key] if score_key in item else 0.0,
                }
            )
        records.sort(key=lambda x: x["agent"])
        decisions[topic_id] = records
    return decisions


def _build_strategy_cards(
    top_topics: list[dict],
    phase_plan: list[dict],
    states: dict[str, TopicState],
    agent_decisions: dict[str, list[dict]] | None = None,
    sources: list[dict[str, str]] | None = None,
) -> list[dict]:
    source_map: dict[str, list[dict[str, str]]] = {}
    for item in sources or []:
        key = item.get("topic_id", "")
        source_map.setdefault(key, []).append(item)

    topic_to_phase = {}
    for phase in phase_plan:
        for topic_item in phase["topics"]:
            topic_to_phase[topic_item["topic_id"]] = {
                "phase": phase["phase"],
                "goal": phase.get("goal", "추정 필요"),
            }

    cards: list[dict] = []
    for item in top_topics:
        topic_id = item["topic_id"]
        state = states.get(topic_id)
        feature = item["features"]
        if not state:
            continue
        phase_info = topic_to_phase.get(topic_id, {"phase": "미정", "goal": "추정 필요"})
        cards.append(
            {
                "topic_id": topic_id,
                "topic_name": item["topic_name"],
                "phase": phase_info["phase"],
                "phase_goal": phase_info["goal"],
                "score": item["total_score"],
                "rank": item.get("rank", 0),
                "feature_profile": {
                    "impact": feature["impact"],
                    "feasibility": feature["feasibility"],
                    "novelty": feature["novelty"],
                    "risk_penalty": feature["risk_penalty"],
                    "research_signal": feature["research_signal"],
                },
                "evidence_count": len(state.evidence),
                "projects": state.project_hits,
                "agent_decisions": agent_decisions.get(topic_id, []) if agent_decisions else [],
                "cause_analysis": _build_root_cause(topic_id, feature, state),
                "evidence_snapshots": [
                    {
                        "file": e.file,
                        "line": e.line_no,
                        "snippet": e.snippet,
                    }
                    for e in state.evidence[:8]
                ],
                "action_plan": _build_action_plan_for_strategy(item),
                "success_metrics": _build_kpi_targets(item),
                "papers": source_map.get(topic_id, [])[:6],
                "project_snapshot": _top_projects_summary(state),
            }
        )
    for idx, card in enumerate(cards, start=1):
        card["rank"] = idx
    return cards


def _build_agent_rankings(
    scores: dict[str, dict[str, float]],
    top_k: int,
    agent_filter: set[str] | None = None,
) -> dict[str, list[str]]:
    agents = agent_filter if agent_filter else set(AGENT_WEIGHTS.keys())
    rankings: dict[str, list[str]] = {}
    for agent in agents:
        key = _agent_score_key(agent)
        ranked_agent = sorted(scores.items(), key=lambda item: item[1].get(key, 0.0), reverse=True)
        rankings[agent] = [topic_id for topic_id, _ in ranked_agent[:top_k]]
    return rankings


def _build_consensus(
    agent_rankings: dict[str, list[str]],
    top_k: int = 6,
) -> list[str]:
    vote_weight_by_rank = {1: 3, 2: 2, 3: 1}
    vote_scores: dict[str, int] = {}
    for ranked_topics in agent_rankings.values():
        for rank, topic_id in enumerate(ranked_topics[:top_k], start=1):
            weight = vote_weight_by_rank.get(rank, 0)
            vote_scores[topic_id] = vote_scores.get(topic_id, 0) + weight
    return [topic_id for topic_id, _ in sorted(vote_scores.items(), key=lambda item: item[1], reverse=True)][:top_k]


def _init_neutral_agent_scores(states: dict[str, TopicState], value: float = 5.0) -> dict[str, dict[str, float]]:
    initial = _clamp_score(value, 0.0, 10.0)
    return {
        topic_id: {_agent_score_key(agent): initial for agent in AGENT_WEIGHTS}
        for topic_id in states
    }


def _pipeline_decisions_to_topic_records(
    decisions: list[OrchestrationDecision] | None,
) -> dict[str, list[dict]]:
    records: dict[str, list[dict]] = {}
    for item in decisions or []:
        record = {
            "agent": item.owner,
            "objective": AGENT_DEFINITIONS.get(item.owner, {}).get("objective", ""),
            "decision": "review",
            "reason": item.rationale,
            "focus": AGENT_DEFINITIONS.get(item.owner, {}).get("decision_focus", []),
            "score": item.confidence,
            "risk": item.risk,
            "next_action": item.next_action,
            "fail_label": item.fail_label,
            "due": item.due,
            "service": item.service,
        }
        records.setdefault(item.topic_id, []).append(record)
    return records


def _topic_item_index(ranked: list[dict]) -> dict[str, dict]:
    return {item["topic_id"]: item for item in ranked}


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen = set[str]()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        deduped.append(value)
        seen.add(value)
    return deduped


def _build_llm_consensus_payload(
    ranked: list[dict],
    states: dict[str, TopicState],
    agent_rankings: dict[str, list[str]],
    discussion: list[dict] | None,
    top_k: int,
) -> dict:
    return {
        "version": "llm-consensus-v2",
        "top_k": top_k,
        "output_contract": {
            "final_consensus": "ordered topic_id list length<=top_k",
            "rationale": "string",
            "concerns": [{"topic_id": "id", "reason": "string"}],
        },
        "agent_rules": {
            agent: {
                "objective": AGENT_DEFINITIONS.get(agent, {}).get("objective", ""),
                "decision_focus": AGENT_DEFINITIONS.get(agent, {}).get("decision_focus", []),
            }
            for agent in AGENT_WEIGHTS
        },
        "discussion": discussion or [],
        "topics": [
            {
                "topic_id": item["topic_id"],
                "topic_name": item["topic_name"],
                "scores": item,
                "evidence_count": len(states[item["topic_id"]].evidence),
                "project_count": states[item["topic_id"]].project_count,
                "risk_penalty": item["features"]["risk_penalty"],
                "feature": item["features"],
                "agent_signals": {
                    "agent_rankings": {
                        agent: ranks.index(item["topic_id"]) + 1
                        if item["topic_id"] in ranks
                        else None
                        for agent, ranks in agent_rankings.items()
                    }
                },
            }
            for item in ranked[:top_k]
            if item["topic_id"] in states
        ],
        "meta": {
            "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
            "topic_count": len(ranked),
        },
    }


def _run_llm_consensus(
    payload: dict,
    command: str | None,
    timeout: float = LLM_CONSENSUS_TIMEOUT_SECONDS,
) -> tuple[str, dict, str]:
    command = command or os.getenv(LLM_CONSENSUS_CMD_ENV)
    if not command:
        return "disabled", {"status": "disabled", "reason": "환경 변수/옵션 미설정"}, ""

    try:
        args = shlex.split(command)
        if not args:
            return "disabled", {"status": "disabled", "reason": "실행 명령이 비어 있음"}, ""
    except ValueError as exc:
        return "failed", {"status": "failed", "reason": f"명령 파싱 실패: {exc}"}, ""

    try:
        proc = subprocess.run(
            args=args,
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=max(1.0, timeout),
            check=False,
        )
    except Exception as exc:
        return "failed", {"status": "failed", "reason": f"실행 실패: {exc}"}, ""

    stderr = proc.stderr.decode("utf-8", errors="ignore").strip()
    raw_output = proc.stdout.decode("utf-8", errors="ignore").strip()
    if proc.returncode != 0:
        return "failed", {
            "status": "failed",
            "reason": f"명령 종료코드 {proc.returncode}",
            "stderr": stderr,
        }, raw_output

    if not raw_output:
        return "failed", {
            "status": "failed",
            "reason": "빈 응답",
            "stderr": stderr,
        }, ""

    try:
        result = json.loads(raw_output)
    except json.JSONDecodeError:
        # fallback: if tool returns mixed logs, extract trailing JSON block
        start = raw_output.find("{")
        end = raw_output.rfind("}")
        if start < 0 or end <= start:
            return "failed", {
                "status": "failed",
                "reason": "JSON 파싱 실패",
                "stderr": stderr,
                "raw_output": raw_output[:400],
            }, raw_output
        try:
            result = json.loads(raw_output[start : end + 1])
        except json.JSONDecodeError:
            return "failed", {
                "status": "failed",
                "reason": "JSON 파싱 실패",
                "stderr": stderr,
                "raw_output": raw_output[:400],
            }, raw_output

    if not isinstance(result, dict):
        return "failed", {"status": "failed", "reason": "응답 형식이 dict가 아님"}, raw_output

    return "ok", result, raw_output


def _to_risk_label(value: float) -> str:
    if value >= 8.0:
        return "high"
    if value >= 6.0:
        return "medium"
    return "low"


def _normalize_fail_label(value: object) -> str:
    label = str(value).strip().upper().replace(" ", "_")
    if label in {PIPELINE_FAIL_LABEL_SKIP, PIPELINE_FAIL_LABEL_RETRY, PIPELINE_FAIL_LABEL_STOP}:
        return label
    return ""


def _coerce_fail_label(risk_label: str, risk_score: float, confidence: float) -> str:
    if risk_label == "high" or risk_score >= 8.0:
        if confidence >= 0.84:
            return LLM_DELIBERATION_FAIL_LABEL_HIGH_RISK
        return LLM_DELIBERATION_FAIL_LABEL_MEDIUM_RISK
    if risk_label == "medium" or risk_score >= 6.0:
        if confidence >= 0.75:
            return LLM_DELIBERATION_FAIL_LABEL_MEDIUM_RISK
        return LLM_DELIBERATION_FAIL_LABEL_LOW_RISK
    return LLM_DELIBERATION_FAIL_LABEL_LOW_RISK


def _resolve_agent_name(raw: object) -> str:
    value = str(raw).strip().lower().replace(" ", "_")
    for agent in AGENT_WEIGHTS:
        if value in {agent.lower(), _agent_score_key(agent)}:
            return agent
    return ""

def _coerce_confidence(value: object, default: float = 0.5) -> float:
    try:
        return _clamp_score(float(value), 0.0, 1.0)
    except (TypeError, ValueError):
        return default


def _parse_llm_decision_record(
    item: dict,
    topic_catalog: dict[str, TopicState],
    service_scope: list[str],
) -> OrchestrationDecision:
    topic_id = str(item.get("topic_id", "")).strip()
    if topic_id not in topic_catalog:
        topic_id = next(iter(topic_catalog), "")
    state = topic_catalog.get(topic_id)
    topic_name = state.topic_name if state else topic_id
    score_delta = float(item.get("score_delta", item.get("delta", 0.0) or 0.0))
    risk_score = float(item.get("risk_score", item.get("risk", 0.0) or 0.0))
    risk_label = item.get("risk", "")
    if isinstance(risk_label, (int, float)):
        risk_label = _to_risk_label(float(risk_label))
    elif isinstance(risk_label, str):
        risk_label = risk_label.strip().lower() or _to_risk_label(risk_score)
    else:
        risk_label = _to_risk_label(risk_score)
    owner = str(item.get("owner", "")).strip() or "Researcher"
    if owner not in AGENT_DEFINITIONS:
        owner = "Researcher"
    target_services_raw = item.get("service", [])
    if isinstance(target_services_raw, str):
        target_services = _normalize_services(target_services_raw.split(","))
    elif isinstance(target_services_raw, (list, tuple, set)):
        target_services = _normalize_services(target_services_raw)
    else:
        target_services = list(service_scope) if service_scope else []
    if not target_services:
        target_services = list(service_scope) if service_scope else ["global"]
    rationale = str(item.get("rationale", "")).strip()
    if not rationale:
        rationale = "LLM 근거 메시지가 누락되어 보수적으로 처리"
    next_action = str(item.get("next_action", "")).strip() or "추가 근거 정리 후 1차 PoC 범위 확정"
    due = str(item.get("due", "")).strip()
    if not due:
        due = _to_decision_due()
    fail_label = _normalize_fail_label(item.get("fail_label", ""))
    if not fail_label:
        fail_label = _coerce_fail_label(
            risk_label=risk_label,
            risk_score=risk_score,
            confidence=_coerce_confidence(item.get("confidence", 0.5), 0.5),
        )
    return OrchestrationDecision(
        decision_id=str(item.get("decision_id", f"decision-{uuid.uuid4()}")),
        owner=owner,
        rationale=rationale,
        risk=risk_label,
        next_action=next_action,
        due=due,
        topic_id=topic_id,
        topic_name=topic_name,
        service=target_services,
        score_delta=_clamp_score(score_delta, -5.0, 5.0),
        confidence=_coerce_confidence(item.get("confidence", 0.5), 0.5),
        fail_label=fail_label,
    )


def _llm_round_payload(
    round_no: int,
    stages: list[str],
    service_scope: list[str],
    ranked: list[dict],
    states: dict[str, TopicState],
    scores: dict[str, dict[str, float]],
    previous_decisions: list[dict] | None,
    discussion: list[dict] | None,
) -> dict:
    return {
        "version": "llm-deliberation-v1",
        "output_contract": {
            "score_adjustments": "topic_id -> {agent_name_or_key: -3.0~3.0}",
            "decisions": [
                {
                    "decision_id": "string",
                    "owner": "CEO|Planner|Developer|Researcher|PM|Ops|QA",
                    "topic_id": "topic id",
                    "rationale": "why",
                    "risk": "low|medium|high",
                    "next_action": "action",
                    "due": "YYYY-MM-DD",
                    "service": ["b2b", "b2c"],
                    "score_delta": "float",
                    "confidence": "0~1",
                    "fail_label": "SKIP|RETRY|STOP",
                }
            ],
            "action_log": "optional list",
        },
        "round": round_no,
        "stages": stages,
        "service_scope": service_scope,
        "agent_rules": {
            agent: {
                "objective": AGENT_DEFINITIONS.get(agent, {}).get("objective", ""),
                "decision_focus": AGENT_DEFINITIONS.get(agent, {}).get("decision_focus", []),
                "weights": AGENT_DEFINITIONS.get(agent, {}).get("weights", {}),
            }
            for agent in AGENT_WEIGHTS
        },
        "topics": [
            {
                "topic_id": item["topic_id"],
                "topic_name": item["topic_name"],
                "scores": item,
                "feature": item["features"],
                "evidence_count": len(states[item["topic_id"]].evidence),
                "project_hits": states[item["topic_id"]].project_hits,
            }
            for item in ranked[: min(8, len(ranked))]
            if item["topic_id"] in states
        ],
        "score_matrix": scores,
        "topic_states": {
            topic_id: {
                "features": state.compute_features(),
                "keyword_hits": state.keyword_hits,
                "business_hits": state.business_hits,
                "novelty_hits": state.novelty_hits,
                "code_hits": state.code_hits,
                "doc_hits": state.doc_hits,
                "history_hits": state.history_hits,
                "projects": sorted(state.project_hits.keys()),
            }
            for topic_id, state in states.items()
        },
        "previous_decisions": previous_decisions or [],
        "previous_discussion": discussion or [],
    }


def _llm_round_response_to_updates(
    payload: dict,
    command: str | None,
    timeout: float,
    ranked: list[dict],
    states: dict[str, TopicState],
    service_scope: list[str],
) -> tuple[str, dict, list[OrchestrationDecision], dict[str, dict[str, float]], list[dict], list[dict]]:
    status, response, raw_output = _run_llm_consensus(payload, command=command, timeout=timeout)
    fallback_updates: dict[str, dict[str, float]] = {}
    action_log: list[dict] = []
    parsed_decisions: list[OrchestrationDecision] = []
    score_adjustments = {topic_id: {agent: 0.0 for agent in AGENT_WEIGHTS} for topic_id in states}

    if status != "ok":
        return status, {"status": status, "reason": response.get("reason", "llm 실행 실패")}, parsed_decisions, score_adjustments, action_log, [{"round": payload.get("round"), "stage": "deliberation", "status": status, "raw_output": raw_output[:800]}]

    updates = response.get("score_adjustments")
    if isinstance(updates, dict):
        for topic_id, per_agent in updates.items():
            if topic_id not in score_adjustments:
                continue
            if not isinstance(per_agent, dict):
                continue
            for agent, delta in per_agent.items():
                resolved_agent = _resolve_agent_name(agent)
                if not resolved_agent:
                    continue
                try:
                    parsed_delta = _clamp_score(float(delta), -3.0, 3.0)
                except (TypeError, ValueError):
                    continue
                score_adjustments[topic_id][resolved_agent] = parsed_delta

    decision_items = response.get("decisions")
    if isinstance(decision_items, list):
        for item in decision_items:
            if not isinstance(item, dict):
                continue
            parsed = _parse_llm_decision_record(item, states, service_scope)
            if parsed.topic_id not in [r.topic_id for r in parsed_decisions]:
                parsed_decisions.append(parsed)

    if isinstance(response.get("action_log"), list):
        action_log = [entry for entry in response.get("action_log") if isinstance(entry, dict)]

    return status, response, parsed_decisions, score_adjustments, action_log, response.get("round_summary", {"round": payload.get("round"), "agent": "llm"})


def _llm_deliberation_round(
    round_no: int,
    stages: list[str],
    service_scope: list[str],
    states: dict[str, TopicState],
    working_scores: dict[str, dict[str, float]],
    ranked: list[dict],
    previous_decisions: list[dict],
    previous_discussion: list[dict],
    command: str | None,
    timeout: float,
) -> tuple[dict[str, dict[str, float]], list[OrchestrationDecision], list[dict], list[dict], dict]:
    topic_ranked = _build_final_score(states, working_scores)  # ranking snapshot
    payload = _llm_round_payload(
        round_no=round_no,
        stages=stages,
        service_scope=service_scope,
        ranked=topic_ranked,
        states=states,
        scores=working_scores,
        previous_decisions=previous_decisions,
        discussion=previous_discussion,
    )
    status, raw_payload, decisions, score_adjustments, llm_actions, round_summary = _llm_round_response_to_updates(
        payload=payload,
        command=command,
        timeout=timeout,
        ranked=topic_ranked,
        states=states,
        service_scope=service_scope,
    )

    applied_updates: dict[str, dict[str, float]] = copy.deepcopy(score_adjustments)
    return applied_updates, decisions, [round_summary] if round_summary else [], llm_actions, {"status": status, "result": raw_payload}
def _consensus_hard_gate(topic_item: dict, state: TopicState) -> tuple[bool, str]:
    feature = topic_item["features"]
    evidence_count = len(state.evidence)
    if evidence_count < LLM_CONSENSUS_MIN_EVIDENCE:
        return False, f"근거 샘플이 부족함(evidence={evidence_count})"
    if feature["risk_penalty"] >= LLM_CONSENSUS_MAX_RISK:
        return False, f"리스크 패널티가 높음({feature['risk_penalty']})"
    if feature["research_signal"] < 4.0 and feature["feasibility"] < 4.8:
        return False, "연구 근거와 실행성 모두 낮아 합의 보류"
    if feature["feasibility"] < 3.2 and state.code_hits < LLM_CONSENSUS_MIN_CODE_DOC_SIGNAL:
        return False, "실행 근거가 충분치 않음"
    # ComplianceOfficer gate: block topics with extreme risk + low feasibility
    if feature["risk_penalty"] >= 7.0 and feature["feasibility"] < 4.0:
        return False, "컴플라이언스 게이트: 고위험 + 낮은 실행성으로 거부"
    return True, "통과"


def _apply_hybrid_consensus(
    ranked: list[dict],
    states: dict[str, TopicState],
    scores: dict[str, dict[str, float]],
    agent_rankings: dict[str, list[str]],
    discussion: list[dict] | None,
    top_k: int,
    command: str | None = None,
    timeout: float = LLM_CONSENSUS_TIMEOUT_SECONDS,
) -> dict:
    target_size = min(top_k, len(ranked))
    payload = _build_llm_consensus_payload(ranked, states, agent_rankings, discussion, target_size)
    status, llm_result, raw_output = _run_llm_consensus(payload, command=command, timeout=timeout)
    if status != "ok":
        return {
            "method": "llm-only",
            "status": "failed",
            "reason": llm_result.get("reason", "llm consensus failed"),
            "final_consensus_ids": [],
            "final_rationale": "",
            "llm": {"status": status, **llm_result},
            "llm_raw_output": raw_output[:1200] if raw_output else "",
            "concerns": [],
            "vetoed": [],
            "gating": [],
            "payload": payload,
            "target_size": target_size,
            "requested_top_k": top_k,
        }

    candidate = llm_result.get("final_consensus", llm_result.get("consensus", []))
    final_consensus: list[str] = []
    if isinstance(candidate, list):
        for topic_id in candidate:
            if not isinstance(topic_id, str):
                continue
            if topic_id in final_consensus:
                continue
            if topic_id not in states:
                continue
            final_consensus.append(topic_id)
            if len(final_consensus) >= target_size:
                break

    concerns: list[dict[str, str]] = []
    concerns_raw = llm_result.get("concerns", [])
    if isinstance(concerns_raw, list):
        for item in concerns_raw:
            if isinstance(item, str):
                concerns.append({"topic_id": item, "reason": "llm concern"})
            elif isinstance(item, dict) and isinstance(item.get("topic_id"), str):
                concerns.append(
                    {
                        "topic_id": item["topic_id"],
                        "reason": str(item.get("reason", "")).strip() or "llm concern",
                    }
                )

    return {
        "method": "llm-only",
        "status": "ok",
        "final_consensus_ids": final_consensus,
        "final_rationale": str(llm_result.get("rationale", "")).strip() or "llm consensus",
        "llm": llm_result,
        "llm_raw_output": raw_output[:1200] if raw_output else "",
        "concerns": concerns,
        "vetoed": [],
        "gating": [],
        "payload": payload,
        "target_size": target_size,
        "requested_top_k": top_k,
    }


def _build_research_queries(top_topics: list[dict], top_k: int = 5) -> list[dict[str, object]]:
    queries: list[dict[str, object]] = []
    for item in top_topics[:top_k]:
        topic_id = item["topic_id"]
        topic_name = item["topic_name"]
        keywords = TOPICS.get(topic_id, {}).get("keywords", [])
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


def _crossref_query_expression(topic_id: str, topic_name: str, keywords: list[str]) -> str:
    del topic_id  # topic_id currently unused but kept for signature parity
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


def _slugify_focus(value: str) -> str:
    lowered = value.strip().lower()
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in lowered)[:80]


def _normalize_source_url(url: str) -> str:
    return (url or "").strip().rstrip("/")


def _format_report_title(version_tag: str, report_focus: str) -> str:
    focus_text = report_focus.strip()
    if focus_text:
        return f"Ora 프로젝트 R&D 연구 주제 선정 보고서 ({version_tag} — {focus_text})"
    return f"Ora 프로젝트 R&D 연구 주제 선정 보고서 ({version_tag})"


def _build_default_sources(top_topics: list[dict], top_k: int = 12) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    arxiv_limit = _arxiv_search_limit()
    crossref_limit = _crossref_search_limit()
    openalex_limit = _openalex_search_limit()

    for item in top_topics[:top_k]:
        topic_id = item["topic_id"]
        topic_name = item["topic_name"]
        ref_candidates = DEFAULT_TOPIC_SOURCES.get(topic_id, [])
        topic_keywords = TOPICS.get(topic_id, {}).get("keywords", [])
        search_candidates = _search_arxiv_candidates(
            topic_id=topic_id,
            topic_name=topic_name,
            keywords=topic_keywords,
            max_results=min(3, arxiv_limit),
        )
        crossref_candidates = _search_crossref_candidates(
            topic_id=topic_id,
            topic_name=topic_name,
            keywords=topic_keywords,
            max_results=min(2, crossref_limit),
        )
        openalex_candidates = _search_openalex_candidates(
            topic_id=topic_id,
            topic_name=topic_name,
            keywords=topic_keywords,
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
            for fallback in fallback_candidates:
                norm_url = _normalize_source_url(fallback["url"])
                if norm_url in seen_urls:
                    continue
                sources.append(fallback)
                seen_urls.add(norm_url)
            for candidate in search_candidates:
                norm_url = _normalize_source_url(candidate.get("url", ""))
                if norm_url in seen_urls:
                    continue
                sources.append(candidate)
                seen_urls.add(norm_url)
            for candidate in crossref_candidates:
                norm_url = _normalize_source_url(candidate.get("url", ""))
                if norm_url in seen_urls:
                    continue
                sources.append(candidate)
                seen_urls.add(norm_url)
            for candidate in openalex_candidates:
                norm_url = _normalize_source_url(candidate.get("url", ""))
                if norm_url in seen_urls:
                    continue
                sources.append(candidate)
                seen_urls.add(norm_url)
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
        for candidate in search_candidates:
            norm_url = _normalize_source_url(candidate.get("url", ""))
            if norm_url in seen_urls:
                continue
            sources.append(candidate)
            seen_urls.add(norm_url)
        for candidate in crossref_candidates:
            norm_url = _normalize_source_url(candidate.get("url", ""))
            if norm_url in seen_urls:
                continue
            sources.append(candidate)
            seen_urls.add(norm_url)
        for candidate in openalex_candidates:
            norm_url = _normalize_source_url(candidate.get("url", ""))
            if norm_url in seen_urls:
                continue
            sources.append(candidate)
            seen_urls.add(norm_url)

    # Keep a manageable count and deterministic order
    return sources[:max(1, top_k * 4)]


def _build_sources_file(
    output_dir: Path,
    version_tag: str,
    report_focus: str,
    top_topics: list[dict],
) -> list[dict[str, str]]:
    scope = (
        f"{version_tag} 확장 영역(또는 V10 이후 미탐색 영역) 기반 다중 에이전트 분석"
        if report_focus
        else "V1~V10 미탐색 영역"
    )
    generated_sources = _build_default_sources(top_topics)
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


def _build_synergy_graph(states: dict[str, TopicState], ranked: list[dict]) -> list[str]:
    selected = {item["topic_id"] for item in ranked[:6]}
    items = sorted(selected)
    lines: list[str] = []
    for i, t1 in enumerate(items):
        for t2 in items[i + 1 :]:
            overlap = len(set(states[t1].project_hits.keys()) & set(states[t2].project_hits.keys()))
            if overlap >= 2:
                lines.append(
                    f"- {states[t1].topic_name} ↔ {states[t2].topic_name}: "
                    f"공통 파일군 {overlap}개 프로젝트에서 확인"
                )
    if not lines:
        lines.append("- 현재 분석 스냅샷 기준, 강한 증거 교집합은 부족해 보이나 정책/UX/모니터링 레이어로 연계 가능성 큼")
    return lines


def _as_markdown(
    workspace: Path,
    top_topics: list[dict],
    states: dict[str, TopicState],
    scores: dict[str, dict[str, float]],
    ranked: list[dict],
    agent_rankings: dict[str, list[str]],
    phases: list[dict],
    synergy_lines: list[str],
    queries: list[dict[str, str]],
    report_focus: str,
    version_tag: str,
    research_sources: list[dict[str, str]] | None = None,
    agent_decisions: dict[str, list[dict]] | None = None,
    discussion: list[dict] | None = None,
    debate_rounds: int = DEBATE_ROUNDS_DEFAULT,
    consensus_summary: dict | None = None,
    orchestration_profile: str = ORCHESTRATION_PROFILE_DEFAULT,
    orchestration_stages: list[str] | None = None,
    pipeline_decisions: list[dict] | list[OrchestrationDecision] | None = None,
    pipeline_stage_log: list[dict] | None = None,
    service_scope: list[str] | None = None,
    feature_scope: list[str] | None = None,
    hierarchical_analysis: dict | None = None,
) -> str:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    is_hierarchical = hierarchical_analysis is not None
    if is_hierarchical:
        agent_order = sorted(FLAT_MODE_AGENTS) + sorted(
            name for name in AGENT_DEFINITIONS if name not in FLAT_MODE_AGENTS
        )
    else:
        agent_order = [name for name in AGENT_FINAL_WEIGHTS]
    agent_title_map = {
        "CEO": "대표(CEO)",
        "Planner": "기획자(Planner)",
        "Developer": "개발자(Developer)",
        "Researcher": "연구자(Researcher)",
        "PM": "PM",
        "Ops": "운영(Ops)",
        "QA": "QA",
        "SecuritySpecialist": "보안전문가(Security)",
        "Linguist": "언어학자(Linguist)",
        "MarketAnalyst": "시장분석가(Market)",
        "FinanceAnalyst": "재무분석가(Finance)",
        "ProductDesigner": "프로덕트디자이너(PD)",
        "DataScientist": "데이터사이언티스트(DS)",
        "DevOpsSRE": "데브옵스(DevOps/SRE)",
        "QALead": "QA팀장(QALead)",
        "DataAnalyst": "데이터분석가(DA)",
        "TechLead": "테크리드(TL)",
        "GrowthHacker": "그로스해커(Growth)",
        "ComplianceOfficer": "컴플라이언스(Compliance)",
    }
    orchestration_stages = _normalize_stages(orchestration_stages, fallback=ORCHESTRATION_STAGES_DEFAULT)
    pipeline_decisions = pipeline_decisions or []
    pipeline_stage_log = pipeline_stage_log or []
    service_scope = service_scope or []
    feature_scope = feature_scope or []
    topic_name_by_id = {item["topic_id"]: item["topic_name"] for item in ranked}
    sources = research_sources or []
    final_consensus_ids = (
        consensus_summary.get("final_consensus_ids", [])
        if consensus_summary
        else []
    )
    consensus_lines = [f"- {topic_name_by_id.get(topic_id, topic_id)}" for topic_id in final_consensus_ids]
    query_lines = [f"- {item['topic_name']}: `{item['web_query']}`" for item in queries]
    strategy_cards = _build_strategy_cards(top_topics, phases, states, agent_decisions, sources)
    source_lines = [
        "- "
        + (f"{item.get('topic', '')}: " if item.get("topic", "") else "")
        + f"[{item.get('title', 'reference')}]({item.get('url', '')})"
        + (f" ({item.get('status', '')})" if item.get("status") else "")
        for item in sources[:20]
    ]

    table_headers = ["순위", "주제"]
    table_headers.extend(agent_order)
    table_headers.extend(["통합점수", "피처 점수(영향/실행성/혁신성)"])
    table_rows = [
        "| " + " | ".join(table_headers) + " |",
        "|" + "|".join(["---"] * len(table_headers)) + "|",
    ]
    for idx, item in enumerate(top_topics, start=1):
        feature = item["features"]
        row_values = [str(idx), item["topic_name"]]
        for agent in agent_order:
            row_values.append(str(item.get(_agent_score_key(agent), 0.0)))
        row_values.append(str(item["total_score"]))
        row_values.append(f"{feature['impact']} / {feature['feasibility']} / {feature['novelty']}")
        table_rows.append("| " + " | ".join(row_values) + " |")

    phases_md = []
    for phase in phases:
        bullets = [f"- {t['topic']} ({t['goal']}, 점수 {t['score']})" for t in phase["topics"]]
        if not bullets:
            continue
        phases_md.append(f"### {phase['phase']}\n" + "\n".join(bullets))

    evidence_md = []
    for item in top_topics:
        evidence_md.append(f"### {item['topic_name']}")
        if not item["evidence"]:
            evidence_md.append("- 증거 없음")
            continue
        for line in item["evidence"]:
            evidence_md.append(f"- {line}")

    sections: list[str] = []
    sections.append(f"# {_format_report_title(version_tag, report_focus)}")
    sections.append(f"> **작성일**: {now}")
    sections.append(
        "**참여자**: " + ", ".join(agent_title_map.get(agent, agent) for agent in agent_order)
    )
    sections.append(f"**범위**: `{workspace}`")
    sections.append(f"**오케스트레이션**: profile=`{orchestration_profile}` stages=`{','.join(orchestration_stages)}`")
    if service_scope:
        sections.append(f"**서비스 스코프**: {', '.join(service_scope)}")
    if feature_scope:
        sections.append(f"**기능 스코프**: {', '.join(feature_scope)}")
    sections.append("---")
    sections.append("## 1. 핵심 전략")
    sections.append("- 다중 에이전트 기반 토픽 점수, 역사 문서 히트율, 프로젝트별 구현성 힌트를 통합해 TOPIC을 선정합니다.")
    sections.append("- 분석된 TOP 항목은 실험/프로토타입 적합성, 구현 리스크, 정부 과제 접점 기준으로 정렬됩니다.")
    sections.append("")
    sections.append(f"## 2. 최종 확정 R&D 주제 (TOP {len(top_topics)})")
    sections.extend(table_rows)
    sections.append("")

    sections.append("## 2.1 협력 에이전트 역할·판단 구조")
    sections.append("- 각 에이전트는 아래 기준으로 1차 판단(지원/이의/재검토/중립)을 수행합니다.")
    for agent_name, profile in AGENT_DEFINITIONS.items():
        weight_lines = [f"{k}:{v:.2f}" for k, v in profile["weights"].items()]
        sections.append(f"### {agent_name}")
        sections.append(f"- 목표: {profile['objective']}")
        sections.append(f"- 가중치: {' / '.join(weight_lines)}")
        sections.append("- 판단 포인트:")
        for focus in profile["decision_focus"]:
            sections.append(f"  - {focus}")
        sections.append("")

    sections.append("## 3. R&D 전략별 상세 실행안(문제 원인 + 액션 플랜 + 근거)")
    for card in strategy_cards:
        sections.append(f"### 전략 {card['rank']}: {card['topic_name']}")
        sections.append(f"- 선정 단계: {card['phase']} / {card['phase_goal']}")
        sections.append(f"- 통합 점수: {card['score']} / 토픽 근거 샘플: {card['evidence_count']}건")
        fp = card["feature_profile"]
        sections.append(
            f"- 특성: 영향 {fp['impact']} / 실행성 {fp['feasibility']} / "
            f"혁신성 {fp['novelty']} / 리스크 {fp['risk_penalty']} / 연구신호 {fp['research_signal']}"
        )
        sections.append("- 프로젝트/증거 분포: " + card["project_snapshot"])
        sections.append("#### 협력 에이전트 판단")
        for dec in card.get("agent_decisions", []):
            status = dec["decision"]
            status_label = {
                "support": "지원",
                "challenge": "이의/보류",
                "review": "재검토",
                "hold": "중립",
            }.get(status, "재검토")
            sections.append(
                f"- {dec['agent']} ({status_label}, 점수 {dec.get('score', 0):.2f}): "
                f"{dec['reason']}"
            )
            focus = ", ".join(dec.get("focus", []))
            if focus:
                sections.append(f"  - 판단 포인트: {focus}")
        sections.append("#### 원인 진단")
        for cause in card["cause_analysis"]:
            sections.append(f"- {cause}")
        sections.append("#### 근거 스냅샷")
        if card["evidence_snapshots"]:
            for ev in card["evidence_snapshots"]:
                sections.append(f"- `{ev['file']}:{ev['line']}` {ev['snippet']}")
        else:
            sections.append("- 상위 근거가 충분히 누적되지 않음")
        sections.append("#### 액션 플랜")
        for step in card["action_plan"]:
            sections.append(f"- **{step['phase']}**")
            for t in step["tasks"]:
                sections.append(f"  - {t}")
        sections.append("#### 성공 지표(Go/No-Go 기준)")
        for m in card["success_metrics"]:
            sections.append(f"- {m}")
        if card["papers"]:
            sections.append("#### 관련 논문/자료(근거)")
            for paper in card["papers"]:
                status = paper.get("status", "")
                status_text = f" [{status}]" if status else ""
                arxiv_id = paper.get("id", "")
                if arxiv_id:
                    sections.append(f"- [{paper.get('title', 'reference')}]({paper.get('url', '')}){status_text} (`{arxiv_id}`)")
                else:
                    sections.append(f"- [{paper.get('title', 'reference')}]({paper.get('url', '')}){status_text}")
    sections.append("")

    sections.append("## 4. 오케스트레이션 단계 실행 로그")
    if pipeline_stage_log:
        for stage_item in pipeline_stage_log:
            stage_name = stage_item.get("stage", "unknown")
            stage_status = stage_item.get("status", "ok")
            stage_message = stage_item.get("message", "")
            sections.append(f"- [{stage_name}] {stage_status}: {stage_message}")
    else:
        sections.append("- 단계 로그가 기록되지 않았습니다.")
    sections.append("")
    sections.append("## 5. LLM 의사결정 객체")
    if pipeline_decisions:
        for decision in pipeline_decisions:
            record = decision.to_dict() if isinstance(decision, OrchestrationDecision) else dict(decision)
            sections.append(
                f"- `{record.get('decision_id', '')}` | owner={record.get('owner', '')} | "
                f"topic={record.get('topic_name', '')} | risk={record.get('risk', '')} | "
                f"fail_label={record.get('fail_label', '')} | confidence={record.get('confidence', 0)}"
            )
            sections.append(f"  - rationale: {record.get('rationale', '')}")
            sections.append(f"  - next_action: {record.get('next_action', '')} / due: {record.get('due', '')}")
    else:
        sections.append("- 생성된 의사결정 객체가 없습니다.")
    sections.append("")
    if consensus_summary:
        sections.append("## 6. LLM 보조 합의 결과")
        sections.append(f"- 합의 방식: {consensus_summary.get('method', 'llm-only')}")
        sections.append(f"- LLM 합의 상태: {consensus_summary.get('status', 'disabled')}")
        sections.append(f"- 최종 후보 반영 사유: {consensus_summary.get('final_rationale', '') or 'rule_only'}")
        sections.append("- LLM 최종 합의: " + ", ".join(topic_name_by_id.get(topic_id, topic_id) for topic_id in final_consensus_ids))
        concerns = consensus_summary.get("concerns", [])
        if concerns:
            sections.append("- LLM 우려 항목:")
            for item in concerns:
                if isinstance(item, dict):
                    topic_id = item.get("topic_id", "")
                    reason = item.get("reason", "")
                else:
                    topic_id = str(item)
                    reason = ""
                sections.append(f"  - {topic_name_by_id.get(topic_id, topic_id)}: {reason}")
        gating = consensus_summary.get("gating", [])
        if gating:
            sections.append("- 하드게이트 보류:")
            for item in gating:
                if isinstance(item, dict):
                    topic_id = item.get("topic_id", "")
                    reason = item.get("reason", "")
                else:
                    topic_id = str(item)
                    reason = ""
                sections.append(f"  - {topic_name_by_id.get(topic_id, topic_id)}: {reason}")
        sections.append("")
    sections.append("## 7. 구현 권장 로드맵")
    sections.extend(phases_md if phases_md else ["- 해당 토픽의 근거가 부족하여 즉시 실행 불가"])
    sections.append("")
    sections.append("## 8. 시너지 추정")
    sections.extend(synergy_lines if synergy_lines else ["- 현재 증거 기반 교집합이 적어 정책/UX/모니터링 레이어 기준으로 간접 연계 권장"])
    sections.append("")
    sections.append("## 9. 협력 에이전트 Top3")
    for agent, top_ids in agent_rankings.items():
        sections.append(f"### {agent}")
        for idx, topic_id in enumerate(top_ids[:3], start=1):
            sections.append(
                f"- {idx}위: {topic_name_by_id.get(topic_id, topic_id)} "
                f"({scores[topic_id].get(_agent_score_key(agent), 0.0)})"
            )
    sections.append("")
    sections.append("## 10. 합의 후보")
    sections.extend(consensus_lines if consensus_lines else ["- LLM 합의 항목이 없습니다."])
    sections.append("")
    sections.append("## 11. 자동 웹 검증 큐")
    sections.extend(query_lines if query_lines else ["- 이번 분석에서 생성된 후보 쿼리 없음"])
    sections.append("")
    sections.append("## 12. 연구 근거 후보")
    sections.extend(source_lines if source_lines else ["- 연구 출처 후보가 부족함"])
    sections.append("")
    sections.append("## 13. 상위 주제 근거 (최대 1개 발췌 근거)")
    sections.extend(evidence_md if evidence_md else ["- 상위 항목 근거가 충분히 수집되지 않음"])

    sections.append("")
    executed_rounds = len(discussion or [])
    sections.append(f"## 14. 에이전트 토론 로그 (요청 {debate_rounds}라운드 / 실행 {executed_rounds}라운드)")
    if not discussion:
        sections.append("- 이번 실행에서 토론 로그 미생성")
    else:
        for round_log in discussion:
            sections.append(f"### Round {round_log.get('round', 'N/A')}")
            pre = round_log.get("pre_round_top3", [])
            post = round_log.get("post_round_top3", [])
            pre_margin = round_log.get("pre_margin", 0.0)
            post_margin = round_log.get("post_margin", 0.0)
            stability = round_log.get("stability", {})
            if pre:
                sections.append("- 라운드 시작 TOP3: " + ", ".join(topic_name_by_id.get(x, x) for x in pre))
            sections.append(f"- 안정성 지표: 겹침 {stability.get('overlap', 0)} / 안정판정 {stability.get('is_stable', False)}")
            sections.append(f"- 마진 변화: {pre_margin:.2f} -> {post_margin:.2f}")
            if post:
                sections.append("- 라운드 종료 TOP3: " + ", ".join(topic_name_by_id.get(x, x) for x in post))
            consensus = round_log.get("agent_consensus", [])
            if consensus:
                sections.append("- 라운드 내 합의 후보: " + ", ".join(topic_name_by_id.get(x, x) for x in consensus[:3]))
            for topic_id, state in (round_log.get("agreement_summary") or {}).items():
                sections.append(f"- {topic_name_by_id.get(topic_id, topic_id)}: 에이전트 의견 {state}")
            for msg in round_log.get("messages", []):
                target_agents = ", ".join(msg.get("target_agents", []))
                sections.append(
                    f"- {msg['speaker']} {msg['action']} → "
                    f"{topic_name_by_id.get(msg['topic_id'], msg['topic_id'])} "
                    f"(적용 대상: {target_agents}, delta {msg.get('delta', 0):.2f}, "
                    f"confidence {msg.get('confidence', 0):.2f}, evidence {msg.get('evidence_weight', 0):.2f}): {msg['reason']}"
                )

    # --- Hierarchical Analysis Section ---
    if hierarchical_analysis:
        sections.append("")
        sections.append("## 15. 계층적 분석 요약 (4-Tier Hierarchical)")
        sections.append(f"- 분석 모드: `{hierarchical_analysis.get('mode', 'hierarchical')}`")
        sections.append("")

        # Tier 1: Practitioner scores
        sections.append("### Tier 1: 실무 전문가 평가")
        t1_agents = sorted(hierarchical_analysis.get("tier1", {}).get("agents", []))
        t1_scores = hierarchical_analysis.get("tier1", {}).get("scores", {})
        if t1_agents and t1_scores:
            t1_headers = ["주제"] + [agent_title_map.get(a, a) for a in t1_agents]
            sections.append("| " + " | ".join(t1_headers) + " |")
            sections.append("|" + "|".join(["---"] * len(t1_headers)) + "|")
            for item in top_topics:
                topic_id = item["topic_id"]
                row = [item["topic_name"]]
                for agent in t1_agents:
                    row.append(str(t1_scores.get(topic_id, {}).get(_agent_score_key(agent), "-")))
                sections.append("| " + " | ".join(row) + " |")
        else:
            sections.append("- Tier 1 스코어 데이터 없음")
        sections.append("")

        # Tier 2: Team lead aggregation
        sections.append("### Tier 2: 팀 리드 종합")
        t2_leads = hierarchical_analysis.get("tier2", {}).get("leads", [])
        t2_scores = hierarchical_analysis.get("tier2", {}).get("scores", {})
        t2_flags = hierarchical_analysis.get("tier2", {}).get("flags", {})
        if t2_leads and t2_scores:
            blend = hierarchical_analysis.get("tier2", {}).get("subordinate_blend", SUBORDINATE_BLEND_DEFAULT)
            sections.append(f"- 하위 에이전트 블렌드 비율: {blend:.0%} 하위 / {1 - blend:.0%} 리드 자체 평가")
            t2_headers = ["주제"] + [agent_title_map.get(l, l) for l in t2_leads] + ["QA 경고"]
            sections.append("| " + " | ".join(t2_headers) + " |")
            sections.append("|" + "|".join(["---"] * len(t2_headers)) + "|")
            for item in top_topics:
                topic_id = item["topic_id"]
                row = [item["topic_name"]]
                for lead in t2_leads:
                    row.append(str(t2_scores.get(topic_id, {}).get(_agent_score_key(lead), "-")))
                flags_for_topic = t2_flags.get(topic_id, [])
                row.append("; ".join(flags_for_topic) if flags_for_topic else "-")
                sections.append("| " + " | ".join(row) + " |")
        sections.append("")

        # Tier 3: Director debate
        sections.append("### Tier 3: 디렉터 토론")
        t3_data = hierarchical_analysis.get("tier3", {})
        t3_rounds = t3_data.get("debate_rounds", 0)
        t3_debate_log = t3_data.get("debate_log", [])
        sections.append(f"- 토론 라운드: {t3_rounds}")
        if t3_debate_log:
            for round_entry in t3_debate_log:
                sections.append(f"#### Round {round_entry.get('round', 'N/A')}")
                for msg in round_entry.get("messages", []):
                    sections.append(
                        f"- {msg.get('speaker', '?')} {msg.get('action', '?')} → "
                        f"{msg.get('topic_name', msg.get('topic_id', '?'))} "
                        f"(delta {msg.get('delta', 0):.2f})"
                    )
        else:
            sections.append("- 토론 로그 없음 (라운드 0 또는 스킵)")
        sections.append("")

        # Tier 4: CEO final
        sections.append("### Tier 4: CEO 최종 결정")
        t4_data = hierarchical_analysis.get("tier4", {})
        t4_scores = t4_data.get("scores", {})
        penalty_topics = t4_data.get("qa_penalty_topics", [])
        if penalty_topics:
            sections.append(f"- QA 게이트 페널티 적용 토픽: {', '.join(topic_name_by_id.get(t, t) for t in penalty_topics)}")
        for item in top_topics:
            tid = item["topic_id"]
            ceo_s = t4_scores.get(tid, {}).get(_agent_score_key("CEO"), "-")
            penalty_mark = " ⚠️ QA 페널티" if tid in penalty_topics else ""
            sections.append(f"- {item['topic_name']}: CEO 점수 {ceo_s}{penalty_mark}")
        sections.append("")

        # Tier score breakdown
        sections.append("### 최종 Tier 가중 합산")
        sections.append(f"- Tier4(CEO) {HIERARCHICAL_FINAL_WEIGHTS['tier4_weight']:.0%} + "
                        f"Tier3(디렉터) {HIERARCHICAL_FINAL_WEIGHTS['tier3_weight']:.0%} + "
                        f"Tier2(팀리드) {HIERARCHICAL_FINAL_WEIGHTS['tier2_weight']:.0%} + "
                        f"Tier1(실무) {HIERARCHICAL_FINAL_WEIGHTS['tier1_weight']:.0%}")
        for item in top_topics[:6]:
            ts_data = item.get("tier_scores", {})
            sections.append(
                f"- {item['topic_name']}: T1={ts_data.get('tier1_avg', '-')} "
                f"T2={ts_data.get('tier2_weighted', '-')} "
                f"T3={ts_data.get('tier3_debated', '-')} "
                f"T4={ts_data.get('tier4_ceo', '-')} "
                f"→ 합산={item.get('total_score', '-')}"
            )
        sections.append("")

    return "\n".join(sections) + "\n\n"


# ---------------------------------------------------------------------------
# Hierarchical 4-Tier pipeline execution functions
# ---------------------------------------------------------------------------

def _execute_tier1(
    states: dict[str, TopicState],
) -> TierResult:
    """Tier 1: All practitioner agents score independently."""
    tier1_agent_names = sorted(TIER_1_AGENTS)
    tier1_weights = {name: AGENT_DEFINITIONS[name]["weights"] for name in tier1_agent_names}
    agent_scores: dict[str, dict[str, float]] = {}
    for topic_id, state in states.items():
        feat = state.compute_features()
        per_topic: dict[str, float] = {}
        for agent_name in tier1_agent_names:
            weights = tier1_weights[agent_name]
            score = (
                weights["impact"] * feat["impact"]
                + weights["novelty"] * feat["novelty"]
                + weights["feasibility"] * feat["feasibility"]
                + weights["research_signal"] * feat["research_signal"]
                + weights["risk"] * feat["risk_penalty"]
            )
            per_topic[_agent_score_key(agent_name)] = round(score, 2)
        agent_scores[topic_id] = per_topic
    return TierResult(
        tier=1,
        tier_label="practitioners",
        agent_scores=agent_scores,
        metadata={"agents": tier1_agent_names},
    )


def _execute_tier2(
    states: dict[str, TopicState],
    tier1_result: TierResult,
    subordinate_blend: float = SUBORDINATE_BLEND_DEFAULT,
    qa_gate_threshold: float = QA_GATE_THRESHOLD_DEFAULT,
) -> TierResult:
    """Tier 2: Team leads aggregate subordinate scores + own evaluation."""
    lead_names = sorted(TIER_2_DOMAIN_MAP.keys())
    lead_weights = {name: AGENT_DEFINITIONS[name]["weights"] for name in lead_names}
    agent_scores: dict[str, dict[str, float]] = {}
    flags: dict[str, list[str]] = {}

    for topic_id, state in states.items():
        feat = state.compute_features()
        per_topic: dict[str, float] = {}
        for lead_name in lead_names:
            domain = TIER_2_DOMAIN_MAP[lead_name]
            sub_agents = domain["tier1_agents"]
            intra_w = domain["intra_weights"]
            aggregation = domain.get("aggregation", "weighted_mean")

            # subordinate weighted mean
            sub_sum = 0.0
            w_sum = 0.0
            min_sub_score = 10.0
            for sub_agent in sub_agents:
                sub_key = _agent_score_key(sub_agent)
                sub_score = tier1_result.agent_scores.get(topic_id, {}).get(sub_key, 5.0)
                w = intra_w.get(sub_agent, 1.0 / max(1, len(sub_agents)))
                sub_sum += w * sub_score
                w_sum += w
                min_sub_score = min(min_sub_score, sub_score)
            sub_avg = sub_sum / max(w_sum, 1e-9)

            # lead's own evaluation
            weights = lead_weights[lead_name]
            lead_own = (
                weights["impact"] * feat["impact"]
                + weights["novelty"] * feat["novelty"]
                + weights["feasibility"] * feat["feasibility"]
                + weights["research_signal"] * feat["research_signal"]
                + weights["risk"] * feat["risk_penalty"]
            )

            # blend: subordinate_blend * sub_avg + (1 - subordinate_blend) * lead_own
            blended = subordinate_blend * sub_avg + (1.0 - subordinate_blend) * lead_own
            blended = round(blended, 2)

            # QALead: min_gated_mean check
            if aggregation == "min_gated_mean":
                gate = domain.get("gate_threshold", qa_gate_threshold)
                if min_sub_score < gate:
                    flags.setdefault(topic_id, []).append(
                        f"QA gate: {lead_name} min_sub_score={min_sub_score:.2f} < threshold={gate}"
                    )

            per_topic[_agent_score_key(lead_name)] = _clamp_score(blended)
        agent_scores[topic_id] = per_topic

    return TierResult(
        tier=2,
        tier_label="team_leads",
        agent_scores=agent_scores,
        flags=flags,
        metadata={"leads": lead_names, "subordinate_blend": subordinate_blend},
    )


def _execute_tier3(
    states: dict[str, TopicState],
    tier2_result: TierResult,
    debate_rounds: int = 2,
) -> TierResult:
    """Tier 3: Cross-domain debate among Tier2 leads."""
    if debate_rounds <= 0:
        return TierResult(
            tier=3,
            tier_label="directors",
            agent_scores=copy.deepcopy(tier2_result.agent_scores),
            debate_log=[],
            flags=copy.deepcopy(tier2_result.flags),
            metadata={"debate_rounds": 0, "skipped": True},
        )

    lead_names = sorted(TIER_2_DOMAIN_MAP.keys())
    working = copy.deepcopy(tier2_result.agent_scores)
    debate_log: list[dict] = []

    for round_no in range(1, debate_rounds + 1):
        round_messages: list[dict] = []
        for topic_id, state in states.items():
            if topic_id not in working:
                continue
            feat = state.compute_features()
            for lead_name in lead_names:
                lead_key = _agent_score_key(lead_name)
                current = working[topic_id].get(lead_key, 5.0)
                supports = _supports_candidate(lead_name, state, feat)
                challenges = _challenges_candidate(lead_name, state, feat)
                if supports and not challenges:
                    delta = DEBATE_SUPPORT_DELTA * 0.5
                    action = "support"
                elif challenges and not supports:
                    delta = DEBATE_CHALLENGE_DELTA * 0.5
                    action = "challenge"
                else:
                    delta = 0.0
                    action = "hold"
                if abs(delta) > 0:
                    # apply trust-weighted adjustment to other leads
                    trust_map = HIERARCHICAL_TRUST.get(lead_name, {})
                    for other_lead in lead_names:
                        if other_lead == lead_name:
                            continue
                        other_key = _agent_score_key(other_lead)
                        if other_key not in working[topic_id]:
                            continue
                        trust = trust_map.get(other_lead, 0.70)
                        applied = delta * DEBATE_INFLUENCE_OTHER * trust
                        working[topic_id][other_key] = _clamp_score(
                            working[topic_id][other_key] + applied
                        )
                    # apply self
                    self_applied = delta * DEBATE_INFLUENCE_SELF
                    working[topic_id][lead_key] = _clamp_score(current + self_applied)

                    round_messages.append({
                        "round": round_no,
                        "speaker": lead_name,
                        "action": action,
                        "topic_id": topic_id,
                        "topic_name": state.topic_name,
                        "delta": round(delta, 4),
                    })

        debate_log.append({
            "round": round_no,
            "messages": round_messages,
        })

    return TierResult(
        tier=3,
        tier_label="directors",
        agent_scores=working,
        debate_log=debate_log,
        flags=copy.deepcopy(tier2_result.flags),
        metadata={"debate_rounds": debate_rounds},
    )


def _execute_tier4(
    states: dict[str, TopicState],
    tier3_result: TierResult,
) -> TierResult:
    """Tier 4: CEO final decision with QA flag penalty."""
    ceo_weights = AGENT_DEFINITIONS["CEO"]["weights"]
    agent_scores: dict[str, dict[str, float]] = {}

    for topic_id, state in states.items():
        feat = state.compute_features()
        ceo_score = (
            ceo_weights["impact"] * feat["impact"]
            + ceo_weights["novelty"] * feat["novelty"]
            + ceo_weights["feasibility"] * feat["feasibility"]
            + ceo_weights["research_signal"] * feat["research_signal"]
            + ceo_weights["risk"] * feat["risk_penalty"]
        )
        # Apply QA flag penalty
        if topic_id in tier3_result.flags:
            ceo_score *= (1.0 - QA_GATE_PENALTY)
        agent_scores[topic_id] = {_agent_score_key("CEO"): round(ceo_score, 2)}

    return TierResult(
        tier=4,
        tier_label="executives",
        agent_scores=agent_scores,
        flags=copy.deepcopy(tier3_result.flags),
        metadata={"qa_penalty_applied": list(tier3_result.flags.keys())},
    )


def _build_hierarchical_final_scores(
    states: dict[str, TopicState],
    tier_results: dict[int, TierResult],
) -> list[dict]:
    """Build final ranked list from 4-tier weighted aggregation."""
    w = HIERARCHICAL_FINAL_WEIGHTS
    tier4_w = w["tier4_weight"]
    tier3_w = w["tier3_weight"]
    tier2_w = w["tier2_weight"]
    tier1_w = w["tier1_weight"]
    lead_weights = w["tier2_lead_weights"]

    output: list[dict] = []
    for topic_id, state in states.items():
        feat = state.compute_features()

        # Tier 4: CEO score
        t4_score = tier_results[4].agent_scores.get(topic_id, {}).get(
            _agent_score_key("CEO"), 5.0
        )

        # Tier 3: average of tier2 lead scores after debate
        t3_scores = tier_results[3].agent_scores.get(topic_id, {})
        t3_total = 0.0
        for lead_name, lw in lead_weights.items():
            t3_total += lw * t3_scores.get(_agent_score_key(lead_name), 5.0)

        # Tier 2: average of tier2 lead scores before debate
        t2_scores = tier_results[2].agent_scores.get(topic_id, {})
        t2_total = 0.0
        for lead_name, lw in lead_weights.items():
            t2_total += lw * t2_scores.get(_agent_score_key(lead_name), 5.0)

        # Tier 1: simple average of all practitioners
        t1_scores = tier_results[1].agent_scores.get(topic_id, {})
        t1_vals = list(t1_scores.values())
        t1_avg = sum(t1_vals) / max(len(t1_vals), 1)

        total = (
            tier4_w * t4_score
            + tier3_w * t3_total
            + tier2_w * t2_total
            + tier1_w * t1_avg
        )
        total = round(total, 2)

        row: dict[str, object] = {
            "topic_id": topic_id,
            "topic_name": state.topic_name,
            "total_score": total,
            "features": feat,
            "project_count": state.project_count,
            "evidence_count": len(state.evidence),
            "evidence": [e.snippet for e in state.evidence[:4]],
            "tier_scores": {
                "tier1_avg": round(t1_avg, 2),
                "tier2_weighted": round(t2_total, 2),
                "tier3_debated": round(t3_total, 2),
                "tier4_ceo": round(t4_score, 2),
            },
            "qa_flags": tier_results.get(3, TierResult(3, "directors", {})).flags.get(topic_id, []),
        }
        # include per-agent scores from all tiers
        for tier_num in (1, 2, 3, 4):
            tr = tier_results.get(tier_num)
            if tr:
                for agent_key, score in tr.agent_scores.get(topic_id, {}).items():
                    row[agent_key] = score
        output.append(row)

    output.sort(key=lambda x: x["total_score"], reverse=True)
    return output


def _run_hierarchical_pipeline(
    states: dict[str, TopicState],
    tier3_debate_rounds: int = 2,
    subordinate_blend: float = SUBORDINATE_BLEND_DEFAULT,
    qa_gate_threshold: float = QA_GATE_THRESHOLD_DEFAULT,
) -> HierarchicalPipelineState:
    """Run the full Tier1 -> Tier2 -> Tier3 -> Tier4 pipeline."""
    pipeline = HierarchicalPipelineState(mode="hierarchical")

    # Tier 1
    pipeline.execution_log.append({"tier": 1, "status": "started"})
    t1 = _execute_tier1(states)
    pipeline.tier_results[1] = t1
    pipeline.execution_log.append({"tier": 1, "status": "completed", "agents": len(TIER_1_AGENTS)})

    # Tier 2
    pipeline.execution_log.append({"tier": 2, "status": "started"})
    t2 = _execute_tier2(states, t1, subordinate_blend=subordinate_blend, qa_gate_threshold=qa_gate_threshold)
    pipeline.tier_results[2] = t2
    pipeline.execution_log.append({"tier": 2, "status": "completed", "flags": len(t2.flags)})

    # Tier 3
    pipeline.execution_log.append({"tier": 3, "status": "started"})
    t3 = _execute_tier3(states, t2, debate_rounds=tier3_debate_rounds)
    pipeline.tier_results[3] = t3
    pipeline.execution_log.append({"tier": 3, "status": "completed", "debate_rounds": tier3_debate_rounds})

    # Tier 4
    pipeline.execution_log.append({"tier": 4, "status": "started"})
    t4 = _execute_tier4(states, t3)
    pipeline.tier_results[4] = t4
    pipeline.execution_log.append({"tier": 4, "status": "completed"})

    # Final ranking
    pipeline.final_ranking = _build_hierarchical_final_scores(states, pipeline.tier_results)

    return pipeline


def _to_json(
    states: dict[str, TopicState],
    scores: dict[str, dict[str, float]],
    scores_initial: dict[str, dict[str, float]] | None,
    ranked: list[dict],
    phases: list[dict],
    report_focus: str,
    version_tag: str,
    research_sources: list[dict[str, str]],
    selected_agent_decisions: dict[str, list[dict]] | None = None,
    discussion: list[dict] | None = None,
    debate_rounds: int = DEBATE_ROUNDS_DEFAULT,
    consensus_summary: dict | None = None,
    orchestration_profile: str = ORCHESTRATION_PROFILE_DEFAULT,
    orchestration_stages: list[str] | None = None,
    service_scope: list[str] | None = None,
    feature_scope: list[str] | None = None,
    pipeline_decisions: list[dict] | list[OrchestrationDecision] | None = None,
    pipeline_stage_log: list[dict] | None = None,
    hierarchical_analysis: dict | None = None,
) -> dict:
    agent_rankings = _build_agent_rankings(scores, top_k=max(1, len(ranked)))
    consensus = []
    if consensus_summary:
        consensus = list(consensus_summary.get("final_consensus_ids", []))
    research_queries = _build_research_queries(ranked, top_k=min(6, len(ranked)))
    selected = ranked[:len(ranked)]
    agent_decisions = selected_agent_decisions or {}
    orchestration_stages = _normalize_stages(orchestration_stages, fallback=ORCHESTRATION_STAGES_DEFAULT)
    pipeline_decisions = pipeline_decisions or []
    stage_log = pipeline_stage_log or []
    decision_records = [
        decision.to_dict() if isinstance(decision, OrchestrationDecision) else dict(decision)
        for decision in pipeline_decisions
    ]
    result = {
        "report_version": version_tag,
        "report_focus": report_focus,
        "generated_at": dt.datetime.now().isoformat(),
        "topics": [states[k].to_dict() for k in sorted(states)],
        "research_sources": research_sources,
        "agent_scores": scores,
        "agent_scores_initial": scores_initial or scores,
        "debate_rounds_requested": debate_rounds,
        "debate_rounds_executed": len(discussion or []),
        "discussion": discussion or [],
        "strategy_cards": _build_strategy_cards(
            selected,
            [{"phase": "Quick win + low risk", "topics": []}] if not phases else phases,
            states,
            agent_decisions,
            research_sources,
        ),
        "agent_rankings": agent_rankings,
        "agent_decisions": agent_decisions,
        "consensus": consensus,
        "consensus_summary": consensus_summary,
        "research_queries": research_queries,
        "ranked": ranked,
        "phases": phases,
        "orchestration": {
            "profile": orchestration_profile,
            "stages": orchestration_stages,
            "service_scope": service_scope or [],
            "feature_scope": feature_scope or [],
            "pipeline_decisions": decision_records,
            "stage_log": stage_log,
        },
    }
    if hierarchical_analysis:
        result["hierarchical_analysis"] = hierarchical_analysis
    return result


def generate_report(
    workspace: Path,
    top_k: int,
    output_dir: Path,
    output_name: str,
    max_files: int,
    extensions: List[str],
    ignore_dirs: set[str],
    history_files: list[Path],
    report_focus: str = "",
    version_tag: str = "V10",
    debate_rounds: int = DEBATE_ROUNDS_DEFAULT,
    orchestration_profile: str = ORCHESTRATION_PROFILE_DEFAULT,
    orchestration_stages: list[str] | str | None = None,
    service_scope: list[str] | str | None = None,
    feature_scope: list[str] | str | None = None,
    llm_deliberation_cmd: str | None = None,
    llm_deliberation_timeout: float = LLM_DELIBERATION_TIMEOUT_SECONDS,
    llm_consensus_cmd: str | None = None,
    llm_consensus_timeout: float = LLM_CONSENSUS_TIMEOUT_SECONDS,
    agent_mode: str = "flat",
    tier3_debate_rounds: int = 2,
    qa_gate_threshold: float = QA_GATE_THRESHOLD_DEFAULT,
    subordinate_blend: float = SUBORDINATE_BLEND_DEFAULT,
) -> dict:
    agent_mode = (agent_mode or "flat").strip().lower()
    if agent_mode not in ("flat", "hierarchical"):
        agent_mode = "flat"

    profile = (orchestration_profile or ORCHESTRATION_PROFILE_DEFAULT).strip().lower()
    if profile not in ORCHESTRATION_PROFILE_LABELS:
        profile = ORCHESTRATION_PROFILE_DEFAULT
    stages = _normalize_stages(
        orchestration_stages if orchestration_stages is not None else ORCHESTRATION_STAGES_DEFAULT,
        fallback=ORCHESTRATION_STAGES_DEFAULT,
    )
    service_scope_tokens = _parse_service_scope_tokens(service_scope)
    service_scope_list = _build_service_scope(service_scope_tokens)
    if isinstance(feature_scope, str):
        feature_scope_list = [token.strip() for token in feature_scope.split(",") if token.strip()]
    else:
        feature_scope_list = [str(token).strip() for token in (feature_scope or []) if str(token).strip()]
    stage_log: list[dict] = []
    pipeline_decisions: list[OrchestrationDecision] = []

    stage_log.append(
        {
            "stage": ORCHESTRATION_STAGE_ANALYSIS,
            "status": "started",
            "message": f"workspace scan start (service_scope={','.join(service_scope_list)})",
        }
    )
    states = analyze_workspace(
        workspace=workspace,
        extensions=extensions,
        ignore_dirs=ignore_dirs,
        max_files=max_files,
        history_files=history_files,
        service_scope=service_scope_tokens,
    )
    stage_log.append(
        {
            "stage": ORCHESTRATION_STAGE_ANALYSIS,
            "status": "completed",
            "message": f"topic_count={len(states)}",
        }
    )
    # -----------------------------------------------------------------------
    # Hierarchical mode: 4-Tier pipeline
    # -----------------------------------------------------------------------
    if agent_mode == "hierarchical":
        stage_log.append({
            "stage": "hierarchical_pipeline",
            "status": "started",
            "message": f"agent_mode=hierarchical tier3_rounds={tier3_debate_rounds}",
        })
        h_pipeline = _run_hierarchical_pipeline(
            states=states,
            tier3_debate_rounds=max(0, tier3_debate_rounds),
            subordinate_blend=subordinate_blend,
            qa_gate_threshold=qa_gate_threshold,
        )
        ranked = h_pipeline.final_ranking
        stage_log.append({
            "stage": "hierarchical_pipeline",
            "status": "completed",
            "message": f"tiers=4, topics={len(ranked)}",
        })

        selected = ranked[:top_k]
        phases = _build_phase_plan(selected, top_k=top_k)
        synergy = _build_synergy_graph(states, selected)

        # Build a flat-compatible scores dict from hierarchical results for report compatibility
        scores: dict[str, dict[str, float]] = {}
        for topic_id in states:
            per_topic: dict[str, float] = {}
            for tier_num in (1, 2, 3, 4):
                tr = h_pipeline.tier_results.get(tier_num)
                if tr:
                    for ak, av in tr.agent_scores.get(topic_id, {}).items():
                        per_topic[ak] = av
            scores[topic_id] = per_topic

        agent_rankings = _build_agent_rankings(scores, top_k=top_k)

        queries = _build_research_queries(selected, top_k=min(6, top_k))
        output_dir.mkdir(parents=True, exist_ok=True)
        research_sources = _build_sources_file(
            output_dir=output_dir,
            version_tag=version_tag,
            report_focus=report_focus,
            top_topics=selected,
        )

        hierarchical_analysis = {
            "mode": "hierarchical",
            "tier1": {
                "agents": list(TIER_1_AGENTS),
                "scores": h_pipeline.tier_results[1].agent_scores,
            },
            "tier2": {
                "leads": list(TIER_2_DOMAIN_MAP.keys()),
                "scores": h_pipeline.tier_results[2].agent_scores,
                "flags": h_pipeline.tier_results[2].flags,
                "subordinate_blend": subordinate_blend,
            },
            "tier3": {
                "debate_rounds": tier3_debate_rounds,
                "scores": h_pipeline.tier_results[3].agent_scores,
                "debate_log": h_pipeline.tier_results[3].debate_log or [],
                "flags": h_pipeline.tier_results[3].flags,
            },
            "tier4": {
                "scores": h_pipeline.tier_results[4].agent_scores,
                "qa_penalty_topics": h_pipeline.tier_results[4].metadata.get("qa_penalty_applied", []),
            },
            "execution_log": h_pipeline.execution_log,
        }

        markdown = _as_markdown(
            workspace=workspace,
            top_topics=selected,
            states=states,
            scores=scores,
            ranked=ranked,
            agent_rankings=agent_rankings,
            phases=phases,
            synergy_lines=synergy,
            queries=queries,
            report_focus=report_focus,
            version_tag=version_tag,
            research_sources=research_sources,
            orchestration_profile=profile,
            orchestration_stages=stages,
            pipeline_stage_log=stage_log,
            service_scope=service_scope_list,
            feature_scope=feature_scope_list,
            hierarchical_analysis=hierarchical_analysis,
        )

        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        md_path = output_dir / f"{output_name}_{ts}.md"
        js_path = output_dir / f"{output_name}_{ts}.json"

        data = _to_json(
            states=states,
            scores=scores,
            scores_initial=scores,
            ranked=ranked,
            phases=phases,
            report_focus=report_focus,
            version_tag=version_tag,
            research_sources=research_sources,
            orchestration_profile=profile,
            orchestration_stages=stages,
            service_scope=service_scope_list,
            feature_scope=feature_scope_list,
            pipeline_stage_log=stage_log,
            hierarchical_analysis=hierarchical_analysis,
        )
        md_path.write_text(markdown, encoding="utf-8")
        js_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "markdown_path": str(md_path),
            "json_path": str(js_path),
            "agent_rankings": agent_rankings,
            "consensus": [],
            "consensus_summary": {},
            "top_topics": selected,
            "debate_rounds_executed": tier3_debate_rounds,
            "pipeline_decisions": [],
            "orchestration": {
                "profile": profile,
                "stages": stages,
                "service_scope": service_scope_list,
                "feature_scope": feature_scope_list,
                "stage_log": stage_log,
            },
            "hierarchical_analysis": hierarchical_analysis,
            "agent_mode": "hierarchical",
            "generated_at": data["generated_at"],
        }

    # -----------------------------------------------------------------------
    # Flat mode (default): existing 7-agent pipeline — unchanged
    # -----------------------------------------------------------------------
    scores = _init_neutral_agent_scores(states, value=5.0)
    discussion: list[dict] = []

    deliberation_round_limit = ORCHESTRATION_PROFILE_ROUND_LIMITS.get(profile, ORCHESTRATION_PROFILE_ROUND_LIMITS[ORCHESTRATION_PROFILE_DEFAULT])
    requested_rounds = max(0, debate_rounds)
    effective_rounds = min(requested_rounds, deliberation_round_limit)
    llm_deliberation_command = llm_deliberation_cmd or os.getenv(LLM_DELIBERATION_CMD_ENV) or llm_consensus_cmd

    if ORCHESTRATION_STAGE_DELIBERATION in stages and effective_rounds > 0:
        if not llm_deliberation_command:
            raise RuntimeError("LLM deliberation command is required. Set --llm-deliberation-cmd or ORA_RD_LLM_DELIBERATION_CMD.")
        stage_log.append(
            {
                "stage": ORCHESTRATION_STAGE_DELIBERATION,
                "status": "started",
                "message": f"rounds={effective_rounds} profile={profile}",
            }
        )
        for round_no in range(1, effective_rounds + 1):
            ranked_snapshot = _build_final_score(states, scores)
            score_updates, decisions, round_summaries, llm_actions, llm_state = _llm_deliberation_round(
                round_no=round_no,
                stages=stages,
                service_scope=service_scope_list,
                states=states,
                working_scores=scores,
                ranked=ranked_snapshot,
                previous_decisions=[decision.to_dict() for decision in pipeline_decisions],
                previous_discussion=discussion,
                command=llm_deliberation_command,
                timeout=max(1.0, llm_deliberation_timeout),
            )
            for topic_id, per_agent in score_updates.items():
                if topic_id not in scores:
                    continue
                for agent_name, delta in per_agent.items():
                    agent_key = _agent_score_key(agent_name)
                    if agent_key not in scores[topic_id]:
                        continue
                    scores[topic_id][agent_key] = _clamp_score(scores[topic_id][agent_key] + delta, 0.0, 10.0)

            if decisions:
                pipeline_decisions.extend(decisions)
            if round_summaries:
                for summary in round_summaries:
                    if isinstance(summary, dict):
                        discussion.append(summary)
            if llm_actions:
                discussion.append({"round": round_no, "messages": llm_actions, "stage": "llm_action_log"})

            status = llm_state.get("status", "unknown")
            stage_log.append(
                {
                    "stage": ORCHESTRATION_STAGE_DELIBERATION,
                    "status": status,
                    "message": f"round={round_no}, decisions={len(decisions)}",
                }
            )

            if status != "ok":
                if profile == ORCHESTRATION_PROFILE_STRICT:
                    raise RuntimeError(f"LLM deliberation failed at round {round_no}: {llm_state}")
                stage_log.append(
                    {
                        "stage": ORCHESTRATION_STAGE_DELIBERATION,
                        "status": "stopped",
                        "message": f"non-strict early-stop on round={round_no}",
                    }
                )
                break
    else:
        discussion = []

    ranked = _build_final_score(states, scores)

    selected = ranked[:top_k]
    phases = _build_phase_plan(selected, top_k=top_k)
    synergy = _build_synergy_graph(states, selected)
    selected_decisions = _pipeline_decisions_to_topic_records(pipeline_decisions)
    if not pipeline_decisions:
        raise RuntimeError("LLM deliberation produced no decisions. Please adjust LLM command/output schema.")
    agent_rankings = _build_agent_rankings(scores, top_k=top_k, agent_filter=FLAT_MODE_AGENTS)
    if not llm_consensus_cmd and not llm_deliberation_command:
        raise RuntimeError("LLM consensus command is required. Set --llm-consensus-cmd or --llm-deliberation-cmd.")
    consensus_summary = _apply_hybrid_consensus(
        ranked=ranked,
        states=states,
        scores=scores,
        agent_rankings=agent_rankings,
        discussion=discussion,
        top_k=top_k,
        command=llm_consensus_cmd,
        timeout=llm_consensus_timeout,
    )
    if consensus_summary.get("status") != "ok":
        raise RuntimeError(f"LLM consensus failed: {consensus_summary.get('reason', consensus_summary.get('status'))}")
    stage_log.append(
        {
            "stage": ORCHESTRATION_STAGE_DELIBERATION,
            "status": "consensus_completed",
            "message": f"consensus_method={consensus_summary.get('method', 'llm-only')}",
        }
    )

    if ORCHESTRATION_STAGE_EXECUTION in stages:
        stage_log.append(
            {
                "stage": ORCHESTRATION_STAGE_EXECUTION,
                "status": "planned",
                "message": f"decision_objects={len(pipeline_decisions)}",
            }
        )

    queries = _build_research_queries(selected, top_k=min(6, top_k))
    output_dir.mkdir(parents=True, exist_ok=True)
    research_sources = _build_sources_file(
        output_dir=output_dir,
        version_tag=version_tag,
        report_focus=report_focus,
        top_topics=selected,
    )
    markdown = _as_markdown(
        workspace=workspace,
        top_topics=selected,
        states=states,
        scores=scores,
        ranked=ranked,
        agent_rankings=agent_rankings,
        phases=phases,
        synergy_lines=synergy,
        queries=queries,
        report_focus=report_focus,
        version_tag=version_tag,
        agent_decisions=selected_decisions,
        research_sources=research_sources,
        discussion=discussion,
        debate_rounds=debate_rounds,
        consensus_summary=consensus_summary,
        orchestration_profile=profile,
        orchestration_stages=stages,
        pipeline_decisions=pipeline_decisions,
        pipeline_stage_log=stage_log,
        service_scope=service_scope_list,
        feature_scope=feature_scope_list,
    )

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = output_dir / f"{output_name}_{ts}.md"
    js_path = output_dir / f"{output_name}_{ts}.json"

    data = _to_json(
        states=states,
        scores=scores,
        scores_initial=scores,
        ranked=ranked,
        phases=phases,
        report_focus=report_focus,
        version_tag=version_tag,
        research_sources=research_sources,
        selected_agent_decisions=selected_decisions,
        discussion=discussion,
        debate_rounds=debate_rounds,
        consensus_summary=consensus_summary,
        orchestration_profile=profile,
        orchestration_stages=stages,
        service_scope=service_scope_list,
        feature_scope=feature_scope_list,
        pipeline_decisions=pipeline_decisions,
        pipeline_stage_log=stage_log,
    )
    md_path.write_text(markdown, encoding="utf-8")
    js_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "markdown_path": str(md_path),
        "json_path": str(js_path),
        "agent_rankings": agent_rankings,
        "consensus": consensus_summary.get("final_consensus_ids", []),
        "consensus_summary": consensus_summary,
        "top_topics": selected,
        "debate_rounds_executed": len(discussion),
        "pipeline_decisions": [item.to_dict() for item in pipeline_decisions],
        "orchestration": {
            "profile": profile,
            "stages": stages,
            "service_scope": service_scope_list,
            "feature_scope": feature_scope_list,
            "stage_log": stage_log,
        },
        "agent_mode": "flat",
        "generated_at": data["generated_at"],
    }
