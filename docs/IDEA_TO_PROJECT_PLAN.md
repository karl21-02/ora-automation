# Idea-to-Project Pipeline (Phase G)

> 아이디어만으로 프로젝트 검증 및 시작을 지원하는 독립 기능

## Overview

### 기존 Ora vs 아이디어→프로젝트

| 구분 | 기존 Ora (프로젝트 분석) | 아이디어→프로젝트 |
|------|--------------------------|-------------------|
| **입력** | 이미 존재하는 코드베이스 | 아이디어 (텍스트/대화) |
| **핵심 질문** | "이 프로젝트의 R&D 방향은?" | "이걸 시작할 가치가 있는가?" |
| **출력** | 전략 리포트, 우선순위 | Go/No-Go, MVP, 검증 계획 |
| **사용자** | 기존 프로젝트 팀 | 창업자, PM, 기획자 |

**핵심**: 완전히 독립적인 기능. 기존 파이프라인과 공유할 수 있는 부분은 재사용하되, 별도 진입점과 출력 형식 필요.

---

## 설계 원칙

### 토스 스타일 적용

1. **빠른 피드백**: 5분 내 초기 Go/No-Go 판단
2. **데이터 기반**: "느낌"이 아닌 시장/경쟁사 데이터
3. **최소 MVP**: 복잡한 기능 X, 핵심만
4. **LLM-Native**: 하드코딩된 슬롯/규칙 없음

### 재사용 vs 신규

| 재사용 (기존 모듈) | 신규 개발 |
|-------------------|-----------|
| 리서치 클라이언트 (Phase F) | 아이디어 분석 프롬프트 |
| 구조화 토론 (Phase D) | Go/No-Go 결정 로직 |
| 에이전트 진화 (Phase E) | MVP 정의 출력 형식 |
| LLM 클라이언트 | 아이디어 전용 에이전트 (선택) |

---

## 사용자 시나리오

### 시나리오 1: Quick Check (5분)

```
사용자: "음성으로 회의록 자동 작성하는 서비스 어때?"

Ora: [즉시 분석]
├── 초기 점수: 7.2/10
├── 유사 제품: Otter.ai, Fireflies, Clova Note
├── 차별화 필요: 한국어 특화, 실시간 액션아이템
├── 시장: 성장 중 (연 20% CAGR)
└── 판정: GO - 단, 차별화 필수

다음 질문:
- 타겟 기업 규모는? (스타트업/중견/대기업)
- 기존에 쓰는 회의 툴이 있나요?
```

### 시나리오 2: Deep Dive (30분)

```
사용자: "구체적으로 분석해줘"

Ora: [병렬 리서치 실행]
├── 경쟁사 분석
│   ├── Otter.ai: 영어 중심, $20/월
│   ├── Fireflies: 화상회의 통합 강점
│   └── Clova Note: 한국어, 무료, 기능 제한
├── 기술 검증
│   ├── Whisper: 한국어 정확도 85%
│   ├── 실시간 처리: 가능 (latency 2-3초)
│   └── 액션아이템 추출: GPT-4로 가능
└── 시장 규모
    └── 한국 기업용 협업툴 시장: 1.2조원

[에이전트 Deliberation]
├── CEO: 전략적으로 B2B SaaS 적합
├── PM: MVP 3개월 내 가능
├── DevLead: Whisper + GPT-4 조합 검증됨
└── 합의: GO (점수 7.8)
```

### 시나리오 3: MVP 정의

```
Ora: [MVP 제안]

핵심 가설:
"한국어 회의에서 액션아이템 추출 정확도 > 80%"

MVP 범위 (4주):
1. 실시간 음성 전사 (Whisper)
2. 액션아이템 자동 추출 (GPT-4)
3. 슬랙 연동

제외 (나중에):
- 화상회의 통합
- 다국어 지원
- 모바일 앱

검증 계획:
- Week 1: 10개 팀 인터뷰
- Week 2: 프로토타입 개발
- Week 3: 5개 팀 베타 테스트
- Week 4: 피드백 반영

Kill Criteria:
- 정확도 < 60%
- 10팀 중 8팀 이상 "안 쓸 것 같다"
```

---

## 기술 설계

### 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                     Idea-to-Project Pipeline                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐                                               │
│  │ 입력 처리    │  ← 텍스트, 대화, (피치덱)                     │
│  └──────┬───────┘                                               │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐     ┌─────────────────────────────────────┐   │
│  │ Quick Check  │ ──> │ 즉시 분석 (LLM 1회 호출)             │   │
│  │ (5분 내)     │     │ - 초기 점수                          │   │
│  └──────┬───────┘     │ - 유사 제품                          │   │
│         │             │ - 차별화 포인트                       │   │
│         │             │ - Go/Pivot/No-Go                      │   │
│         │             └─────────────────────────────────────┘   │
│         │                                                        │
│         │ (Go인 경우)                                           │
│         ▼                                                        │
│  ┌──────────────┐     ┌─────────────────────────────────────┐   │
│  │ Deep Dive    │ ──> │ 병렬 리서치 (Phase F 재사용)          │   │
│  │ (30분)       │     │ - 경쟁사 분석                         │   │
│  └──────┬───────┘     │ - 기술 검증                          │   │
│         │             │ - 시장 규모                          │   │
│         │             └─────────────────────────────────────┘   │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐     ┌─────────────────────────────────────┐   │
│  │ Deliberation │ ──> │ 구조화 토론 (Phase D 재사용)          │   │
│  │              │     │ - 에이전트 의견 수렴                  │   │
│  └──────┬───────┘     │ - 최종 Go/No-Go                      │   │
│         │             └─────────────────────────────────────┘   │
│         │                                                        │
│         ▼                                                        │
│  ┌──────────────┐     ┌─────────────────────────────────────┐   │
│  │ MVP 정의     │ ──> │ 출력 생성                             │   │
│  │              │     │ - 핵심 가설                          │   │
│  └──────────────┘     │ - MVP 범위                           │   │
│                       │ - 검증 계획                          │   │
│                       │ - Kill Criteria                      │   │
│                       └─────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 데이터 모델

```python
@dataclass
class IdeaInput:
    """사용자 아이디어 입력."""
    raw_text: str                      # 원본 텍스트
    conversation_history: list[dict]   # 대화 기록 (있으면)
    context: dict                      # 추가 맥락 (선택)


@dataclass
class QuickCheckResult:
    """5분 내 빠른 분석 결과."""
    initial_score: float               # 0.0 ~ 10.0
    verdict: str                       # "GO" | "PIVOT" | "NO_GO"
    similar_products: list[dict]       # 유사 제품들
    differentiation_needed: list[str]  # 차별화 필요 포인트
    market_signal: str                 # 시장 신호 요약
    next_questions: list[str]          # 다음 질문들
    confidence: float                  # 분석 신뢰도


@dataclass
class DeepDiveResult:
    """심층 분석 결과."""
    competitor_analysis: dict          # 경쟁사 분석
    tech_validation: dict              # 기술 검증
    market_sizing: dict                # 시장 규모
    deliberation_result: dict          # 에이전트 토론 결과
    final_score: float                 # 최종 점수
    final_verdict: str                 # 최종 판정


@dataclass
class MVPDefinition:
    """MVP 정의."""
    core_hypothesis: str               # 핵심 가설
    mvp_scope: list[str]               # MVP 범위
    excluded_features: list[str]       # 제외 기능
    validation_plan: list[dict]        # 주차별 검증 계획
    kill_criteria: list[str]           # 중단 조건
    estimated_timeline: str            # 예상 기간
    required_resources: dict           # 필요 리소스


@dataclass
class IdeaToProjectResult:
    """전체 파이프라인 결과."""
    idea_input: IdeaInput
    quick_check: QuickCheckResult
    deep_dive: DeepDiveResult | None   # Go인 경우만
    mvp: MVPDefinition | None          # Go인 경우만
    created_at: str
```

### API 설계

```python
# 새 라우터: idea_router.py

# 1. Quick Check (즉시 응답)
POST /api/v1/ideas/quick-check
Body: { "idea": "음성 회의록 서비스", "context": {} }
Response: QuickCheckResult

# 2. Deep Dive (비동기, 진행상황 SSE)
POST /api/v1/ideas/deep-dive
Body: { "idea": "...", "quick_check_id": "..." }
Response: { "job_id": "..." }

GET /api/v1/ideas/deep-dive/{job_id}/stream
Response: SSE events (progress, result)

# 3. MVP 정의
POST /api/v1/ideas/{idea_id}/mvp
Body: { "deep_dive_id": "...", "preferences": {} }
Response: MVPDefinition

# 4. 전체 결과 조회
GET /api/v1/ideas/{idea_id}
Response: IdeaToProjectResult
```

---

## 에이전트 구성

### 옵션 1: 기존 에이전트 재사용

| 에이전트 | 아이디어 검증 역할 |
|----------|-------------------|
| CEO | 전략적 적합성, 시장 타이밍 |
| PM | 실행 가능성, MVP 범위 |
| DevLead | 기술 리스크, 구현 복잡도 |
| Researcher | 시장/경쟁사 분석 |
| DataAnalyst | 데이터 기반 검증 |

### 옵션 2: 아이디어 전용 에이전트 추가

| 신규 에이전트 | 역할 |
|--------------|------|
| Investor | 투자 관점, 수익 모델 평가 |
| MarketAnalyst | 시장 규모, 성장률 분석 |
| UserAdvocate | 사용자 관점, 페인포인트 검증 |
| Skeptic | Devil's Advocate, 리스크 발굴 |

### 권장: 옵션 1 + Skeptic

- 기존 에이전트 재사용으로 복잡성 최소화
- Skeptic만 추가하여 아이디어 검증에 특화된 비판적 시각 확보

---

## 구현 단계

### Phase G-1: Quick Check (MVP)
- [ ] IdeaInput, QuickCheckResult 데이터 모델
- [ ] quick_check() LLM 함수
- [ ] POST /api/v1/ideas/quick-check 엔드포인트
- [ ] 테스트

### Phase G-2: Deep Dive
- [ ] DeepDiveResult 데이터 모델
- [ ] 경쟁사 분석 (Phase F 재사용)
- [ ] 기술 검증 (LLM)
- [ ] 시장 규모 추정 (LLM)
- [ ] Deliberation 연동 (Phase D 재사용)
- [ ] SSE 스트리밍
- [ ] 테스트

### Phase G-3: MVP 정의
- [ ] MVPDefinition 데이터 모델
- [ ] MVP 생성 LLM 함수
- [ ] 검증 계획 생성
- [ ] Kill Criteria 생성
- [ ] 테스트

### Phase G-4: 통합 및 UI
- [ ] 전체 파이프라인 오케스트레이션
- [ ] 프론트엔드 아이디어 입력 UI
- [ ] 결과 시각화
- [ ] E2E 테스트

---

## 미결정 사항

1. **입력 형식**: 텍스트만? 대화형? 피치덱 업로드?
2. **에이전트 구성**: 기존 재사용? 신규 추가?
3. **출력 형식**: 리포트? 대시보드? 프로젝트 자동 생성?
4. **DB 저장**: 아이디어 이력 저장? 버전 관리?
5. **권한**: 누구나 사용? 조직별 제한?

---

## 성공 지표

| 지표 | 목표 |
|------|------|
| Quick Check 응답 시간 | < 30초 |
| Deep Dive 완료 시간 | < 5분 |
| 사용자 만족도 | > 4.0/5.0 |
| Go → 실제 프로젝트 전환율 | > 30% |
| No-Go 정확도 (나중에 실패한 아이디어 비율) | > 70% |
