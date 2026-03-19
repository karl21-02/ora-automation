# AI Company Designer — 에이전트 조직 커스터마이징 시스템

> 사용자가 **AI 에이전트로 구성된 회사**를 직접 설계하고, 채팅에서 정의한 작업을 해당 회사에 할당하는 시스템.
>
> **핵심 개념**: 토스(Toss) 조직 구조를 본뜬 **사일로 + 챕터** 이중 구조.
> 사용자는 여러 AI 회사를 만들 수 있고, 각 대화(작업)는 특정 회사에 소속된다.

---

## 목차

1. [현황 분석](#1-현황-분석)
2. [설계 결정 사항](#2-설계-결정-사항)
3. [아키텍처](#3-아키텍처)
4. [Phase 1: DB 모델 + CRUD API](#4-phase-1-db-모델--crud-api)
5. [Phase 2: 프리셋 시딩](#5-phase-2-프리셋-시딩)
6. [Phase 3: 파이프라인 통합](#6-phase-3-파이프라인-통합)
7. [Phase 4: 프론트엔드 — 비주얼 에디터](#7-phase-4-프론트엔드--비주얼-에디터)
8. [Phase 5: 대화-회사 연결 + 사이드바](#8-phase-5-대화-회사-연결--사이드바)
9. [Phase 6: Gemini 기반 조직 추천 (UPCE 통합)](#9-phase-6-gemini-기반-조직-추천-upce-통합)
10. [Phase 7: 협업 모드](#10-phase-7-협업-모드)
11. [Phase 8: 테스트](#11-phase-8-테스트)
12. [검증 체크리스트](#12-검증-체크리스트)
13. [구현 순서 요약](#13-구현-순서-요약)

---

## 1. 현황 분석

### 하드코딩된 에이전트 설정

**`src/ora_rd_orchestrator/config.py`**:

```python
# Line 207 — scoring 참여 에이전트 (flat mode)
FLAT_MODE_AGENTS = {"CEO", "Planner", "Developer", "Researcher", "PM", "Ops", "QA", "DataAnalyst", "TechLead", "GrowthHacker"}

# Line 210-222 — consensus 가중치
AGENT_FINAL_WEIGHTS = {
    "CEO": 0.20, "Planner": 0.14, "Developer": 0.12, "Researcher": 0.12,
    "PM": 0.10, "Ops": 0.08, "QA": 0.04, "DataAnalyst": 0.06,
    "TechLead": 0.06, "GrowthHacker": 0.05, "ComplianceOfficer": 0.03,
}
```

**사용처** (런타임에 오버라이드해야 하는 곳):

| 파일 | 라인 | 용도 |
|------|------|------|
| `pipeline.py` | 712 | `score_all_agents(..., agent_filter=FLAT_MODE_AGENTS)` |
| `pipeline.py` | 852 | `build_agent_rankings(scores, agent_filter=FLAT_MODE_AGENTS)` |
| `report_builder.py` | 660, 700 | `weights = agent_weights or AGENT_FINAL_WEIGHTS` |
| `report_builder.py` | 678, 733 | `agents = agent_filter or set(AGENT_FINAL_WEIGHTS.keys())` |
| `report_builder.py` | 934 | `agent_order = [name for name in AGENT_FINAL_WEIGHTS]` |

### 기존 파이프라인 (교체 대상)

`pipeline.py`의 기존 Flat Mode → **LangGraph 3단계 수렴 파이프라인으로 전면 교체**.
`engine.py` (Hierarchical Mode, 레거시 모놀리스) → **삭제 대상**.

### YAML 페르소나 (24개)

`src/ora_rd_orchestrator/personas/*.yaml` — 24개 파일.

**YAML 구조** (`ceo.yaml` 기준):

```yaml
agent_id: "CEO"
display_name: "CEO"
display_name_ko: "CEO (수주 적중률에 집착하는 사업 총괄)"
role: "ceo"
tier: 4
domain: null
team: "strategy"
personality:
  archetype: "..."
  motivation: "..."
  communication_style: "..."
behavioral_directives: [...]
constraints: [...]
decision_focus: [...]
weights: {impact: 0.46, novelty: 0.23, feasibility: 0.14, ...}
trust_map: {CEO: 1.0, Planner: 0.78, ...}
system_prompt_template: |
  당신은 {display_name_ko}입니다. ...
```

### PersonaRegistry 클래스 (`personas.py`)

```python
class PersonaRegistry:
    def __init__(self, persona_dir: Path | None = None)
    def load_all(self) -> dict[str, AgentPersona]     # YAML → 메모리
    def get_persona(agent_id) -> AgentPersona | None
    def get_team(team_name) -> list[AgentPersona]
    def get_tier(tier) -> list[AgentPersona]
    def to_agent_definitions() -> dict       # 삭제 대상 (LangGraph 전환 후)
    def to_agent_weights() -> dict           # 삭제 대상
    def to_trust_map() -> dict               # 삭제 대상
```

### pipeline.py 핵심 흐름 (Line 329-950)

```
1. Load personas (L339)  → PersonaRegistry(dir).load_all()
2. Topic discovery (L365) → discover_topics()
3. Workspace analysis (L437) → analyze_workspace()
4. Scoring (L706)        → score_all_agents(..., agent_filter=FLAT_MODE_AGENTS)
5. Deliberation (L734)   → llm_deliberation_round() × N rounds
6. Agent rankings (L851) → build_agent_rankings(..., agent_filter=FLAT_MODE_AGENTS)
7. Consensus (L912)      → apply_hybrid_consensus()
8. Report (L1066+)       → build_report() — AGENT_FINAL_WEIGHTS가 report_builder 내부에서 사용
```

### 프론트엔드 패턴

- **스타일**: 모든 컴포넌트 inline `React.CSSProperties` (외부 CSS 없음)
- **상태**: `useState` + `useCallback` (React 19)
- **API**: `frontend/src/lib/api.ts` — `request<T>()` 헬퍼, BASE = `/api/v1`
- **타입**: `frontend/src/types.ts` — 모든 인터페이스 정의
- **탭**: `Sidebar.tsx` L60 — 현재 `'chats' | 'reports'` 2개 탭
- **실행 확인**: `ChatWindow.tsx` L177-209 — plan 확인 후 `createRun()` 호출

---

## 2. 설계 결정 사항

토론을 통해 확정된 핵심 설계 결정.

### 2.1 조직 구조: 토스(Toss) 스타일

토스의 **사일로(Silo) + 챕터(Chapter)** 이중 구조를 본뜬 AI 회사:

```
Organization (= AI 회사)
│
├── 🌟 C-Level (조직 직속, 사일로/챕터 밖)
│   ├── CEO — 전체 방향 조언자, 가중치 높음
│   └── ComplianceOfficer — 거버넌스 게이트
│
├── Chapters (큰 그림 — 전문가 그룹, 에이전트의 정체성)
│   ├── Engineering 📐 : shared_directives, chapter_prompt
│   ├── Security 🔒    : shared_directives, chapter_prompt
│   ├── Research 🔬    : shared_directives, chapter_prompt
│   ├── Product 📦     : shared_directives, chapter_prompt
│   └── Data 📊       : shared_directives, chapter_prompt
│
├── Silos (임무 팀 — 에이전트가 배치되어 일하는 곳)
│   ├── 전략기획 사일로
│   ├── 프로덕트 사일로
│   ├── 플랫폼 사일로
│   ├── 품질보증 사일로
│   └── 리서치 사일로
│
├── Agents (챕터 1개 + 사일로 1개에 소속, C-Level은 둘 다 없음)
│   ├── Developer     — chapter: Engineering → silo: 플랫폼
│   ├── SecuritySpec  — chapter: Security   → silo: 품질보증
│   ├── Researcher    — chapter: Research   → silo: 리서치
│   └── PM            — chapter: Product    → silo: 프로덕트
│
└── Pipeline Params (debate_rounds, top_k, profile 등)
```

**토스 원칙 적용:**

| 토스 원칙 | 우리 시스템 |
|----------|------------|
| 사일로 = 미니 스타트업, 제품 단위 | 사일로 = 미션/분석 대상 팀 |
| 챕터 = 같은 직군 지식 공유 | 챕터 = 같은 전문 분야 에이전트, shared_directives로 지식 공유 |
| 사일로 내부 수평, 상하관계 없음 | 동일 — 사일로 내 에이전트는 수평 |
| C-Level은 사일로 밖 조언자 | 동일 — 조직 직속, 사일로/챕터 밖 |
| DRI(직접 책임자) 제도 | 각 에이전트가 자기 전문 영역의 최종 결정권 |

### 2.2 챕터의 역할: 공유 프롬프트 레이어

챕터 = **"같은 전문가끼리 지식 공유"** (토스 챕터의 원래 의도를 AI 시스템으로 번역)

```python
# 챕터가 가진 공유 지식
class OrganizationChapter:
    shared_directives: list      # 공통 행동 지침 → 소속 에이전트 전원 적용
    shared_constraints: list     # 공통 제약 조건
    shared_decision_focus: list  # 공통 평가 기준
    chapter_prompt: str          # 챕터 레벨 프롬프트 → system_prompt에 주입
```

**런타임 동작:**

```
에이전트의 최종 system_prompt =
    chapter_prompt (Engineering 챕터의 공유 관점)
  + agent system_prompt (Developer 개인의 성격/지침)

최종 directives = chapter shared_directives + agent directives
최종 constraints = chapter shared_constraints + agent constraints
최종 decision_focus = chapter shared_decision_focus + agent decision_focus
```

**예시:**

```yaml
챕터 "Engineering":
  chapter_prompt: |
    당신은 Engineering 챕터 소속입니다.
    같은 챕터의 동료들과 기술적 관점을 공유합니다.
    기술 구현 가능성과 운영 안정성을 최우선으로 평가하세요.
  shared_directives:
    - "구현 복잡도와 유지보수 비용을 항상 고려하라"
    - "기술 부채 관점에서 평가하라"
  shared_constraints:
    - "검증되지 않은 기술 스택 추천 시 반드시 리스크 명시"
  shared_decision_focus:
    - "feasibility"
    - "risk_penalty"

→ Engineering 챕터의 Developer, DevOpsSRE, TechLead 모두에게 자동 적용
→ 챕터 설정 하나 바꾸면 소속 에이전트 전원에게 반영
```

### 2.3 에이전트 생성 흐름

```
1. 챕터에서 에이전트 생성 (챕터 = 정체성)
   → "Engineering 챕터에 새 Developer 추가"

2. 사일로에 배치 (사일로 = 임무)
   → Agent Palette에서 드래그 → 사일로에 드롭

3. C-Level은 조직 직속
   → 사일로/챕터 없이 조직에 바로 추가
```

### 2.4 기존 tier/domain/team → 제거

| 기존 | 변경 | 이유 |
|------|------|------|
| `tier: int` (1-4) | **제거** | C-Level은 조직 직속, 나머지는 사일로 내 수평 |
| `domain: str` (상위 리드) | **제거** | 상하관계 없음 (토스 원칙) |
| `team: str` (사일로 성격) | **`silo_id: FK`** | 사일로 테이블로 대체 |
| (없음) | **`chapter_id: FK`** | 챕터 테이블 참조 |
| `Organization.teams` | **제거** | `OrganizationSilo` 테이블로 대체 |
| `Organization.flat_mode_agents` | **제거** | 자동 파생 (enabled=true인 에이전트) |
| `Organization.agent_final_weights` | **제거** | 자동 파생 (에이전트 개별 weight_score) |

### 2.5 컨셉: "AI 회사 설계"

| 항목 | 결정 |
|------|------|
| 핵심 메타포 | 사용자가 **AI 에이전트로 구성된 회사**를 만들고, 작업을 할당 |
| 조직 없으면 | 프리셋(Default Toss Silo) 자동 적용 |
| 여러 회사 | 사용자는 여러 회사를 생성 가능 |

### 2.6 커스터마이징 심도: Level B

| Level | 설명 | 시기 |
|-------|------|------|
| **A** | 에이전트 속성만 (이름, 성격, 가중치, 신뢰도) | - |
| **B (MVP)** | A + 파이프라인 파라미터 + 사일로/챕터 구성 | **MVP** |
| **C** | B + Hierarchical 파이프라인 tier 실행 로직 | V2 |

### 2.7 대화-회사 관계

```
┌──────────────┐       ┌──────────────────┐
│ Organization │ 1 ─ N │ ChatConversation │
│              │       │   org_id (FK)    │
└──────────────┘       └──────────────────┘
```

- `ChatConversation.org_id` — 대화는 회사에 소속
- 회사 미지정 대화 → `org_id = NULL` → 프리셋 자동 적용
- 대화 중 회사 변경 가능 (Switch 협업)

### 2.8 사이드바 회사별 그룹핑

```
┌────────────────────────────┐
│ [Chats] [Reports] [Orgs]  │
├────────────────────────────┤
│ 🏢 Default (Toss Silo)    │
│   ├ 보안 트렌드 분석       │
│   ├ AI 서버 성능 리뷰     │
│   └ B2B 영업 전략          │
│                            │
│ 🏢 My Security Corp       │
│   ├ 취약점 분석            │
│   └ 모의 해킹 결과 검토   │
│                            │
│ 📎 미분류                  │
│   └ 일반 대화              │
└────────────────────────────┘
```

### 2.9 Gemini 기반 조직 추천

- UPCE Dialog Engine에 **ORG_RECOMMEND** 스테이지 추가
- Gemini가 작업 내용 + 보유 조직 목록 기반으로 추천
- 조직 1개만 있으면 → 자동 적용, 스킵

### 2.10 협업 모드 (3가지, 각각 별도 기능)

| 모드 | 설명 | 시기 |
|------|------|------|
| **Switch** | 대화 중 회사 변경 | **MVP** |
| **Guest** | 다른 회사에서 에이전트 빌려오기 | **V2** |
| **Joint** | 두 회사를 합쳐서 분석 | **V3** |

### 2.11 UI 모드: 기본 / 고급

| | 일반 유저 (기본 모드) | 파워 유저 (고급 모드) |
|---|---|---|
| 회사 생성 | 프리셋 복제 1클릭 | 빈 캔버스에서 설계 |
| 사일로 | 기본 제공, 삭제/추가 | 자유 생성 |
| 에이전트 | ON/OFF 토글 | 드래그 배치 + 상세 편집 |
| 챕터 | 안 보임 (자동) | 고급 설정에서 편집 |
| 파이프라인 | 기본값 | 직접 튜닝 |

### 2.12 에이전트 생성 UX

**필수 입력 (최소 생성):**

| 필드 | 설명 |
|------|------|
| `agent_id` | 고유 식별자 (영문+숫자+_, 자동 생성 가능: "Developer_2") |
| `display_name` | 영문 표시 이름 |
| `display_name_ko` | 한국어 이름+설명 |
| `chapter_id` | 소속 챕터 (C-Level 아닌 이상 필수) |
| `role` | 드롭다운 선택 |

**자동 기본값 (생성 후 편집 가능):**
- `weights` — 챕터 기반 합리적 기본값 (Engineering → feasibility 높게)
- `trust_map` — 모든 에이전트에 대해 0.5 균등
- `system_prompt_template` — 챕터 + role 기반 자동 생성 템플릿
- `behavioral_directives`, `constraints`, `decision_focus` — 빈 리스트 (챕터 공유만 적용)
- `weight_score` — 1.0 (기본 영향력)
- `personality` — 빈 dict

**생성 방법:**

| 방법 | 진입점 | UX |
|------|--------|-----|
| 빈 템플릿 | Agent Palette "[+ 새 에이전트]" | 챕터 선택 → 필수 입력 → 기본값 생성 |
| 복제 | 기존 에이전트 카드 "복제" 버튼 | 모든 필드 복사 → agent_id만 변경 ("Developer_2") |
| C-Level | C-Level 영역 "[+ C-Level 추가]" | silo/chapter 없이, is_clevel=True 자동 |

**에이전트 수 상한: 없음.** 1000개 이상도 가능 (3단계 파이프라인이 확장성 보장).

### 2.13 파이프라인: LangGraph 3단계 수렴 기반 자율 토론

에이전트 수에 관계없이 확장 가능한 파이프라인. **LangGraph StateGraph**로 구현.
토스 조직 구조를 평가 구조에 직접 활용. TypedDict 기반 상태 관리.

**모든 에이전트가 모든 토픽을 평가하는 게 아니라, 조직 구조를 따라 계층적으로 수렴.**

```
Level 1: 챕터 내부 토론 (병렬)
  같은 챕터 에이전트끼리 토론 → 챕터 관점 점수 수렴
  C-Level은 개별 평가 (챕터 밖)
  수렴 조건: 챕터 내 점수 분산 < threshold
  상한: level1_max_rounds (기본 5)

Level 2: 사일로 내부 토론 (병렬)
  같은 사일로의 챕터 대표끼리 토론 → 사일로 의견 수렴
  수렴 조건: 사일로 내 의견 변화 < threshold
  상한: level2_max_rounds (기본 3)

Level 3: C-Level + 사일로 대표 전체 deliberation
  수렴 조건: 전체 랭킹 안정화
  상한: level3_max_rounds (기본 3)
```

**수렴 판정:**

```python
def is_converged(prev_scores: dict, curr_scores: dict, threshold: float = 0.15) -> bool:
    """이전 라운드 대비 점수 변화가 작으면 수렴."""
    deltas = [abs(curr_scores[k] - prev_scores[k]) for k in curr_scores]
    return max(deltas) < threshold
```

- **수렴** → 토론 종료, 다음 Level로
- **미수렴 + 상한 미달** → 라운드 추가
- **상한 도달** → 강제 종료, 현재 점수로 진행

**흐름 예시 (1000 에이전트, 30 챕터, 30 사일로):**

```
Level 1: 챕터 내부 (30 챕터 × 병렬)
  Engineering 챕터 (200명):
    라운드 1 → 분산 0.8
    라운드 2 → 분산 0.3
    라운드 3 → 분산 0.1 → ✅ 수렴 (3R)
  Security 챕터 (50명):
    라운드 1 → 분산 0.2
    라운드 2 → 분산 0.08 → ✅ 수렴 (2R)
  (챕터별 수렴 시점 다름 — 빨리 끝난 챕터는 대기)

Level 2: 사일로 내부 (30 사일로 × 병렬)
  플랫폼 사일로: Engineering 대표 + Ops 대표 토론
    라운드 1-2 → ✅ 수렴

Level 3: 전체 deliberation
  CEO + ComplianceOfficer + 30 사일로 대표
    라운드 1-3 → ✅ 수렴 → 최종 consensus
```

**LLM 호출 수 비교 (6토픽 기준):**

| 에이전트 | 챕터 | 사일로 | L1 (평균 3R) | L2 (평균 2R) | L3 (평균 3R) | 총 호출 |
|---------|------|-------|-------------|-------------|-------------|--------|
| 24 | 8 | 5 | 24 | 10 | 21 | ~330 |
| 100 | 15 | 10 | 45 | 20 | 36 | ~606 |
| 500 | 25 | 20 | 75 | 40 | 66 | ~1,086 |
| 1000 | 30 | 30 | 90 | 60 | 96 | ~1,476 |

**토스 원칙과의 대응:**

| 토스 원칙 | 파이프라인 활용 |
|----------|---------------|
| 챕터 = 같은 전문가 지식 공유 | Level 1: 같은 관점 → 배치 평가 가능 |
| 사일로 = 미션 팀 자율 의사결정 | Level 2: 사일로 내부 수렴 → 대표 발언 |
| C-Level = 최종 방향 조언 | Level 3: deliberation은 소수 정예 |
| 사일로 안에서 정리 → 경영진 보고 | Level 1→2→3 자연스러운 상향 흐름 |

### 2.14 Org Config 전달: 하이브리드 (env / file)

```python
# service.py — create_run() 내부
org_json = json.dumps(org_config)
if len(org_json) > 80_000:  # ~80KB safety margin
    path = f"/tmp/ora_org_{run_id}.json"
    Path(path).write_text(org_json)
    env["ORA_ORG_CONFIG_PATH"] = path
else:
    env["ORA_ORG_CONFIG_JSON"] = org_json
```

```python
# pipeline.py — generate_report() 내부
config_raw = os.getenv("ORA_ORG_CONFIG_JSON", "")
if not config_raw:
    config_path = os.getenv("ORA_ORG_CONFIG_PATH", "")
    if config_path:
        config_raw = Path(config_path).read_text()
```

**보안 — Pydantic validator:**

| 필드 | 상한 |
|------|------|
| `agent_id` | 영문+숫자+_, 3-64자 |
| `display_name` | 128자 |
| `system_prompt_template` | 4000자 |
| `chapter_prompt` | 2000자 |
| `behavioral_directives` 각 항목 | 500자 |

---

## 3. 아키텍처

```
Frontend (React)                        Backend (FastAPI)
┌───────────────────────┐              ┌──────────────────────────┐
│ Sidebar               │              │ org_router.py            │
│  - 회사별 대화 그룹   │ ──GET────>  │   /api/v1/orgs           │
│                       │              │   /api/v1/orgs/:id       │
│ OrgDesigner           │              │   /api/v1/orgs/:id/silos │
│  - 사일로 + 챕터 에디터│ ──CRUD───> │   /api/v1/orgs/:id/      │
│  - 드래그 앤 드롭     │              │     chapters, agents     │
│                       │              │                          │
│ ChatWindow            │              │ chat_router.py           │
│  - 조직 추천 UI       │              │   Conversation.org_id    │
│  - Switch 선택        │              │   ORG_RECOMMEND stage    │
└───────────────────────┘              └──────────┬───────────────┘
                                                  │ DB
                                                  ▼
                                        ┌──────────────────┐
                                        │ organizations    │
                                        │ organization_    │
                                        │   silos          │
                                        │ organization_    │
                                        │   chapters       │
                                        │ organization_    │
                                        │   agents         │
                                        │ chat_            │
                                        │   conversations  │
                                        │   .org_id (FK)   │
                                        └────────┬─────────┘
                                                 │
                                        create_run(org_id)
                                                 │
                                                 ▼
                                        run.env["ORA_ORG_CONFIG_JSON"]
                                                 │
                                                 ▼
                                        Worker → subprocess
                                                 │
                                                 ▼
                                        pipeline.py: generate_report()
                                        PersonaRegistry.from_org_config()
                                        chapter prompts merged into agents
```

**핵심 설계 결정:**

- Organization → Silo → Agent, Organization → Chapter → Agent (이중 소속)
- C-Level 에이전트는 silo_id=NULL, chapter_id=NULL (조직 직속)
- 챕터의 shared_directives/chapter_prompt가 에이전트 프롬프트에 런타임 주입
- `flat_mode_agents`, `agent_final_weights`는 DB에 저장하지 않고 자동 파생
- `ORA_ORG_CONFIG_JSON` 환경변수로 worker subprocess에 전달
- `make run` (CLI) 실행 시에도 프리셋 org config를 자동 생성하여 LangGraph 파이프라인으로 실행

---

## 4. Phase 1: DB 모델 + CRUD API

### 커밋: `feat(org): add organization/silo/chapter/agent models and CRUD API`

### 4.1 수정 파일

| 파일 | 변경 |
|------|------|
| `src/ora_automation_api/models.py` | `Organization`, `OrganizationSilo`, `OrganizationChapter`, `OrganizationAgent` 모델 추가, `ChatConversation.org_id` 추가 |
| `src/ora_automation_api/schemas.py` | Org/Silo/Chapter/Agent Pydantic 스키마 추가 |
| `src/ora_automation_api/org_router.py` | **신규** — 조직/사일로/챕터/에이전트 CRUD 라우터 |
| `src/ora_automation_api/main.py` | 라우터 등록 + DDL에 새 테이블 포함 |

### 4.2 DB 모델

```python
class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_preset: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pipeline_params: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # {
    #   "level1_max_rounds": 5,       # 챕터 내부 토론 상한
    #   "level2_max_rounds": 3,       # 사일로 내부 토론 상한
    #   "level3_max_rounds": 3,       # 전체 deliberation 상한
    #   "convergence_threshold": 0.15, # 수렴 판정 임계값
    #   "top_k": 6,                   # 상위 N개 전략
    #   "orchestration_profile": "standard",
    # }
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class OrganizationSilo(Base):
    """사일로 — 미션/임무 팀. 에이전트가 배치되어 일하는 곳."""
    __tablename__ = "organization_silos"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_org_silo_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#3b82f6")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class OrganizationChapter(Base):
    """챕터 — 전문가 그룹. 에이전트의 정체성 + 공유 지식 레이어."""
    __tablename__ = "organization_chapters"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_org_chapter_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 챕터 공유 지식 — 소속 에이전트 전원에게 적용
    shared_directives: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    shared_constraints: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    shared_decision_focus: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    chapter_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#8b5cf6")
    icon: Mapped[str] = mapped_column(String(4), nullable=False, default="📁")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class OrganizationAgent(Base):
    """에이전트 — 챕터(정체성) + 사일로(임무)에 소속. C-Level은 둘 다 NULL."""
    __tablename__ = "organization_agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    silo_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organization_silos.id", ondelete="SET NULL"),
        nullable=True,      # NULL = C-Level (조직 직속)
    )
    chapter_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organization_chapters.id", ondelete="SET NULL"),
        nullable=True,      # NULL = C-Level (챕터 밖)
    )
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name_ko: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_clevel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    personality: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    behavioral_directives: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    constraints: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    decision_focus: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    weights: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    trust_map: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    system_prompt_template: Mapped[str] = mapped_column(Text, nullable=False, default="")
    weight_score: Mapped[float] = mapped_column(nullable=False, default=1.0)
    # consensus 영향력 (정규화하여 agent_final_weights 자동 파생)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
```

**ChatConversation 변경:**

```python
class ChatConversation(Base):
    # ... 기존 필드 유지 ...
    org_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
```

### 4.3 자동 파생 로직

```python
def derive_flat_mode_agents(agents: list[OrganizationAgent]) -> set[str]:
    """enabled=true인 에이전트의 agent_id 집합."""
    return {a.agent_id for a in agents if a.enabled}


def derive_agent_final_weights(agents: list[OrganizationAgent]) -> dict[str, float]:
    """에이전트 weight_score를 정규화하여 consensus 가중치 생성."""
    enabled = [a for a in agents if a.enabled]
    total = sum(a.weight_score for a in enabled) or 1.0
    return {a.agent_id: round(a.weight_score / total, 4) for a in enabled}
```

### 4.4 API 엔드포인트

```
# 조직
GET    /api/v1/orgs                           조직 목록
POST   /api/v1/orgs                           조직 생성
GET    /api/v1/orgs/{id}                      조직 상세 (사일로+챕터+에이전트 포함)
PATCH  /api/v1/orgs/{id}                      조직 수정
DELETE /api/v1/orgs/{id}                      조직 삭제 (프리셋 불가)
POST   /api/v1/orgs/{id}/clone                조직 복제 (deep copy)

# 사일로
POST   /api/v1/orgs/{id}/silos                사일로 추가
PATCH  /api/v1/orgs/{id}/silos/{silo_id}      사일로 수정
DELETE /api/v1/orgs/{id}/silos/{silo_id}      사일로 삭제

# 챕터
POST   /api/v1/orgs/{id}/chapters             챕터 추가
PATCH  /api/v1/orgs/{id}/chapters/{ch_id}     챕터 수정 (shared_directives 등)
DELETE /api/v1/orgs/{id}/chapters/{ch_id}      챕터 삭제

# 에이전트
POST   /api/v1/orgs/{id}/agents               에이전트 추가
PATCH  /api/v1/orgs/{id}/agents/{agent_id}    에이전트 수정
DELETE /api/v1/orgs/{id}/agents/{agent_id}    에이전트 삭제
```

---

## 5. Phase 2: 프리셋 시딩

### 커밋: `feat(org): seed preset organization from YAML personas on startup`

### 5.1 프리셋 구조

기존 24개 YAML 에이전트를 토스 스타일로 재배치:

**C-Level (조직 직속):**

| 에이전트 | silo_id | chapter_id | is_clevel |
|---------|---------|------------|-----------|
| CEO | NULL | NULL | true |
| ComplianceOfficer | NULL | NULL | true |

**사일로 + 챕터 배치:**

| 사일로 | 에이전트 | 챕터 |
|--------|---------|------|
| 전략기획 | Planner | Strategy 📋 |
| 전략기획 | DataScientist | Data 📊 |
| 전략기획 | DataAnalyst | Data 📊 |
| 프로덕트 | PM | Product 📦 |
| 프로덕트 | ProductDesigner | Product 📦 |
| 프로덕트 | MarketAnalyst | Product 📦 |
| 프로덕트 | TechLead | Engineering 📐 |
| 플랫폼 | Ops | Ops ⚙️ |
| 플랫폼 | Developer_BE | Engineering 📐 |
| 플랫폼 | Developer_FE | Engineering 📐 |
| 플랫폼 | Developer_DevOps | Engineering 📐 |
| 플랫폼 | DevOpsSRE | Engineering 📐 |
| 플랫폼 | GrowthHacker | Ops ⚙️ |
| 플랫폼 | FinanceAnalyst | Ops ⚙️ |
| 품질보증 | QALead | QA 🧪 |
| 품질보증 | SecuritySpecialist | Security 🔒 |
| 품질보증 | Linguist | QA 🧪 |
| 품질보증 | QA | QA 🧪 |
| 리서치 | Researcher | Research 🔬 |

**프리셋 챕터:**

| 챕터 | icon | color | shared_directives (요약) |
|------|------|-------|------------------------|
| Engineering 📐 | 📐 | #3b82f6 | 구현 복잡도, 기술 부채 고려 |
| Security 🔒 | 🔒 | #ef4444 | OWASP 기준, 보안 위협 최우선 |
| Research 🔬 | 🔬 | #06b6d4 | 최신 논문/학술 근거 필수 참조 |
| Product 📦 | 📦 | #8b5cf6 | 시장 수요, UX, 비즈니스 임팩트 |
| Data 📊 | 📊 | #f59e0b | 데이터 기반 판단, 정량적 근거 |
| QA 🧪 | 🧪 | #10b981 | 품질 게이트, 테스트 커버리지 |
| Ops ⚙️ | ⚙️ | #6b7280 | 운영 안정성, 비용 효율 |
| Strategy 📋 | 📋 | #ec4899 | 중장기 전략, 로드맵 정합성 |

### 5.2 시딩 로직 — `main.py`에 추가

```python
def _seed_preset_org() -> None:
    """최초 기동 시 24개 YAML 페르소나 → 프리셋 조직 자동 생성."""
    # 1. 이미 프리셋 있으면 스킵
    # 2. Organization 생성 (is_preset=True)
    # 3. 8개 챕터 생성 (OrganizationChapter)
    # 4. 5개 사일로 생성 (OrganizationSilo)
    # 5. 24개 YAML → OrganizationAgent 행 생성
    #    - C-Level(CEO, ComplianceOfficer): silo_id=NULL, chapter_id=NULL, is_clevel=True
    #    - 나머지: 위 표에 따라 silo_id, chapter_id 매핑
    #    - system_prompt_template: YAML 원본에서 읽기
    #    - weight_score: AGENT_FINAL_WEIGHTS에서 가져오기
```

---

## 6. Phase 3: 파이프라인 통합 — LangGraph + TypedDict

### 커밋: `feat(pipeline): LangGraph 3-level convergence pipeline with silo/chapter structure`

### 6.1 왜 LangGraph인가

| 우리 요구사항 | LangGraph 해법 |
|-------------|---------------|
| 챕터/사일로 수가 조직마다 다름 | **동적 Fan-out** — 런타임에 그래프 분기 수 결정 |
| 챕터 내부 에이전트끼리 토론 | **멀티에이전트 대화** — 노드 간 메시지 교환 |
| 수렴할 때까지 반복 | **조건부 엣지 루프** — 선언적 수렴 제어 |
| Level 1에서 30분 → Level 2 실패 시 재시작 비용 | **체크포인트** — Level 1 결과 보존, Level 2부터 재개 |
| UI에 실시간 진행 표시 | **노드별 스트리밍 이벤트** → SSE |
| 실행 중 사용자 승인 | **interrupt_before** → Human-in-the-loop |

### 6.2 수정 파일

| 파일 | 변경 |
|------|------|
| `src/ora_rd_orchestrator/graph_state.py` | **신규** — TypedDict 상태 정의 |
| `src/ora_rd_orchestrator/graph_nodes.py` | **신규** — 각 노드 함수 |
| `src/ora_rd_orchestrator/graph_builder.py` | **신규** — StateGraph 조립 + compile |
| `src/ora_rd_orchestrator/personas.py` | `PersonaRegistry.from_org_config()` classmethod 추가 |
| `src/ora_rd_orchestrator/pipeline.py` | LangGraph 그래프 실행으로 교체 |
| `src/ora_automation_api/service.py` | `create_run()`에서 org_id → JSON 직렬화 (하이브리드 전달) |
| `src/ora_automation_api/schemas.py` | `OrchestrationRunCreate.org_id` 필드 추가 |
| `pyproject.toml` | `langgraph` 의존성 추가 |

### 6.3 TypedDict 상태 정의 — graph_state.py

```python
# src/ora_rd_orchestrator/graph_state.py
from __future__ import annotations
from typing import TypedDict, Annotated
import operator


class ChapterScore(TypedDict):
    chapter_name: str
    topic_scores: dict[str, float]         # {topic_id: score}
    agent_scores: dict[str, dict[str, float]]  # {agent_id: {topic_id: score}}
    round_count: int
    converged: bool


class SiloSummary(TypedDict):
    silo_name: str
    topic_scores: dict[str, float]
    summary: str                           # LLM이 생성한 사일로 의견 요약
    round_count: int
    converged: bool


class CLevelScore(TypedDict):
    agent_id: str
    topic_scores: dict[str, float]


class PipelineState(TypedDict):
    """3단계 수렴 파이프라인의 전체 상태.

    Annotated[..., operator.add] 필드는 Fan-out 결과를 자동 합산.
    """
    # ── 입력 ──
    org_config: dict
    workspace_path: str

    # ── Topic Discovery ──
    topics: list[dict]
    workspace_summary: dict

    # ── Level 1: 챕터 내부 토론 ──
    chapter_scores: Annotated[list[ChapterScore], operator.add]
    clevel_scores: list[CLevelScore]
    level1_round: int
    level1_complete: bool

    # ── Level 2: 사일로 내부 토론 ──
    silo_summaries: Annotated[list[SiloSummary], operator.add]
    level2_round: int
    level2_complete: bool

    # ── Level 3: 전체 deliberation ──
    final_scores: dict[str, float]
    ranking: list[dict]
    consensus_log: list[dict]
    level3_round: int
    level3_complete: bool

    # ── Report ──
    report_path: str
    report_json: dict

    # ── 메타 ──
    error: str | None
```

**왜 TypedDict인가 (dataclass가 아니라):**

| | dataclass | TypedDict |
|---|-----------|-----------|
| LangGraph 호환 | 변환 필요 | **네이티브** |
| 체크포인트 직렬화 | `asdict()` 필요 | **자동** |
| Fan-in 합산 | 수동 collect | **`Annotated[list, operator.add]`로 자동** |
| 부분 업데이트 | 전체 교체 | **키별 merge** |

기존 `types.py`의 dataclass(`AgentPersona`, `TopicDiscovery` 등)는 **그대로 유지**.
노드 내부에서 dict ↔ dataclass 변환:

```python
def level1_chapter_node(state: PipelineState) -> dict:
    topics = [TopicDiscovery(**t) for t in state["topics"]]
    # ... 로직 ...
    return {"chapter_scores": [result]}  # 부분 업데이트만 반환
```

### 6.4 그래프 구조 — graph_builder.py

```python
# src/ora_rd_orchestrator/graph_builder.py
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from .graph_state import PipelineState
from .graph_nodes import (
    topic_discovery_node,
    workspace_analysis_node,
    level1_fanout_node,
    level1_chapter_node,
    level1_clevel_node,
    level1_convergence_check,
    level2_fanout_node,
    level2_silo_node,
    level2_convergence_check,
    level3_deliberation_node,
    level3_convergence_check,
    consensus_node,
    report_node,
)


def build_pipeline_graph(checkpointer=None) -> StateGraph:
    builder = StateGraph(PipelineState)

    # ── 노드 등록 ──
    builder.add_node("topic_discovery", topic_discovery_node)
    builder.add_node("workspace_analysis", workspace_analysis_node)
    builder.add_node("level1_fanout", level1_fanout_node)
    builder.add_node("level1_chapter", level1_chapter_node)
    builder.add_node("level1_clevel", level1_clevel_node)
    builder.add_node("level1_check", level1_convergence_check)
    builder.add_node("level2_fanout", level2_fanout_node)
    builder.add_node("level2_silo", level2_silo_node)
    builder.add_node("level2_check", level2_convergence_check)
    builder.add_node("level3_deliberation", level3_deliberation_node)
    builder.add_node("level3_check", level3_convergence_check)
    builder.add_node("consensus", consensus_node)
    builder.add_node("report", report_node)

    # ── 엣지 ──
    builder.add_edge(START, "topic_discovery")
    builder.add_edge("topic_discovery", "workspace_analysis")
    builder.add_edge("workspace_analysis", "level1_fanout")

    # Level 1: Fan-out → 챕터별 병렬 + C-Level → Fan-in → 수렴 체크
    builder.add_conditional_edges("level1_fanout", fanout_chapters)
    builder.add_edge("level1_chapter", "level1_check")
    builder.add_edge("level1_clevel", "level1_check")
    builder.add_conditional_edges("level1_check", lambda s: (
        "level2_fanout" if s["level1_complete"] else "level1_fanout"
    ))

    # Level 2: Fan-out → 사일로별 병렬 → Fan-in → 수렴 체크
    builder.add_conditional_edges("level2_fanout", fanout_silos)
    builder.add_edge("level2_silo", "level2_check")
    builder.add_conditional_edges("level2_check", lambda s: (
        "level3_deliberation" if s["level2_complete"] else "level2_fanout"
    ))

    # Level 3: 루프
    builder.add_edge("level3_deliberation", "level3_check")
    builder.add_conditional_edges("level3_check", lambda s: (
        "consensus" if s["level3_complete"] else "level3_deliberation"
    ))

    builder.add_edge("consensus", "report")
    builder.add_edge("report", END)

    return builder.compile(checkpointer=checkpointer or MemorySaver())


def fanout_chapters(state: PipelineState) -> list[str]:
    """org_config의 챕터 수에 따라 동적 Fan-out."""
    chapters = state["org_config"].get("chapters", [])
    destinations = [f"level1_chapter" for _ in chapters]
    destinations.append("level1_clevel")  # C-Level은 항상
    return destinations


def fanout_silos(state: PipelineState) -> list[str]:
    """org_config의 사일로 수에 따라 동적 Fan-out."""
    silos = state["org_config"].get("silos", [])
    return [f"level2_silo" for _ in silos]
```

**시각화:**

```
            ┌──────────────────┐
            │  topic_discovery │
            └────────┬─────────┘
                     ▼
            ┌──────────────────┐
            │workspace_analysis│
            └────────┬─────────┘
                     ▼
            ┌──────────────────┐
     ┌──────│  level1_fanout   │──────┐
     │      └──────────────────┘      │
     ▼               ▼                ▼
┌─────────┐  ┌─────────────┐  ┌───────────┐
│chapter_A │  │ chapter_B   │  │  clevel   │  ← 동적 Fan-out (챕터 수만큼)
└────┬─────┘  └──────┬──────┘  └─────┬─────┘
     └───────────────┼───────────────┘
                     ▼
            ┌──────────────────┐
            │  level1_check    │──── 미수렴 → level1_fanout (재토론)
            └────────┬─────────┘
                     ▼ 수렴
            ┌──────────────────┐
     ┌──────│  level2_fanout   │──────┐
     ▼      └──────────────────┘      ▼
┌─────────┐              ┌─────────────────┐
│ silo_A  │              │     silo_B      │  ← 동적 Fan-out (사일로 수만큼)
└────┬────┘              └───────┬─────────┘
     └───────────┬───────────────┘
                 ▼
            ┌──────────────────┐
            │  level2_check    │──── 미수렴 → level2_fanout (재토론)
            └────────┬─────────┘
                     ▼ 수렴
            ┌──────────────────────┐
            │ level3_deliberation  │◄── 미수렴 ──┐
            └────────┬─────────────┘             │
                     ▼                           │
            ┌──────────────────┐                 │
            │  level3_check    │─────────────────┘
            └────────┬─────────┘
                     ▼ 수렴
            ┌──────────────────┐
            │    consensus     │
            └────────┬─────────┘
                     ▼
            ┌──────────────────┐
            │     report       │
            └──────────────────┘
```

### 6.5 수렴 판정 로직

```python
def is_converged(prev_scores: dict, curr_scores: dict, threshold: float = 0.15) -> bool:
    """이전 라운드 대비 최대 점수 변화가 threshold 미만이면 수렴."""
    if not prev_scores:
        return False
    deltas = [abs(curr_scores[k] - prev_scores[k]) for k in curr_scores]
    return max(deltas) < threshold
```

각 Level의 check 노드에서 호출:
- **수렴** → 다음 Level로 진행
- **미수렴 + 상한 미달** → 같은 Level fanout으로 돌아감 (재토론)
- **상한 도달** → 강제 수렴 처리, 다음 Level로

### 6.6 ORA_ORG_CONFIG 구조

**전달 방식: 하이브리드** (2.14 참조)
- ≤80KB → `ORA_ORG_CONFIG_JSON` 환경변수
- \>80KB → `ORA_ORG_CONFIG_PATH` 파일 경로

```json
{
  "org_id": "uuid",
  "org_name": "My Security Corp",
  "pipeline_params": {
    "level1_max_rounds": 5,
    "level2_max_rounds": 3,
    "level3_max_rounds": 3,
    "convergence_threshold": 0.15,
    "top_k": 6
  },
  "chapters": [
    {
      "id": "uuid",
      "name": "Engineering",
      "shared_directives": ["구현 복잡도 고려"],
      "shared_constraints": [],
      "shared_decision_focus": ["feasibility"],
      "chapter_prompt": "당신은 Engineering 챕터 소속입니다..."
    }
  ],
  "silos": [
    {
      "id": "uuid",
      "name": "취약점 분석",
      "agent_ids": ["SecuritySpec", "Developer_3", "QA_2"]
    }
  ],
  "agents": [
    {
      "agent_id": "Developer",
      "silo_name": "취약점 분석",
      "chapter_name": "Engineering",
      "is_clevel": false,
      "display_name_ko": "...",
      "weights": {},
      "trust_map": {},
      "system_prompt_template": "...",
      "behavioral_directives": [],
      "constraints": [],
      "decision_focus": [],
      "weight_score": 1.2
    }
  ]
}
```

### 6.7 PersonaRegistry 확장

```python
@classmethod
def from_org_config(cls, org_config: dict) -> PersonaRegistry:
    """DB에서 가져온 org config로 레지스트리 생성.
    챕터 프롬프트를 에이전트 프롬프트에 병합.
    """
    # 1. 챕터 맵 구축: chapter_name → chapter_data
    # 2. 각 에이전트:
    #    - chapter의 shared_directives + agent directives 병합
    #    - chapter의 shared_constraints + agent constraints 병합
    #    - chapter의 shared_decision_focus + agent decision_focus 병합
    #    - system_prompt = chapter_prompt + agent system_prompt
    # 3. _parse_persona()로 AgentPersona 변환
```

### 6.8 service.py — create_run()

```python
def create_run(db, payload):
    org_id = payload.org_id
    if not org_id:
        preset = db.scalar(select(Organization).where(Organization.is_preset == True).limit(1))
        if preset:
            org_id = preset.id

    if org_id:
        org_config = serialize_org_config(db, org_id)
        org_json = json.dumps(org_config)
        if len(org_json) > 80_000:
            path = f"/tmp/ora_org_{run_id}.json"
            Path(path).write_text(org_json)
            env["ORA_ORG_CONFIG_PATH"] = path
        else:
            env["ORA_ORG_CONFIG_JSON"] = org_json
```

### 6.9 pipeline.py 변경

```python
from .graph_builder import build_pipeline_graph

# 1. Config 로드
config_raw = os.getenv("ORA_ORG_CONFIG_JSON", "")
if not config_raw:
    config_path = os.getenv("ORA_ORG_CONFIG_PATH", "")
    if config_path:
        config_raw = Path(config_path).read_text()

if not config_raw:
    # CLI 실행 (DB 없음) → YAML 프리셋에서 org config 자동 생성
    config_raw = json.dumps(build_preset_org_config_from_yaml(resolved_persona_dir))

org_config = json.loads(config_raw)

# LangGraph 파이프라인 실행 (유일한 실행 경로)
graph = build_pipeline_graph()
result = graph.invoke({
    "org_config": org_config,
    "workspace_path": workspace_path,
})
# result["report_json"], result["ranking"] 등 사용
```

### 6.10 데이터 흐름 요약

```
1. API: POST /orchestrations {org_id: "xxx"}
2. service.py:
   - org + silos + chapters + agents 조회
   - 하이브리드 직렬화 (env or file)
3. Worker subprocess
4. pipeline.py:
   - config 로드
   - build_pipeline_graph() → LangGraph StateGraph 생성
   - graph.invoke() 실행:
     topic_discovery → workspace_analysis
     → level1_fanout → [chapter_A, chapter_B, ..., clevel] (동적 Fan-out)
     → level1_check → 수렴까지 루프
     → level2_fanout → [silo_A, silo_B, ...] (동적 Fan-out)
     → level2_check → 수렴까지 루프
     → level3_deliberation → level3_check → 수렴까지 루프
     → consensus → report
   - 체크포인트 자동 저장 (Level 실패 시 이전 Level부터 재개 가능)
5. CLI 실행 (DB 없음) → YAML에서 프리셋 org config 자동 생성 → 동일 LangGraph 경로
```

---

## 7. Phase 4: 프론트엔드 — 비주얼 에디터

### 커밋: `feat(frontend): organization designer with silo/chapter structure`

### 7.1 파일 목록

| 파일 | 역할 | 변경 |
|------|------|------|
| `frontend/src/types.ts` | 타입 추가 | `Organization`, `OrgSilo`, `OrgChapter`, `OrgAgent` 등 |
| `frontend/src/lib/api.ts` | API 추가 | 조직/사일로/챕터/에이전트 CRUD 함수 |
| `frontend/src/components/Sidebar.tsx` | 수정 | 3번째 탭 "Orgs" + 대화 회사별 그룹핑 |
| `frontend/src/App.tsx` | 수정 | OrgDesigner 상태 관리, 뷰 전환 |
| `frontend/src/components/OrgPanel.tsx` | **신규** | 조직 목록 + 생성/복제/삭제 |
| `frontend/src/components/OrgDesigner.tsx` | **신규** | 비주얼 에디터 (핵심) |
| `frontend/src/components/AgentEditor.tsx` | **신규** | 에이전트 편집 모달 |
| `frontend/src/components/ChapterEditor.tsx` | **신규** | 챕터 편집 (고급 모드) |

### 7.2 OrgDesigner — 기본 모드

```
┌─────────────────────────────────────────────────────────────┐
│ 🏢 My Security Corp                      [기본] [고급]     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🌟 C-Level (조직 직속)                                    │
│  ┌──────────────────┐  ┌──────────────────────┐            │
│  │ CEO              │  │ ComplianceOfficer     │            │
│  └──────────────────┘  └──────────────────────┘            │
│                                                             │
│  ── 사일로 ──────────────────────────────────────────       │
│                                                             │
│  ┌─ 취약점 분석 ──────────────────────────── [×] ──┐       │
│  │  ┌──────────────────┐ ┌──────────────┐ ┌──────┐│       │
│  │  │ SecuritySpec     │ │ Developer    │ │ QA   ││       │
│  │  │ Security 🔒     │ │ Eng. 📐     │ │ QA 🧪││       │
│  │  └──────────────────┘ └──────────────┘ └──────┘│       │
│  │                                     DROP ZONE  │       │
│  └─────────────────────────────────────────────────┘       │
│                                                             │
│  ┌─ 시장조사 ─────────────────────────────── [×] ──┐       │
│  │  ┌──────────────┐ ┌────────────────┐ ┌────────┐│       │
│  │  │ Researcher   │ │ MarketAnalyst  │ │ DataAn.││       │
│  │  │ Research 🔬 │ │ Product 📦    │ │ Data 📊││       │
│  │  └──────────────┘ └────────────────┘ └────────┘│       │
│  │                                     DROP ZONE  │       │
│  └─────────────────────────────────────────────────┘       │
│                                                             │
│  [+ 사일로 추가]                                            │
│                                                             │
│  ── Agent Palette ──────────────────────────────────        │
│  챕터별:                                                    │
│  Engineering 📐: [Developer] [DevOpsSRE] [TechLead]        │
│  Security 🔒:   [SecuritySpec]                              │
│  Research 🔬:   [Researcher]                                │
│  [+ 새 에이전트]                                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

- 에이전트 카드에 **챕터 뱃지** (아이콘 + 색상) 표시
- Agent Palette는 **챕터별로 그룹** — 어떤 전문 분야인지 한눈에
- 드래그하여 사일로에 배치
- C-Level 영역은 맨 위 고정
- 사일로 내부는 수평 나열 (상하관계 없음)

### 7.3 OrgDesigner — 고급 모드

기본 모드에 추가로:

```
│  ── 챕터 관리 (고급) ──────────────────────────────         │
│  ┌─────────────────────────────────────────────────┐       │
│  │ Engineering 📐                          [편집]  │       │
│  │  chapter_prompt: "기술 구현 관점으로..."         │       │
│  │  shared_directives: 2개                         │       │
│  │  소속: Developer, DevOpsSRE, TechLead           │       │
│  ├─────────────────────────────────────────────────┤       │
│  │ Security 🔒                             [편집]  │       │
│  │  chapter_prompt: "보안 위협 관점으로..."         │       │
│  │  shared_directives: 1개                         │       │
│  │  소속: SecuritySpecialist                       │       │
│  ├─────────────────────────────────────────────────┤       │
│  │ [+ 챕터 추가]                                   │       │
│  └─────────────────────────────────────────────────┘       │
│                                                             │
│  ── Pipeline Settings (고급) ──────────────────────         │
│  L1 Max Rounds: [5 ▼]  L2 Max Rounds: [3 ▼]               │
│  L3 Max Rounds: [3 ▼]  Convergence: [0.15   ]              │
│  Top K: [6 ▼]  Profile: [standard ▼]                       │
│  Service Scope: ☑ b2b  ☑ ai  ☐ telecom  ☐ b2c             │
```

### 7.4 AgentEditor — 에이전트 편집 모달

에이전트 카드 더블클릭 시 표시:

```
┌───────────────────────────────────────┐
│ Agent: SecuritySpecialist         [×] │
├───────────────────────────────────────┤
│ 기본 정보                             │
│  ID: SecuritySpecialist               │
│  이름: [Security Specialist      ]    │
│  한국어: [보안 전문가 (공격자 관...]   │
│  역할: [security_specialist ▼]        │
│  사일로: [취약점 분석 ▼]              │
│  챕터: [Security 🔒 ▼]              │
│  영향력: ████████░░  0.12 (weight)    │
├───────────────────────────────────────┤
│ 성격 (Personality)                    │
│  Archetype: [...]                     │
│  Motivation: [...]                    │
│  Communication: [...]                 │
├───────────────────────────────────────┤
│ 행동 지침                             │
│  📌 챕터 공유: "OWASP Top 10..."     │  ← 챕터에서 상속 (읽기 전용)
│  1. [에이전트 고유 지침...]    [×]    │
│  [+ 추가]                             │
├───────────────────────────────────────┤
│ 가중치 (Weights)                      │
│  impact:     ████████████  0.46       │
│  novelty:    ██████        0.23       │
│  feasibility:████          0.14       │
├───────────────────────────────────────┤
│ 신뢰도 (Trust Map)                    │
│  CEO:      ██████████  1.00           │
│  Planner:  ████████    0.78           │
├───────────────────────────────────────┤
│ 시스템 프롬프트 (고급)                │
│ ┌─────────────────────────────────┐   │
│ │ 당신은 {display_name_ko}입니... │   │
│ └─────────────────────────────────┘   │
├───────────────────────────────────────┤
│ [취소]  [저장]                        │
└───────────────────────────────────────┘
```

챕터에서 상속받은 지침은 **읽기 전용으로 표시** — "이건 챕터에서 온 거야"라는 걸 명확히.

---

## 8. Phase 5: 대화-회사 연결 + 사이드바

### 커밋: `feat(org): conversation-organization binding with sidebar grouping`

### 8.1 수정 파일

| 파일 | 변경 |
|------|------|
| `frontend/src/components/Sidebar.tsx` | 대화를 회사별로 그룹핑, Orgs 탭 추가 |
| `frontend/src/components/ChatWindow.tsx` | 현재 대화의 회사 표시, Switch UI |
| `frontend/src/App.tsx` | 조직 상태 관리 |
| `src/ora_automation_api/chat_router.py` | Conversation CRUD에 org_id 지원 |

### 8.2 ChatWindow — 회사 표시 + Switch

```
┌─────────────────────────────────────────────┐
│ 🏢 My Security Corp [변경 ▼]              │  ← 상단 바
├─────────────────────────────────────────────┤
│                                             │
│ (대화 메시지들)                             │
│                                             │
├─────────────────────────────────────────────┤
│ [메시지 입력...]                   [전송]   │
└─────────────────────────────────────────────┘
```

실행 확인 시 회사 자동 적용:

```
┌─────────────────────────────────┐
│ 실행 계획                        │
│ target: run-cycle               │
│ 🏢 My Security Corp            │  ← 대화의 회사가 자동 적용
│ [취소]  [실행]                   │
└─────────────────────────────────┘
```

---

## 9. Phase 6: Gemini 기반 조직 추천 (UPCE 통합)

### 커밋: `feat(chat): org recommendation via Gemini in UPCE dialog engine`

### 9.1 UPCE 흐름 변경

```
기존: UNDERSTANDING → PROJECT_SELECT → SLOT_FILLING → CONFIRMING → EXECUTING → REPORTING
변경: UNDERSTANDING → PROJECT_SELECT → ORG_RECOMMEND → SLOT_FILLING → CONFIRMING → EXECUTING → REPORTING
```

### 9.2 ORG_RECOMMEND 스테이지

- 조직 1개 → 자동 적용, 스킵
- 조직 2개+ → Gemini가 작업 + 조직 목록(사일로/챕터 구성 포함) 분석 → 추천

```
🤖 이 작업은 보안 분석에 특화되어 있어요.

   🏢 My Security Corp를 추천합니다.
   (취약점 분석 사일로 + Security 챕터 보유)

   ┌───────────────────────────────────┐
   │ ★ My Security Corp       [선택] │
   │   Default (Toss Silo)    [선택] │
   └───────────────────────────────────┘
```

---

## 10. Phase 7: 협업 모드

### 10.1 Switch — 회사 변경 (MVP)

Phase 5에서 구현. ChatWindow 상단 "[변경]" 드롭다운.

### 10.2 Guest — 에이전트 빌려오기 (V2)

```python
class OrchestrationRun(Base):
    guest_agent_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
```

다른 회사의 에이전트를 이번 run에만 임시 추가.

### 10.3 Joint — 회사 합병 실행 (V3)

```python
class OrchestrationRun(Base):
    joint_org_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
```

두 회사의 에이전트 + 챕터 지식을 병합하여 실행.

---

## 11. Phase 8: 테스트

### 커밋: `test(org): organization/silo/chapter/agent CRUD + 3-level pipeline tests`

```python
class TestOrganizationCRUD:
    # 조직 생성/조회/수정/삭제
    # 프리셋 삭제 거부

class TestSiloCRUD:
    # 사일로 추가/수정/삭제
    # 사일로 삭제 시 소속 에이전트 silo_id = NULL

class TestChapterCRUD:
    # 챕터 추가/수정/삭제
    # shared_directives 업데이트

class TestOrganizationAgents:
    # 에이전트 추가/수정/삭제
    # C-Level: silo_id=NULL, chapter_id=NULL
    # 일반: silo_id + chapter_id 설정
    # 필수 필드만으로 생성 → 기본값 확인
    # 복제 → agent_id 변경 확인

class TestOrganizationClone:
    # deep copy: org + silos + chapters + agents
    # is_preset=False

class TestPresetSeeding:
    # 시작 시 프리셋 생성: 5 silos, 8 chapters, 24 agents
    # 중복 시딩 방지

class TestChapterPromptMerge:
    # 챕터 shared_directives + agent directives 병합 확인
    # chapter_prompt + agent system_prompt 병합 확인

class TestAutoDerivation:
    # derive_flat_mode_agents() — enabled=true만
    # derive_agent_final_weights() — weight_score 정규화

class TestGraphState:
    # PipelineState TypedDict 생성/부분 업데이트
    # Annotated[list, operator.add] Fan-in 합산 동작

class TestConvergence:
    # is_converged() — threshold 이하 수렴 판정
    # is_converged() — threshold 초과 미수렴

class TestLevel1ChapterNode:
    # level1_chapter_node — 같은 챕터 에이전트끼리 토론 → ChapterScore 반환
    # level1_clevel_node — C-Level 개별 평가 → CLevelScore 반환
    # level1_convergence_check — max_rounds 도달 시 강제 수렴
    # fanout_chapters — 동적 Fan-out (챕터 수만큼 분기)

class TestLevel2SiloNode:
    # level2_silo_node — 챕터 대표 → 사일로 내 토론 → SiloSummary 반환
    # level2_convergence_check — 수렴 조기 종료
    # fanout_silos — 동적 Fan-out (사일로 수만큼 분기)

class TestLevel3DeliberationNode:
    # level3_deliberation_node — C-Level + 사일로 대표 deliberation
    # level3_convergence_check — 랭킹 안정화 수렴

class TestGraphIntegration:
    # build_pipeline_graph() → graph.invoke() 통합 테스트
    # 소규모 (5 에이전트) — 전체 흐름 정상 동작
    # 중규모 (50 에이전트) — 동적 Fan-out + 수렴
    # 대규모 (200 에이전트 mock) — LLM 호출 수 검증
    # 체크포인트 — Level 2 실패 후 Level 1 결과 보존/재개

class TestOrgConfigTransfer:
    # ≤80KB → ORA_ORG_CONFIG_JSON 환경변수
    # >80KB → ORA_ORG_CONFIG_PATH 파일 경로
    # pipeline.py에서 양쪽 모두 로드 가능

class TestConversationOrgBinding:
    # conversation.org_id 설정/변경
    # org_id=NULL → 프리셋 자동 적용

class TestRunWithOrg:
    # org_id → config 직렬화 확인
    # 사일로, 챕터, 에이전트, pipeline_params 모두 포함

class TestPersonaRegistryFromOrgConfig:
    # from_org_config()로 생성
    # 챕터 프롬프트 병합 확인

class TestInputValidation:
    # agent_id 형식 (영문+숫자+_, 3-64자)
    # system_prompt_template 길이 상한 (4000자)
    # chapter_prompt 길이 상한 (2000자)

class TestOrgRecommendation:
    # 조직 1개 → 스킵
    # 조직 2개+ → Gemini 추천
```

---

## 12. 검증 체크리스트

### 자동 검증

```bash
PYTHONPATH=src python3 -m pytest tests/ -v
cd frontend && npx tsc --noEmit
cd frontend && npx vite build
```

### 수동 검증

| # | 검증 항목 | 확인 방법 |
|---|----------|----------|
| 1 | 프리셋 자동 생성 | GET /api/v1/orgs → "Default (Toss Silo)" + 5 silos + 8 chapters + 24 agents |
| 2 | 사일로 CRUD | POST/PATCH/DELETE 사일로 |
| 3 | 챕터 CRUD | 챕터 생성 → shared_directives 설정 → 소속 에이전트에 반영 |
| 4 | 에이전트 배치 | 에이전트 생성 → silo + chapter 지정 |
| 5 | C-Level | silo=NULL, chapter=NULL인 에이전트 생성 |
| 6 | 조직 복제 | clone → silos + chapters + agents deep copy |
| 7 | 챕터 프롬프트 병합 | ORA_ORG_CONFIG에서 병합된 프롬프트 확인 |
| 8 | 자동 파생 | enabled 에이전트 → flat_mode_agents, weight_score → agent_final_weights |
| 9 | 3단계 파이프라인 | Level 1(챕터) → Level 2(사일로) → Level 3(전체) 수렴 확인 |
| 10 | 수렴 판정 | 점수 분산 < threshold 시 조기 종료 확인 |
| 11 | 대규모 에이전트 | 100+ 에이전트 org → 파이프라인 정상 완료 |
| 12 | Config 하이브리드 전달 | ≤80KB → env, >80KB → file 자동 분기 |
| 13 | 사이드바 그룹핑 | Chats 탭에서 회사별 대화 그룹 |
| 14 | 기본/고급 모드 | 기본: 사일로+에이전트만, 고급: 챕터+파이프라인 |
| 15 | 챕터 뱃지 | 에이전트 카드에 챕터 아이콘+색상 표시 |
| 16 | 조직 추천 | 조직 2개+ 보유 시 Gemini 추천 |
| 17 | 입력 검증 | agent_id 형식, prompt 길이 상한 |
| 18 | CLI 실행 | make run → YAML 프리셋에서 org config 자동 생성 → LangGraph 파이프라인 동작 |

---

## 13. 구현 순서 요약

| Phase | 커밋 메시지 | 핵심 변경 | 시기 |
|-------|------------|-----------|------|
| 1 | `feat(org): add organization/silo/chapter/agent models and CRUD API` | models.py, schemas.py, org_router.py, main.py | MVP |
| 2 | `feat(org): seed preset organization from YAML personas on startup` | main.py `_seed_preset_org()` | MVP |
| 3 | `feat(pipeline): LangGraph 3-level convergence pipeline` | graph_state.py, graph_nodes.py, graph_builder.py, personas.py, pipeline.py, service.py | MVP |
| 4 | `feat(frontend): organization designer with silo/chapter structure` | OrgDesigner, AgentEditor, ChapterEditor, types.ts, api.ts | MVP |
| 5 | `feat(org): conversation-organization binding with sidebar grouping` | Sidebar.tsx, ChatWindow.tsx, chat_router.py | MVP |
| 6 | `feat(chat): org recommendation via Gemini in UPCE dialog engine` | chat_router.py, llm_planner.py, ChatWindow.tsx | MVP |
| 7a | `feat(org): switch organization mid-conversation` | (Phase 5에 포함) | MVP |
| 7b | `feat(org): guest agent collaboration mode` | OrchestrationRun.guest_agent_ids | V2 |
| 7c | `feat(org): joint organization run mode` | OrchestrationRun.joint_org_ids | V3 |
| 8 | `test(org): organization/silo/chapter/agent CRUD + pipeline tests` | test_organizations.py | MVP |

### MVP 범위

**포함:**
- 조직/사일로/챕터/에이전트 CRUD API
- 프리셋 시딩 (토스 스타일 5 silos + 8 chapters + 24 agents)
- 파이프라인 통합 (챕터 프롬프트 병합, 자동 파생)
- 비주얼 에디터 (기본/고급 모드)
- 대화-회사 연결 + 사이드바 그룹핑
- Switch 협업
- Gemini 조직 추천
- 테스트

**V2:**
- Guest 협업 (에이전트 빌려오기)
- Level C 커스터마이징 (Hierarchical mode)

**V3:**
- Joint 협업 (회사 합병 실행)
