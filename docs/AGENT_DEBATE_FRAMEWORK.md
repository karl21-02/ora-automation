# Agent Debate Framework — Ora 페르소나 기반 서브에이전트 토론

## 개요

Claude Code Task tool 기반 멀티에이전트 토론 프레임워크.
ora-automation의 24개 YAML 페르소나(Toss 사일로 구조)에서 22개를 서브에이전트 프롬프트로 변환하여 병렬 실행한다.

- **원본(Source of Truth)**: `src/ora_rd_orchestrator/personas/*.yaml`
- **서브에이전트 프롬프트**: `docs/agents/*.md`
- **제외**: DebateSupervisor (토론 프로세스 역할), WebSearchAgent (쿼리 유틸리티)

---

## 아키텍처

```
질문/의사결정
     │
     ▼
┌─────────────────┐
│  패널 선정       │  ← 7개 프리셋 또는 수동 선택
│  (3~10명)       │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  병렬 Task 실행 (Claude Code Task tool)  │
│                                         │
│  Task(agent=ceo.md)  ──┐                │
│  Task(agent=pm.md)   ──┤  동시 실행      │
│  Task(agent=ops.md)  ──┘                │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  종합 (Synthesis)│  ← 합의/이견 테이블 + 최종 권고
└─────────────────┘
```

### 실행 흐름

1. **질문 정의**: 의사결정 사안, 맥락, 선택지를 구조화
2. **패널 선정**: 프리셋 패널 또는 에이전트 수동 지정
3. **병렬 실행**: 각 에이전트 MD를 프롬프트로 Task tool 호출
4. **응답 수집**: 에이전트별 판정(SUPPORT/CHALLENGE/NEUTRAL) + 분석
5. **종합**: 합의 사항, 이견 사항, 리스크, 최종 권고를 테이블로 정리

---

## 사일로 구조

```
                          ┌──────────┐
                          │   CEO    │ Tier 4 (strategy)
                          └────┬─────┘
              ┌────────────────┼────────────────┐
              │                │                │
        ┌─────┴─────┐   ┌─────┴─────┐   ┌──────┴──────┐
        │  Planner   │   │    PM     │   │    Ops      │   ← Tier 2 리드
        │ (research) │   │ (product) │   │ (platform)  │
        └─────┬──────┘   └─────┬─────┘   └──────┬──────┘
              │                │                 │
  ┌───────────┼──────┐  ┌─────┼──────┐  ┌───────┼──────────┐
  │Researcher │Data  │  │Product   │Market│ │Developer│DevOps│
  │DataScientist│    │  │Designer  │Analyst│ │Frontend │SRE  │
  │DataAnalyst│      │  │TechLead  │      │ │DevOps   │     │
  │SearchEval │      │  │          │      │ │Finance  │Growth│
  └───────────┘      │  └──────────┘      │ └─────────┘     │
                     │                    │                  │
              ┌──────┴──────┐                                │
              │   QALead    │ Tier 2 (quality_assurance)     │
              └──────┬──────┘                                │
                     │                                       │
        ┌────────────┼──────────┐                            │
        │QA  │Security│Linguist │                            │
        └────┘Specialist       │                             │
                               │                             │
                    ┌──────────┴─────────┐
                    │ ComplianceOfficer  │  governance
                    └────────────────────┘
```

### 5개 미션 사일로 + 거버넌스

| 사일로 | 리드 | 하위 에이전트 | 핵심 미션 |
|--------|------|---------------|----------|
| **strategy** | CEO (Tier 4) | Planner, GrowthHacker | 사업 전략, ROI, 수주 파이프라인 |
| **research_intelligence** | Planner (Tier 2) | Researcher, DataScientist, DataAnalyst, SearchEvaluator | 기술 탐색, 학술 근거, 데이터 분석 |
| **product_realization** | PM (Tier 2) | ProductDesigner, MarketAnalyst, TechLead | 제품 기획, UX, 시장 분석, 아키텍처 |
| **platform_infrastructure** | Ops (Tier 2) | Developer, DeveloperFrontend, DeveloperDevOps, DevOpsSRE, FinanceAnalyst, GrowthHacker | 개발, 배포, 인프라, 재무 |
| **quality_assurance** | QALead (Tier 2) | QA, SecuritySpecialist, Linguist | 품질 게이트, 보안, 언어 품질 |
| **governance** | — | CEO, ComplianceOfficer, DebateSupervisor* | 규제, 컴플라이언스, 토론 관리 |

> *DebateSupervisor는 토론 프로세스 역할이므로 서브에이전트 프롬프트에서 제외

---

## 프리셋 패널 (7개)

### 1. 전체 라운드테이블

대규모 전략 의사결정. 전 사일로 대표 참여.

| # | 에이전트 | 사일로 | 역할 |
|---|---------|--------|------|
| 1 | CEO | strategy | 최종 의사결정자 |
| 2 | Planner | research_intelligence | 연구 전략 리드 |
| 3 | PM | product_realization | 제품 리드 |
| 4 | Ops | platform_infrastructure | 인프라 리드 |
| 5 | QALead | quality_assurance | 품질 리드 |
| 6 | TechLead | product_realization | 아키텍처 |
| 7 | Researcher | research_intelligence | 학술 근거 |
| 8 | Developer | platform_infrastructure | 백엔드 구현 |
| 9 | SecuritySpecialist | quality_assurance | 보안 |
| 10 | ComplianceOfficer | governance | 규제/컴플라이언스 |

### 2. 전략 분석

R&D 방향, 시장 분석, 데이터 기반 의사결정.

| # | 에이전트 | 역할 |
|---|---------|------|
| 1 | CEO | 사업 전략 |
| 2 | Planner | 연구 전략 |
| 3 | Researcher | 학술 근거 |
| 4 | DataScientist | 통계 검증 |
| 5 | MarketAnalyst | 시장 분석 |
| 6 | DataAnalyst | 지표 분석 |

### 3. 제품 실현

기능 기획, UX, 기술 구현 결정.

| # | 에이전트 | 역할 |
|---|---------|------|
| 1 | PM | 제품 기획 |
| 2 | ProductDesigner | UX/UI |
| 3 | TechLead | 아키텍처 |
| 4 | Developer | 백엔드 |
| 5 | DeveloperFrontend | 프론트엔드 |
| 6 | MarketAnalyst | 시장 검증 |

### 4. 인프라/운영

배포, 인프라, 비용, 운영 안정성.

| # | 에이전트 | 역할 |
|---|---------|------|
| 1 | Ops | 운영 리드 |
| 2 | DeveloperDevOps | CI/CD |
| 3 | DevOpsSRE | SLO/신뢰성 |
| 4 | Developer | 백엔드 |
| 5 | FinanceAnalyst | 비용 분석 |
| 6 | SecuritySpecialist | 보안 |

### 5. 품질 게이트

릴리즈 판정, 보안 검증, 컴플라이언스.

| # | 에이전트 | 역할 |
|---|---------|------|
| 1 | QALead | 품질 게이트 |
| 2 | QA | 테스트 |
| 3 | SecuritySpecialist | 보안 |
| 4 | Linguist | 언어 품질 |
| 5 | ComplianceOfficer | 규제 |

### 6. 성장/GTM

성장 실험, 마케팅, 퍼널 최적화.

| # | 에이전트 | 역할 |
|---|---------|------|
| 1 | GrowthHacker | 성장 전략 |
| 2 | MarketAnalyst | 시장 분석 |
| 3 | PM | 제품 연계 |
| 4 | DataAnalyst | 지표 분석 |
| 5 | FinanceAnalyst | ROI |

### 7. 기술 부채

아키텍처 리팩토링, 코드 품질, 인프라 개선.

| # | 에이전트 | 역할 |
|---|---------|------|
| 1 | TechLead | 아키텍처 |
| 2 | Developer | 백엔드 |
| 3 | DeveloperFrontend | 프론트엔드 |
| 4 | DeveloperDevOps | CI/CD |
| 5 | DevOpsSRE | SRE |

---

## 에이전트 카탈로그 (22개)

| # | agent_id | 파일 | 사일로 | Tier | 상위 | 핵심 관점 |
|---|----------|------|--------|------|------|----------|
| 1 | CEO | `ceo.md` | strategy | 4 | — | 수주 적중률, ROI |
| 2 | ComplianceOfficer | `compliance-officer.md` | governance | 3 | — | 규제, 개인정보보호 |
| 3 | Planner | `planner.md` | research_intelligence | 2 | — | 기술 차별성, 과제화 |
| 4 | Researcher | `researcher.md` | research_intelligence | 1 | Planner | 논문 근거, 재현성 |
| 5 | DataScientist | `data-scientist.md` | research_intelligence | 1 | Planner | 통계 타당성 |
| 6 | DataAnalyst | `data-analyst.md` | research_intelligence | 1 | Planner | 핵심 지표, A/B 테스트 |
| 7 | SearchEvaluator | `search-evaluator.md` | research_intelligence | 1 | Planner | 검색 품질, 저널 랭킹 |
| 8 | PM | `pm.md` | product_realization | 2 | — | KPI, 스프린트 관리 |
| 9 | ProductDesigner | `product-designer.md` | product_realization | 1 | PM | UX, 디자인 시스템 |
| 10 | MarketAnalyst | `market-analyst.md` | product_realization | 1 | PM | TAM/SAM/SOM, 경쟁사 |
| 11 | TechLead | `tech-lead.md` | product_realization | 1 | PM | 아키텍처, 기술 부채 |
| 12 | Ops | `ops.md` | platform_infrastructure | 2 | — | 운영 안정성, SLO |
| 13 | Developer | `developer-backend.md` | platform_infrastructure | 1 | Ops | 백엔드 PoC, API |
| 14 | DeveloperFrontend | `developer-frontend.md` | platform_infrastructure | 1 | Ops | UI/UX, 접근성 |
| 15 | DeveloperDevOps | `developer-devops.md` | platform_infrastructure | 1 | Ops | CI/CD, 자동화 |
| 16 | DevOpsSRE | `devops-sre.md` | platform_infrastructure | 1 | Ops | SLO, 가용성 |
| 17 | FinanceAnalyst | `finance-analyst.md` | platform_infrastructure | 1 | Ops | ROI, 투자 회수 |
| 18 | GrowthHacker | `growth-hacker.md` | platform_infrastructure | 1 | Ops | AARRR, CAC/LTV |
| 19 | QALead | `qa-lead.md` | quality_assurance | 2 | — | 품질 게이트 |
| 20 | QA | `qa.md` | quality_assurance | 1 | QALead | 테스트, 회귀 버그 |
| 21 | SecuritySpecialist | `security-specialist.md` | quality_assurance | 1 | QALead | OWASP, 보안 |
| 22 | Linguist | `linguist.md` | quality_assurance | 1 | QALead | NLP, 프롬프트 품질 |

---

## 사용법

### 입력 형식

```markdown
## 의사결정 사안
{{DECISION}}

## 맥락
{{CONTEXT}}

## 선택지
{{OPTIONS}}
```

### 트리거 예시

```
사용자: "마이크로서비스 전환 vs 모놀리스 유지, 전체 라운드테이블로 토론해줘"

→ 패널: 전체 라운드테이블 (10명)
→ 각 에이전트 MD를 프롬프트로 Task tool 병렬 호출
→ 응답 종합
```

### 에이전트 출력 형식 (공통)

모든 에이전트는 아래 형식으로 응답한다:

```markdown
## 리서치 결과

| 출처 | 핵심 내용 | URL |
|------|----------|-----|
| ... | ... | ... |

## 판정

- **판정**: SUPPORT / CHALLENGE / NEUTRAL
- **확신도**: 1-10
- **핵심 근거**: (1문장)

## 상세 분석

(3-5문장)

## 리스크/우려 사항

- ...

## 권고 사항

- ...
```

---

## 종합 프로토콜

모든 에이전트 응답을 수집한 후, 아래 테이블로 종합한다.

### 종합 테이블

```markdown
## 에이전트별 판정 요약

| 에이전트 | 판정 | 확신도 | 핵심 근거 |
|---------|------|--------|----------|
| CEO | SUPPORT | 8 | ... |
| PM | CHALLENGE | 7 | ... |
| ... | ... | ... | ... |

## 합의 사항
- (과반수 이상 동의한 포인트)

## 이견 사항
| 쟁점 | SUPPORT 측 | CHALLENGE 측 | 핵심 논거 차이 |
|------|-----------|-------------|---------------|
| ... | ... | ... | ... |

## 주요 리스크
- (2명 이상 언급한 리스크)

## 최종 권고
(종합 판단 + 조건부 권고)
```

---

## 에이전트 추가/수정 가이드

### 새 에이전트 MD 만들기

1. `src/ora_rd_orchestrator/personas/`에 YAML 페르소나를 먼저 추가
2. 아래 템플릿으로 `docs/agents/{kebab-case}.md` 생성

```markdown
# {display_name} — {display_name_ko}

> 사일로: {team} | 티어: {tier} | 상위: {domain}
> YAML: src/ora_rd_orchestrator/personas/{file}.yaml

## 정체성
{personality.archetype}로서, {personality.motivation}.
소통 방식: {personality.communication_style}

## 전문 영역
- {decision_focus 항목들}

## 평가 기준
- {behavioral_directives 항목들}

## 제약 조건
- {constraints 항목들}

## 평가 가중치

| 항목 | 비중 |
|------|------|
| impact | {weights.impact} |
| novelty | {weights.novelty} |
| feasibility | {weights.feasibility} |
| research_signal | {weights.research_signal} |
| risk | {weights.risk} |

## 교차 신뢰도

| 에이전트 | 신뢰도 |
|---------|--------|
| {agent} | {value} |

## 프롬프트 템플릿

당신은 {display_name_ko}입니다.

{personality.archetype}로서, {personality.motivation}.
소통 방식: {personality.communication_style}

### 행동 지침
{behavioral_directives}

### 제약 조건
{constraints}

### 의사결정 사안
{{DECISION}}

### 맥락
{{CONTEXT}}

### 선택지
{{OPTIONS}}

### 지시사항
- WebSearch tool을 활용하여 최신 자료를 검색하세요.
- 검색 결과를 기반으로 아래 형식으로 응답하세요.

### 출력 형식

## 리서치 결과
| 출처 | 핵심 내용 | URL |
|------|----------|-----|
| ... | ... | ... |

## 판정
- **판정**: SUPPORT / CHALLENGE / NEUTRAL
- **확신도**: 1-10
- **핵심 근거**: (1문장)

## 상세 분석
(3-5문장)

## 리스크/우려 사항
- ...

## 권고 사항
- ...
```

### 기존 에이전트 수정

1. YAML 원본을 먼저 수정
2. 해당 MD 파일의 관련 섹션을 YAML과 동기화
3. 프리셋 패널 구성이 영향받는지 이 문서에서 확인

### 파일 네이밍 규칙

- YAML: `snake_case.yaml` (예: `developer_backend.yaml`)
- MD: `kebab-case.md` (예: `developer-backend.md`)
- agent_id → 파일명 매핑은 에이전트 카탈로그 참조
