from __future__ import annotations

import datetime as dt
import json
import math
import os
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
    },
}

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
    return sorted(candidates)[:max_files]


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


def analyze_workspace(
    workspace: Path,
    extensions: List[str],
    ignore_dirs: set[str],
    max_files: int,
    history_files: list[Path],
) -> dict[str, TopicState]:
    states: dict[str, TopicState] = {
        topic_id: TopicState(topic_id=topic_id, topic_name=details["name"])
        for topic_id, details in TOPICS.items()
    }

    ext_set = {item.lower().lstrip(".") for item in extensions}
    file_paths = _iter_files(workspace, ext_set, set(ignore_dirs), max_files)

    for file_path in file_paths:
        lines = _read_lines(file_path)
        if not lines:
            continue

        is_code_file = file_path.suffix.lower() in {".java", ".kt", ".py", ".ts", ".tsx"}
        project_name = _infer_project_name(workspace, file_path)

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
        ceo = (
            AGENT_WEIGHTS["CEO"]["impact"] * feat["impact"]
            + AGENT_WEIGHTS["CEO"]["novelty"] * feat["novelty"]
            + AGENT_WEIGHTS["CEO"]["feasibility"] * feat["feasibility"]
            + AGENT_WEIGHTS["CEO"]["research_signal"] * feat["research_signal"]
            + AGENT_WEIGHTS["CEO"]["risk"] * feat["risk_penalty"]
        )
        planner = (
            AGENT_WEIGHTS["Planner"]["impact"] * feat["impact"]
            + AGENT_WEIGHTS["Planner"]["novelty"] * feat["novelty"]
            + AGENT_WEIGHTS["Planner"]["feasibility"] * feat["feasibility"]
            + AGENT_WEIGHTS["Planner"]["research_signal"] * feat["research_signal"]
            + AGENT_WEIGHTS["Planner"]["risk"] * feat["risk_penalty"]
        )
        developer = (
            AGENT_WEIGHTS["Developer"]["impact"] * feat["impact"]
            + AGENT_WEIGHTS["Developer"]["novelty"] * feat["novelty"]
            + AGENT_WEIGHTS["Developer"]["feasibility"] * feat["feasibility"]
            + AGENT_WEIGHTS["Developer"]["research_signal"] * feat["research_signal"]
            + AGENT_WEIGHTS["Developer"]["risk"] * feat["risk_penalty"]
        )
        result[topic_id] = {
            "CEO": round(ceo, 2),
            "Planner": round(planner, 2),
            "Developer": round(developer, 2),
        }
    return result


def _build_global_scores(
    scores: dict[str, dict[str, float]],
) -> list[tuple[str, float]]:
    topic_votes = _rank_from_scores(scores)
    totals: list[tuple[str, float]] = []
    for topic_id in scores:
        total = round(
            0.45 * scores[topic_id]["CEO"]
            + 0.25 * scores[topic_id]["Planner"]
            + 0.30 * scores[topic_id]["Developer"]
            + 0.02 * topic_votes[topic_id],
            2,
        )
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

        ranked_by_speaker = sorted(scores.items(), key=lambda item: item[1][speaker], reverse=True)
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
            topic_id: {agent: 0.0 for agent in AGENT_WEIGHTS}
            for topic_id in states
        }

        for msg in messages:
            if msg.topic_id not in working_scores:
                continue
            for target in [msg.speaker] + msg.target_agents:
                trust = AGENT_TRUST.get(msg.speaker, {}).get(target, 0.72)
                weight = DEBATE_INFLUENCE_SELF if target == msg.speaker else DEBATE_INFLUENCE_OTHER
                weight *= trust
                applied_delta = msg.delta * weight * max(0.45, msg.confidence)
                working_scores[msg.topic_id][target] = _clamp_score(
                    working_scores[msg.topic_id][target] + applied_delta,
                    lo=0.0,
                    hi=10.0,
                )
                adjustment_map[msg.topic_id][target] += applied_delta

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
        "CEO": sorted(scores.items(), key=lambda i: i[1]["CEO"], reverse=True),
        "Planner": sorted(scores.items(), key=lambda i: i[1]["Planner"], reverse=True),
        "Developer": sorted(scores.items(), key=lambda i: i[1]["Developer"], reverse=True),
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
        total = round(
            0.45 * scores[topic_id]["CEO"]
            + 0.25 * scores[topic_id]["Planner"]
            + 0.30 * scores[topic_id]["Developer"]
            + 0.02 * topic_votes[topic_id],
            2,
        )
        output.append(
            {
                "topic_id": topic_id,
                "topic_name": state.topic_name,
                "total_score": total,
                "ceo": scores[topic_id]["CEO"],
                "planner": scores[topic_id]["Planner"],
                "developer": scores[topic_id]["Developer"],
                "features": feature,
                "project_count": state.project_count,
                "evidence_count": len(state.evidence),
                "evidence": [e.snippet for e in state.evidence[:4]],
            }
        )
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
            action, reason = _agent_decision(agent, state, feature)
            records.append(
                {
                    "agent": agent,
                    "objective": _agent_role_profile(agent),
                    "decision": action,
                    "reason": reason,
                    "focus": _agent_focus_points(agent),
                    "score": item[agent.lower()] if agent.lower() in item else 0.0,
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


def _build_agent_rankings(scores: dict[str, dict[str, float]], top_k: int) -> dict[str, list[str]]:
    rankings: dict[str, list[str]] = {}
    for agent in AGENT_WEIGHTS:
        ranked_agent = sorted(scores.items(), key=lambda item: item[1][agent], reverse=True)
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
    base_consensus = _build_consensus(agent_rankings, top_k=min(top_k, len(ranked)))
    return {
        "version": "hybrid-consensus-v1",
        "top_k": top_k,
        "agent_consensus": base_consensus,
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
    ranked_map = _topic_item_index(ranked)
    payload = _build_llm_consensus_payload(ranked, states, agent_rankings, discussion, target_size)
    base_consensus = _build_consensus(agent_rankings, top_k=target_size)
    status, llm_result, raw_output = _run_llm_consensus(payload, command=command, timeout=timeout)

    final_candidate = list(base_consensus)
    llm_rationale = "rule_only"
    llm_overall = {"status": status}
    llm_concerns: list[dict[str, str]] = []
    vetoed: list[str] = []
    gated: list[dict[str, str]] = []

    if status == "ok":
        candidate = llm_result.get("final_consensus", llm_result.get("consensus", []))
        if isinstance(candidate, list):
            final_candidate = [topic_id for topic_id in candidate if isinstance(topic_id, str)]
            if final_candidate:
                final_candidate = final_candidate[:target_size]
                llm_rationale = str(llm_result.get("rationale", "")).strip() or llm_rationale
                llm_overall = llm_result
            else:
                final_candidate = list(base_consensus)

        concerns_raw = llm_result.get("concerns", [])
        if isinstance(concerns_raw, list):
            for item in concerns_raw:
                if isinstance(item, str):
                    llm_concerns.append({"topic_id": item, "reason": "LLM 내부 우려 지점으로 표기됨"})
                elif isinstance(item, dict):
                    topic_id = item.get("topic_id")
                    if isinstance(topic_id, str):
                        reason = str(item.get("reason", "")).strip() or "LLM 내부 우려 지점으로 표기됨"
                        llm_concerns.append({"topic_id": topic_id, "reason": reason})
    else:
        llm_overall = {"status": status, "reason": llm_result.get("reason", "llm 미사용/실패")}

    ordered_candidate_ids: list[str] = []
    seen = set[str]()
    for topic_id in final_candidate:
        if topic_id in seen:
            continue
        ordered_candidate_ids.append(topic_id)
        seen.add(topic_id)
    for topic_id in base_consensus:
        if len(ordered_candidate_ids) >= target_size:
            break
        if topic_id in seen:
            continue
        ordered_candidate_ids.append(topic_id)
        seen.add(topic_id)

    gated_consensus: list[str] = []
    for topic_id in ordered_candidate_ids[:target_size]:
        item = ranked_map.get(topic_id)
        state = states.get(topic_id)
        if not item or not state:
            continue
        passed, reason = _consensus_hard_gate(item, state)
        if not passed:
            vetoed.append(topic_id)
            gated.append({"topic_id": topic_id, "reason": reason})
            continue
        gated_consensus.append(topic_id)

    if len(gated_consensus) < target_size:
        # fallback: ensure baseline order and hard-gate constraints with fill-up
        for topic_id in base_consensus:
            if topic_id in gated_consensus:
                continue
            if topic_id in vetoed:
                continue
            item = ranked_map.get(topic_id)
            state = states.get(topic_id)
            if not item or not state:
                continue
            passed, reason = _consensus_hard_gate(item, state)
            if passed:
                gated_consensus.append(topic_id)
            else:
                vetoed.append(topic_id)
                gated.append({"topic_id": topic_id, "reason": reason})
            if len(gated_consensus) >= target_size:
                break

    final_consensus = _dedupe_preserve_order(gated_consensus)[:target_size]
    if len(final_consensus) < target_size:
        for topic_id in base_consensus:
            if topic_id in final_consensus or topic_id in vetoed:
                continue
            item = ranked_map.get(topic_id)
            if not item:
                continue
            state = states.get(topic_id)
            if not state:
                continue
            passed, reason = _consensus_hard_gate(item, state)
            if not passed:
                vetoed.append(topic_id)
                gated.append({"topic_id": topic_id, "reason": reason})
                continue
            final_consensus.append(topic_id)
            if len(final_consensus) >= target_size:
                break

    dedup_vetoed: list[str] = []
    for topic_id in vetoed:
        if topic_id not in dedup_vetoed:
            dedup_vetoed.append(topic_id)

    dedup_gated: list[dict[str, str]] = []
    seen_gated = set[str]()
    for entry in gated:
        key = entry.get("topic_id")
        if not isinstance(key, str) or key in seen_gated:
            continue
        dedup_gated.append(entry)
        seen_gated.add(key)

    return {
        "method": "llm-assisted-hybrid" if status == "ok" else "rule-only",
        "status": status,
        "base_consensus": base_consensus,
        "final_consensus_ids": final_consensus[:target_size],
        "final_rationale": llm_rationale,
        "llm": llm_overall,
        "llm_raw_output": raw_output[:1200] if raw_output else "",
        "concerns": llm_concerns,
        "vetoed": dedup_vetoed,
        "gating": dedup_gated,
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
) -> str:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    topic_name_by_id = {item["topic_id"]: item["topic_name"] for item in ranked}
    sources = research_sources or []
    base_consensus = _build_consensus(agent_rankings, top_k=min(6, len(ranked)))
    final_consensus_ids = (
        consensus_summary.get("final_consensus_ids", [])
        if consensus_summary
        else []
    )
    base_consensus_ids = consensus_summary.get("base_consensus", base_consensus) if consensus_summary else base_consensus
    consensus_lines = [f"- {topic_name_by_id.get(topic_id, topic_id)}" for topic_id in final_consensus_ids]
    base_consensus_lines = [f"- {topic_name_by_id.get(topic_id, topic_id)}" for topic_id in base_consensus_ids]
    if not consensus_lines:
        consensus_lines = base_consensus_lines
    query_lines = [f"- {item['topic_name']}: `{item['web_query']}`" for item in queries]
    strategy_cards = _build_strategy_cards(top_topics, phases, states, agent_decisions, sources)
    source_lines = [
        "- "
        + (f"{item.get('topic', '')}: " if item.get("topic", "") else "")
        + f"[{item.get('title', 'reference')}]({item.get('url', '')})"
        + (f" ({item.get('status', '')})" if item.get("status") else "")
        for item in sources[:20]
    ]

    table_rows = [
        "| 순위 | 주제 | CEO | Planner | Developer | 통합점수 | 피처 점수(영향/실행성/혁신성) |",
        "|---|---|---|---|---|---|---|",
    ]
    for idx, item in enumerate(top_topics, start=1):
        feature = item["features"]
        table_rows.append(
            f"| {idx} | {item['topic_name']} | {item['ceo']} | {item['planner']} | "
            f"{item['developer']} | {item['total_score']} | "
            f"{feature['impact']} / {feature['feasibility']} / {feature['novelty']} |"
        )

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
    sections.append(f"**참여자**: 대표(CEO), 기획자(Planner), 개발자(Developer) 3인 회의")
    sections.append(f"**범위**: `{workspace}`")
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

    sections.append("## 4. 에이전트 합의 논의")
    sections.append("- CEO: 시장성/과제 가능성 중심으로 고점이 높은 주제 우선.")
    sections.append("- Planner: 대화 체감 품질·업무 확장성·데이터 축적 효과를 우선.")
    sections.append("- Developer: 기존 파이프라인 재사용 가능성과 단기 구현 난이도를 우선.")
    sections.append("")
    if consensus_summary:
        sections.append("## 5. LLM 보조 합의 결과")
        sections.append(f"- 합의 방식: {consensus_summary.get('method', 'rule-only')}")
        sections.append(f"- LLM 합의 상태: {consensus_summary.get('status', 'disabled')}")
        sections.append(f"- 최종 후보 반영 사유: {consensus_summary.get('final_rationale', '') or 'rule_only'}")
        base_ids = consensus_summary.get("base_consensus", base_consensus)
        sections.append("- Rule 합의 결과(요약): " + ", ".join(topic_name_by_id.get(topic_id, topic_id) for topic_id in base_ids))
        sections.append("- LLM/하드게이트 최종 합의: " + ", ".join(topic_name_by_id.get(topic_id, topic_id) for topic_id in final_consensus_ids))
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
    sections.append("## 6. 구현 권장 로드맵")
    sections.extend(phases_md if phases_md else ["- 해당 토픽의 근거가 부족하여 즉시 실행 불가"])
    sections.append("")
    sections.append("## 7. 시너지 추정")
    sections.extend(synergy_lines if synergy_lines else ["- 현재 증거 기반 교집합이 적어 정책/UX/모니터링 레이어 기준으로 간접 연계 권장"])
    sections.append("")
    sections.append("## 8. 협력 에이전트 Top3")
    for agent, top_ids in agent_rankings.items():
        sections.append(f"### {agent}")
        for idx, topic_id in enumerate(top_ids[:3], start=1):
            sections.append(f"- {idx}위: {topic_name_by_id.get(topic_id, topic_id)} ({scores[topic_id][agent]})")
    sections.append("")
    sections.append("## 9. 합의 후보")
    sections.extend(consensus_lines if consensus_lines else ["- 3인 공통 상위 항목이 부족함"])
    sections.append("")
    sections.append("## 10. 자동 웹 검증 큐")
    sections.extend(query_lines if query_lines else ["- 이번 분석에서 생성된 후보 쿼리 없음"])
    sections.append("")
    sections.append("## 11. 연구 근거 후보")
    sections.extend(source_lines if source_lines else ["- 연구 출처 후보가 부족함"])
    sections.append("")
    sections.append("## 12. 상위 주제 근거 (최대 1개 발췌 근거)")
    sections.extend(evidence_md if evidence_md else ["- 상위 항목 근거가 충분히 수집되지 않음"])

    sections.append("")
    executed_rounds = len(discussion or [])
    sections.append(f"## 13. 에이전트 토론 로그 (요청 {debate_rounds}라운드 / 실행 {executed_rounds}라운드)")
    if not discussion:
        sections.append("- 이번 실행에서 토론 로그 미생성")
    else:
        for round_log in discussion:
            sections.append(f"### Round {round_log['round']}")
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

    return "\n".join(sections) + "\n\n"


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
) -> dict:
    agent_rankings = _build_agent_rankings(scores, top_k=max(1, len(ranked)))
    consensus = _build_consensus(agent_rankings, top_k=min(8, len(ranked)))
    research_queries = _build_research_queries(ranked, top_k=min(6, len(ranked)))
    selected = ranked[:len(ranked)]
    agent_decisions = selected_agent_decisions or _build_agent_decisions(selected, states)
    return {
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
    }


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
    llm_consensus_cmd: str | None = None,
    llm_consensus_timeout: float = LLM_CONSENSUS_TIMEOUT_SECONDS,
) -> dict:
    states = analyze_workspace(
        workspace=workspace,
        extensions=extensions,
        ignore_dirs=ignore_dirs,
        max_files=max_files,
        history_files=history_files,
    )
    base_scores = score_by_agents(states)
    discussed_scores, discussion = simulate_roundtable_deliberation(
        states=states,
        initial_scores=base_scores,
        rounds=max(0, debate_rounds),
    )
    scores = discussed_scores
    ranked = _build_final_score(states, scores)

    selected = ranked[:top_k]
    phases = _build_phase_plan(selected, top_k=top_k)
    synergy = _build_synergy_graph(states, selected)
    all_decisions = _build_agent_decisions(ranked, states)
    selected_decisions = {topic_id: all_decisions.get(topic_id, []) for topic_id in [item["topic_id"] for item in selected]}
    agent_rankings = _build_agent_rankings(scores, top_k=top_k)
    consensus = _build_consensus(agent_rankings, top_k=min(6, len(ranked)))
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
    )

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = output_dir / f"{output_name}_{ts}.md"
    js_path = output_dir / f"{output_name}_{ts}.json"

    data = _to_json(
        states=states,
        scores=scores,
        scores_initial=base_scores,
        ranked=ranked,
        phases=phases,
        report_focus=report_focus,
        version_tag=version_tag,
        research_sources=research_sources,
        selected_agent_decisions=selected_decisions,
        discussion=discussion,
        debate_rounds=debate_rounds,
        consensus_summary=consensus_summary,
    )
    md_path.write_text(markdown, encoding="utf-8")
    js_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "markdown_path": str(md_path),
        "json_path": str(js_path),
        "agent_rankings": agent_rankings,
        "consensus": consensus_summary.get("final_consensus_ids", consensus),
        "consensus_summary": consensus_summary,
        "top_topics": selected,
        "debate_rounds_executed": len(discussion),
        "generated_at": data["generated_at"],
    }
