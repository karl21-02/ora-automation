# Ora Automation Enhancement Plan

> 전체 고도화 계획 문서. 모든 개선은 **LLM-Native** 방식으로 구현하며, 하드코딩이나 규칙 기반 로직은 사용하지 않음.

## Overview

현재 시스템의 강점을 유지하면서 7가지 영역을 고도화한다:

| Phase | 영역 | 설명 | 우선순위 |
|-------|------|------|----------|
| A | 신뢰도 기반 가중치 | LLM이 에이전트별 confidence를 판단하여 가중 평균 | P1 |
| B | 동적 대표 선정 | LLM이 Chapter 토론 후 적합한 대표 선정 | P1 |
| C | 다중 관점 합의 | 여러 렌즈(impact, risk, speed 등)로 복수 추천 생성 | P2 |
| D | 토론 구조화 | 주장→반박→중재 프롬프트 구조 제공 | P2 |
| E | 에이전트 진화 | 과거 결과 기반 weights/trust_map 자동 조정 | P3 |
| F | 리서치 확장 | GitHub, HuggingFace, 트렌드 분석 소스 추가 | P2 |
| G | 아이디어→프로젝트 | 프로젝트 없이 아이디어만으로 시작 지원 | P3 |

---

## Phase A: 신뢰도 기반 가중치 (Confidence-Based Weighting)

### 현재 상태
```python
# deliberation.py - 단순 평균
avg = sum(values) / len(values)
```

모든 에이전트의 점수가 동일한 비중으로 평균됨.

### 목표
LLM이 각 에이전트의 **confidence (0.0 ~ 1.0)**를 함께 출력하고, 가중 평균에 반영.

### 구현 방향

**1. LLM 출력 스키마 확장**
```json
{
  "score_adjustments": {
    "topic_1": {
      "agent_a": {"delta": 1.5, "confidence": 0.9},
      "agent_b": {"delta": -0.5, "confidence": 0.6}
    }
  }
}
```

**2. 가중 평균 계산**
```python
def weighted_average(scores_with_confidence: list[tuple[float, float]]) -> float:
    """LLM이 출력한 confidence를 가중치로 사용"""
    total_weight = sum(conf for _, conf in scores_with_confidence)
    if total_weight == 0:
        return sum(s for s, _ in scores_with_confidence) / len(scores_with_confidence)
    return sum(s * c for s, c in scores_with_confidence) / total_weight
```

**3. 프롬프트 수정**
- deliberation 프롬프트에 confidence 출력 지시 추가
- "각 점수 조정에 대해 0.0~1.0 사이의 확신도를 함께 제공하세요"

### 영향 범위
- `src/ora_rd_orchestrator/deliberation.py`
- `src/ora_rd_orchestrator/convergence.py`
- LLM 프롬프트 템플릿

### 예상 효과
- 확신 있는 에이전트의 의견이 더 큰 영향력
- 불확실한 상황에서 더 보수적인 합의
- 점수 변동의 이유 추적 가능

---

## Phase B: 동적 대표 선정 (Dynamic Representative Selection)

### 현재 상태
```python
# convergence.py
rep_agents.append(cr["agent_ids"][0])  # 첫 번째 에이전트 (임의)
```

Level 2 Silo 토론에서 Chapter 대표가 리스트 첫 번째로 고정됨.

### 목표
Level 1 Chapter 토론 결과를 바탕으로 LLM이 **가장 적합한 대표**를 선정.

### 구현 방향

**1. 대표 선정 LLM 호출 추가**
```python
def select_chapter_representative(
    chapter_id: str,
    agents: list[str],
    deliberation_history: list[dict],
    scores: dict[str, dict[str, float]]
) -> str:
    """LLM이 Chapter 토론 결과를 보고 대표 선정"""
    prompt = f"""
    Chapter '{chapter_id}'의 토론이 완료되었습니다.

    참여 에이전트: {agents}
    토론 히스토리: {deliberation_history}
    최종 점수: {scores}

    이 Chapter를 Silo 레벨에서 대표할 가장 적합한 에이전트를 선택하세요.

    선정 기준:
    - 토론에서 균형 잡힌 시각을 보여줬는가
    - 다른 에이전트들의 의견을 잘 종합했는가
    - Chapter의 전문성을 대표할 수 있는가

    반환 형식:
    {{"representative": "agent_id", "rationale": "선정 이유"}}
    """
    return llm_call(prompt)
```

**2. 수렴 파이프라인 수정**
- Level 1 완료 후 → 대표 선정 LLM 호출
- 선정된 대표로 Level 2 진행

### 영향 범위
- `src/ora_rd_orchestrator/convergence.py`
- 새 함수: `select_chapter_representative()`

### 예상 효과
- Chapter 의견을 더 정확히 대표
- 토론 맥락이 Silo 레벨로 전달
- 선정 이유 로깅으로 투명성 확보

---

## Phase C: 다중 관점 합의 (Multi-Perspective Consensus)

### 현재 상태
```python
# consensus.py
final_consensus_ids = [...]  # 단일 Top K 리스트
```

하나의 관점(종합 점수)으로만 토픽 선정.

### 목표
**여러 렌즈**로 복수의 추천 생성:
- `max_impact`: 비즈니스 임팩트 최대화
- `min_risk`: 리스크 최소화
- `quick_wins`: 빠른 실행 가능
- `strategic_moat`: 장기 경쟁력

### 구현 방향

**1. 합의 출력 스키마 확장**
```json
{
  "perspectives": {
    "max_impact": {
      "topics": ["topic_1", "topic_3"],
      "rationale": "시장 규모와 성장률 기준"
    },
    "min_risk": {
      "topics": ["topic_2", "topic_5"],
      "rationale": "기술 성숙도와 팀 역량 기준"
    },
    "quick_wins": {
      "topics": ["topic_4"],
      "rationale": "3개월 내 출시 가능"
    },
    "strategic_moat": {
      "topics": ["topic_1", "topic_6"],
      "rationale": "경쟁사 진입 장벽 구축"
    }
  },
  "primary_recommendation": ["topic_1", "topic_3", "topic_2"],
  "synthesis": "전체 균형을 고려한 최종 추천 근거"
}
```

**2. 프롬프트 수정**
```
당신은 최종 합의를 도출하는 의사결정자입니다.

각 관점별로 추천 토픽을 선정하세요:
1. max_impact: 비즈니스 임팩트가 가장 큰 토픽
2. min_risk: 리스크가 가장 낮은 토픽
3. quick_wins: 빠르게 실행 가능한 토픽
4. strategic_moat: 장기 경쟁력을 구축하는 토픽

그 다음, 모든 관점을 종합한 primary_recommendation을 제시하세요.
```

### 영향 범위
- `src/ora_rd_orchestrator/consensus.py`
- `src/ora_rd_orchestrator/report_builder.py` (리포트에 다중 관점 표시)
- 프론트엔드: 관점별 탭/필터 UI

### 예상 효과
- 의사결정자가 상황에 맞는 추천 선택 가능
- "왜 이 토픽인가"에 대한 다양한 근거 제공
- 리스크 회피형 vs 공격적 전략 선택 지원

---

## Phase D: 토론 구조화 (Structured Debate Prompts)

### 현재 상태
자유 형식 LLM 추론. 에이전트 간 상호작용이 명시적이지 않음.

### 목표
**주장 → 반박 → 중재** 구조로 토론 품질 향상.

### 구현 방향

**1. 라운드별 역할 분리**
```python
def structured_deliberation_round(
    topic: str,
    agents: list[Agent],
    current_scores: dict,
    round_num: int
) -> dict:
    # Step 1: 주장 (Advocate)
    advocates = get_high_scorers(current_scores, topic)
    advocate_prompt = f"""
    당신은 {topic}의 지지자입니다.
    현재 점수: {current_scores[topic]}

    이 토픽을 지지하는 3가지 핵심 논거를 제시하세요.
    """
    advocate_arguments = llm_call(advocate_prompt)

    # Step 2: 반박 (Challenger)
    challengers = get_low_scorers(current_scores, topic)
    challenger_prompt = f"""
    당신은 {topic}에 대한 비판자입니다.
    지지자 논거: {advocate_arguments}

    각 논거에 대한 반박을 제시하세요.
    """
    challenger_arguments = llm_call(challenger_prompt)

    # Step 3: 중재 (Mediator)
    mediator_prompt = f"""
    지지 논거: {advocate_arguments}
    반박 논거: {challenger_arguments}

    양측 의견을 종합하여:
    1. 합의 가능한 점수 범위를 제안하세요
    2. 해결되지 않은 쟁점을 정리하세요
    3. 다음 라운드에서 검토할 사항을 제시하세요
    """
    mediation_result = llm_call(mediator_prompt)

    return {
        "advocate": advocate_arguments,
        "challenger": challenger_arguments,
        "mediation": mediation_result,
        "proposed_scores": extract_scores(mediation_result)
    }
```

**2. 토론 히스토리 구조화**
```json
{
  "round_1": {
    "topic_1": {
      "advocate": {"agents": ["PM", "CEO"], "arguments": [...]},
      "challenger": {"agents": ["DevOps", "QA"], "arguments": [...]},
      "mediation": {"proposed_score": 7.2, "unresolved": [...]}
    }
  }
}
```

### 영향 범위
- `src/ora_rd_orchestrator/deliberation.py`
- 새 함수들: `get_advocates()`, `get_challengers()`, `mediate()`

### 예상 효과
- 토론 과정이 명확하고 추적 가능
- 양측 의견이 균형 있게 반영
- 수렴 속도 향상 (구조화된 협상)

---

## Phase E: 에이전트 진화 (Agent Evolution System)

### 현재 상태
에이전트 weights, trust_map이 고정 (YAML 또는 DB).

### 목표
과거 오케스트레이션 결과를 바탕으로 LLM이 **에이전트 파라미터 조정 제안**.

### 구현 방향

**1. 실행 결과 평가 수집**
```python
# 새 테이블: agent_performance
class AgentPerformance(Base):
    id: str
    agent_id: str
    run_id: str
    topic_id: str
    predicted_score: float  # 에이전트가 준 점수
    actual_outcome: float   # 실제 결과 (사용자 피드백 또는 후속 분석)
    accuracy_delta: float   # |predicted - actual|
    created_at: datetime
```

**2. 진화 제안 LLM 호출**
```python
def suggest_agent_evolution(
    agent_id: str,
    performance_history: list[AgentPerformance],
    current_weights: dict,
    current_trust_map: dict
) -> dict:
    prompt = f"""
    에이전트 '{agent_id}'의 최근 성과:
    {performance_history}

    현재 설정:
    - weights: {current_weights}
    - trust_map: {current_trust_map}

    성과 분석 결과를 바탕으로 다음을 제안하세요:
    1. weights 조정 (어떤 요소의 비중을 높이거나 낮출지)
    2. trust_map 조정 (어떤 에이전트를 더/덜 신뢰할지)
    3. behavioral_directives 추가/수정 제안

    반환 형식:
    {{
      "weights_adjustment": {{"impact": +0.05, "feasibility": -0.03}},
      "trust_adjustment": {{"PM": +0.1, "DevOps": -0.05}},
      "directive_suggestions": ["새로운 지침..."],
      "rationale": "조정 이유"
    }}
    """
    return llm_call(prompt)
```

**3. 관리자 승인 플로우**
- LLM 제안은 `pending_evolutions` 테이블에 저장
- 관리자가 UI에서 검토 후 승인/거부
- 승인 시 실제 에이전트 설정에 반영

### 영향 범위
- 새 테이블: `agent_performance`, `pending_evolutions`
- 새 API: `/api/v1/agents/{id}/evolution`
- 프론트엔드: 진화 제안 검토 UI

### 예상 효과
- 에이전트가 시간이 지남에 따라 개선
- 조직의 실제 의사결정 패턴 학습
- 신뢰할 수 있는 에이전트 자동 발굴

---

## Phase F: 리서치 소스 확장 (Research Source Expansion)

### 현재 상태
5개 학술 소스: ArXiv, Crossref, OpenAlex, Semantic Scholar, Google Scholar

### 목표
**실무 관련 소스** 추가:
- GitHub (코드, 트렌딩 레포)
- HuggingFace (모델, 데이터셋)
- Papers With Code (구현체)
- 기술 블로그 (Medium, dev.to)
- 뉴스/트렌드

### 구현 방향

**1. 새 리서치 클라이언트 추가**

```python
# research.py에 추가

async def search_github(query: str, limit: int = 10) -> list[dict]:
    """GitHub 코드/레포 검색"""
    # GitHub Search API 사용
    # 트렌딩 레포, 관련 코드 스니펫 반환

async def search_huggingface(query: str, limit: int = 10) -> list[dict]:
    """HuggingFace 모델/데이터셋 검색"""
    # HuggingFace Hub API 사용
    # 관련 모델, 데이터셋, Spaces 반환

async def search_papers_with_code(query: str, limit: int = 10) -> list[dict]:
    """Papers With Code 검색"""
    # 논문 + 구현체 함께 반환

async def search_tech_blogs(query: str, limit: int = 10) -> list[dict]:
    """기술 블로그 검색 (LLM으로 관련성 필터링)"""
    # Medium, dev.to, 회사 기술 블로그 크롤링
    # LLM으로 관련성 점수 매기기
```

**2. 소스 통합 및 중복 제거**
```python
async def build_comprehensive_sources(topics: list[str]) -> dict:
    """모든 소스에서 검색 후 LLM으로 통합"""
    all_sources = await asyncio.gather(
        search_arxiv(topics),
        search_github(topics),
        search_huggingface(topics),
        search_papers_with_code(topics),
        search_tech_blogs(topics),
    )

    # LLM으로 중복 제거 및 관련성 순위 매기기
    prompt = f"""
    다음 리서치 소스들을 분석하세요:
    {all_sources}

    1. 중복된 항목을 식별하고 제거하세요
    2. 각 토픽별로 관련성 순으로 정렬하세요
    3. 핵심 인사이트를 요약하세요
    """
    return llm_call(prompt)
```

### 영향 범위
- `src/ora_rd_orchestrator/research.py`
- `src/ora_rd_orchestrator/config.py` (새 API 키 환경변수)
- `src/ora_rd_orchestrator/pipeline.py` (소스 통합)

### 예상 효과
- 학술 논문 + 실제 구현체 연결
- 트렌드 파악 (GitHub 스타, HuggingFace 다운로드)
- 더 실용적인 리서치 결과

---

## Phase G: 아이디어→프로젝트 파이프라인 (Idea-to-Project Pipeline)

### 현재 상태
기존 프로젝트 디렉토리 스캔 → 분석 → 리포트

프로젝트가 없으면 시작 불가.

### 목표
**아이디어만으로 시작**:
1. 사용자 아이디어 인터뷰 (슬롯 필링)
2. 시장/기술 리서치
3. 에이전트 deliberation으로 방향 결정
4. 프로젝트 구조 생성 (선택적)

### 구현 방향

**1. 아이디어 인터뷰 플로우**
```python
# dialog_engine.py에 새 인텐트 추가

IDEA_INTERVIEW_SLOTS = [
    "problem_statement",    # 해결하려는 문제
    "target_users",         # 타겟 사용자
    "unique_value",         # 차별화 포인트
    "technical_approach",   # 기술적 접근 (선택)
    "constraints",          # 제약 조건 (예산, 시간, 팀)
]

async def interview_idea(conversation_history: list) -> dict:
    """LLM이 사용자 아이디어를 인터뷰"""
    prompt = f"""
    사용자가 새로운 서비스/프로젝트 아이디어를 가지고 있습니다.
    대화 기록: {conversation_history}

    아직 수집되지 않은 정보를 자연스럽게 질문하세요:
    - 필수: {IDEA_INTERVIEW_SLOTS}

    사용자가 모호하게 답하면 구체적인 예시를 들어 clarify하세요.
    충분한 정보가 모이면 요약을 제시하고 확인받으세요.
    """
    return llm_call(prompt)
```

**2. 아이디어 기반 리서치**
```python
async def research_idea(idea_summary: dict) -> dict:
    """아이디어를 바탕으로 시장/기술 리서치"""
    # 경쟁사 분석
    competitors = await search_competitors(idea_summary["problem_statement"])

    # 기술 트렌드
    tech_trends = await search_tech_trends(idea_summary["technical_approach"])

    # 시장 규모 (가능하면)
    market_data = await search_market_data(idea_summary["target_users"])

    # LLM으로 종합
    prompt = f"""
    아이디어: {idea_summary}
    경쟁사: {competitors}
    기술 트렌드: {tech_trends}
    시장 데이터: {market_data}

    이 아이디어에 대한 종합 분석을 제공하세요:
    1. 기회 요소
    2. 위험 요소
    3. 추천 접근법
    4. 우선 검증해야 할 가설
    """
    return llm_call(prompt)
```

**3. 에이전트 Deliberation (기존 파이프라인 재사용)**
```python
async def deliberate_idea(idea_summary: dict, research_results: dict) -> dict:
    """에이전트들이 아이디어에 대해 토론"""
    # 가상의 "토픽"으로 변환
    topics = [
        {"id": "idea_main", "label": idea_summary["problem_statement"], ...},
        # 세부 기능/접근법을 서브 토픽으로
    ]

    # 기존 convergence 파이프라인 실행
    return await run_convergence_pipeline(topics, org_config)
```

**4. 프로젝트 생성 (선택적)**
```python
async def generate_project_structure(
    idea_summary: dict,
    deliberation_result: dict,
    tech_stack: str  # LLM 추천 또는 사용자 선택
) -> dict:
    """프로젝트 scaffold 생성"""
    prompt = f"""
    아이디어: {idea_summary}
    에이전트 deliberation 결과: {deliberation_result}
    기술 스택: {tech_stack}

    이 프로젝트의 초기 구조를 생성하세요:
    1. 디렉토리 구조
    2. 핵심 파일 목록
    3. README.md 초안
    4. 첫 번째 마일스톤 정의

    실제 코드는 생성하지 말고 구조와 설명만 제공하세요.
    """
    return llm_call(prompt)
```

### 영향 범위
- `src/ora_automation_api/dialog_engine.py` (새 인텐트)
- 새 모듈: `src/ora_automation_api/idea_pipeline.py`
- 프론트엔드: 아이디어 인터뷰 UI

### 예상 효과
- 프로젝트 없이도 Ora 사용 가능
- 아이디어 단계에서 에이전트 인사이트 활용
- 빠른 가설 검증 지원

---

## Implementation Timeline

```
Phase A (신뢰도 가중치)     ████░░░░░░  2-3일
Phase B (동적 대표 선정)    ████░░░░░░  2-3일
Phase C (다중 관점 합의)    ██████░░░░  3-4일
Phase D (토론 구조화)       ██████░░░░  3-4일
Phase E (에이전트 진화)     ████████░░  5-7일
Phase F (리서치 확장)       ██████░░░░  3-4일
Phase G (아이디어 파이프라인) ████████░░  5-7일
```

총 예상: 3-4주 (순차적 진행 시)

---

## Success Metrics

| Phase | 측정 지표 |
|-------|----------|
| A | 합의 품질 향상 (사용자 만족도) |
| B | Chapter 대표 적합도 (LLM 자체 평가) |
| C | 의사결정 다양성 (관점별 추천 분포) |
| D | 토론 수렴 속도 (라운드 수 감소) |
| E | 예측 정확도 향상 (delta 감소) |
| F | 리서치 커버리지 (소스당 유용 결과 수) |
| G | 아이디어→실행 전환율 |

---

## Dependencies & Prerequisites

- **LLM API**: Gemini (기본), OpenAI (폴백)
- **새 API 키** (Phase F):
  - `GITHUB_TOKEN`
  - `HUGGINGFACE_TOKEN`
- **DB 마이그레이션** (Phase E):
  - `agent_performance` 테이블
  - `pending_evolutions` 테이블

---

## 원칙

1. **No Hardcoding**: 모든 로직은 LLM이 판단
2. **Gradual Rollout**: 각 Phase 독립적으로 배포 가능
3. **Backwards Compatible**: 기존 기능 유지
4. **Observable**: 모든 LLM 호출 로깅
5. **Testable**: 각 Phase별 테스트 케이스
