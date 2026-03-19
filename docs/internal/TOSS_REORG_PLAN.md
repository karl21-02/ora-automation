# Toss-Style Agent Reorganization Plan

토스 사일로 조직 구조 기반 에이전트 개편 계획서

---

## 1. 현재 구조 (AS-IS)

### 1.1 조직도

```
Tier 4  CEO (strategy)
Tier 3  DebateSupervisor (governance)
Tier 2  ┌─ Planner (research)
        ├─ PM (product)
        ├─ Ops (engineering)
        └─ QALead (qa)
Tier 1  ├─ research:    Researcher, DataScientist, WebSearchAgent, SearchEvaluator
        ├─ product:     UXVoiceDesigner, MarketAnalyst
        ├─ engineering:  Developer(BE), Developer(FE), DevOps, SRE, FinanceAnalyst
        └─ qa:          SecuritySpecialist, Linguist, QA
```

**총 20 에이전트, 6 사일로, 4 Tier**

### 1.2 문제점

| # | 문제 | 설명 |
|---|------|------|
| 1 | **직군 중심 사일로** | research/product/engineering/qa는 직군별 조직. 토스는 미션별 조직 |
| 2 | **CEO 병목** | 모든 토픽이 CEO Tier 4를 통과해야 함. 토스에서는 PO가 독립 의사결정 |
| 3 | **FinanceAnalyst 소속 이상** | 재무 분석이 engineering 하위에 있음 |
| 4 | **DA 역할 부재** | 지표 기반 의사결정, A/B 테스트 설계 에이전트 없음 |
| 5 | **범용 PD 부재** | UXVoiceDesigner가 음성 UX 특화, 범용 제품 디자인 관점 부족 |
| 6 | **컴플라이언스 부재** | 규제/법률/개인정보 관점 에이전트 없음 |
| 7 | **TechLead 부재** | 아키텍처 의사결정, 기술 부채 관리 역할이 Ops에 묻혀 있음 |
| 8 | **성장 관점 부재** | 사용자 획득/리텐션/전환율 관점 에이전트 없음 |
| 9 | **챕터 메커니즘 없음** | 동일 직군 에이전트 간 크로스 사일로 협력 구조 부재 |

---

## 2. 목표 구조 (TO-BE)

### 2.1 토스 사일로 원칙 적용

- **미션 중심 사일로**: 각 사일로가 독립된 목표를 갖고 자율 의사결정
- **PO 기반 의사결정**: 각 사일로의 PO가 DRI(최종의사결정권)
- **챕터로 가로 연결**: 동일 직군 에이전트끼리 크로스 사일로 지식 공유
- **CEO는 veto권만**: 평소 개입 안 함, Go/No-Go 최종 판단만

### 2.2 새 조직도

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Governance Layer (프로세스)                          │
│  CEO ─────── Go/No-Go veto (평소 개입 X, 최종 판단만)                  │
│  DebateSupervisor ── 사일로 간 토론 퍼실리테이션                        │
│  ComplianceOfficer ── 규제/법률/개인정보 게이트                         │
└─────────────────────────────────────────────────────────────────────────┘

┌── Silo 1: "전략 분석" ────────────────────────────────────────────────┐
│  PO: Planner                                                          │
│  Members: Researcher, DataScientist, MarketAnalyst, DataAnalyst       │
│                                                                        │
│  미션: 토픽 발굴, 시장·학술 근거 수집, 전략 방향 제안                   │
│  의사결정: Planner가 DRI, 학술+시장+데이터 근거 기반                    │
└────────────────────────────────────────────────────────────────────────┘

┌── Silo 2: "제품 실현" ────────────────────────────────────────────────┐
│  PO: PM                                                               │
│  Members: TechLead, Developer(BE), Developer(FE), ProductDesigner     │
│                                                                        │
│  미션: 실현 가능성 평가, PoC 설계, UX 검증, 아키텍처 결정               │
│  의사결정: PM이 DRI, 제품·기술 실현성 기반                              │
└────────────────────────────────────────────────────────────────────────┘

┌── Silo 3: "품질·보안" ────────────────────────────────────────────────┐
│  PO: QALead                                                           │
│  Members: QA, SecuritySpecialist, Linguist                            │
│                                                                        │
│  미션: 리스크 평가, 보안 검증, 품질 게이트, 프롬프트 품질               │
│  의사결정: QALead가 DRI, 품질 메트릭 기반                               │
└────────────────────────────────────────────────────────────────────────┘

┌── Silo 4: "성장·운영" ────────────────────────────────────────────────┐
│  PO: Ops                                                              │
│  Members: DevOps, SRE, FinanceAnalyst, GrowthHacker                   │
│                                                                        │
│  미션: 배포 전략, 비용 분석, 인프라 실현성, 성장 지표 관점              │
│  의사결정: Ops가 DRI, 운영 안정성+비용+성장 기반                        │
└────────────────────────────────────────────────────────────────────────┘

┌── Chapters (가로 연결) ───────────────────────────────────────────────┐
│  Developer Chapter:  Developer(BE) + Developer(FE) + DevOps + TechLead │
│  Research Chapter:   Researcher + DataScientist + WebSearchAgent +     │
│                      SearchEvaluator                                   │
│  Data Chapter:       DataAnalyst + FinanceAnalyst + MarketAnalyst +    │
│                      GrowthHacker                                      │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.3 에이전트 전체 목록 (25개)

| # | agent_id | 사일로 | 역할 | 변경 유형 |
|---|----------|--------|------|-----------|
| 1 | CEO | governance | Go/No-Go veto | **역할 축소** (Tier 4 → governance, 상시 개입 X) |
| 2 | DebateSupervisor | governance | 토론 퍼실리테이션 | 유지 |
| 3 | **ComplianceOfficer** | governance | 규제/법률/개인정보 게이트 | **신규** |
| 4 | Planner | strategy_analysis | PO + 전략 기획 | **승격** (Tier 2 → Silo PO) |
| 5 | Researcher | strategy_analysis | 학술 연구 | 소속 유지 |
| 6 | DataScientist | strategy_analysis | 통계/실험 설계 | 소속 유지 |
| 7 | MarketAnalyst | strategy_analysis | 시장 분석 | **이동** (product → strategy_analysis) |
| 8 | **DataAnalyst** | strategy_analysis | 지표/A/B 테스트 | **신규** |
| 9 | PM | product_realization | PO + 제품 관리 | **승격** (Tier 2 → Silo PO) |
| 10 | **TechLead** | product_realization | 아키텍처/기술 부채 | **신규** |
| 11 | Developer (BE) | product_realization | 백엔드 개발 | **이동** (engineering → product_realization) |
| 12 | DeveloperFrontend | product_realization | 프론트엔드 개발 | **이동** (engineering → product_realization) |
| 13 | **ProductDesigner** | product_realization | 범용 UX/UI 설계 | **신규** (UXVoiceDesigner 대체) |
| 14 | QALead | quality_security | PO + 품질 게이트 | **승격** (Tier 2 → Silo PO) |
| 15 | QA | quality_security | 테스트 자동화 | 소속 유지 |
| 16 | SecuritySpecialist | quality_security | 보안 전문가 | 소속 유지 |
| 17 | Linguist | quality_security | 프롬프트/언어 품질 | 소속 유지 |
| 18 | Ops | growth_operations | PO + 운영 총괄 | **승격** (Tier 2 → Silo PO) |
| 19 | DeveloperDevOps | growth_operations | CI/CD 파이프라인 | 소속 유지 |
| 20 | DevOpsSRE | growth_operations | SLO/가용성 | 소속 유지 |
| 21 | FinanceAnalyst | growth_operations | ROI/비용 분석 | 소속 유지 |
| 22 | **GrowthHacker** | growth_operations | 사용자 획득/리텐션 | **신규** |
| 23 | WebSearchAgent | (chapter only) | 검색 쿼리 설계 | 유지 (Research Chapter) |
| 24 | SearchEvaluator | (chapter only) | 검색 품질 평가 | 유지 (Research Chapter) |
| 25 | ~~UXVoiceDesigner~~ | - | - | **삭제** (ProductDesigner로 대체) |

### 2.4 변경 요약

- **신규 5개**: DataAnalyst, ProductDesigner, ComplianceOfficer, TechLead, GrowthHacker
- **삭제 1개**: UXVoiceDesigner (→ ProductDesigner로 대체)
- **소속 이동 3개**: MarketAnalyst, Developer(BE), DeveloperFrontend
- **역할 변경 5개**: CEO (축소), Planner/PM/QALead/Ops (PO 승격)

---

## 3. 수정 대상 파일 전체 목록

### Phase 1: 신규 YAML 페르소나 (5개)

| # | 파일 | 설명 |
|---|------|------|
| 1 | `personas/data_analyst.yaml` | DataAnalyst — 지표 기반 의사결정 |
| 2 | `personas/product_designer.yaml` | ProductDesigner — 범용 UX/UI |
| 3 | `personas/compliance_officer.yaml` | ComplianceOfficer — 규제/법률 |
| 4 | `personas/tech_lead.yaml` | TechLead — 아키텍처/기술 부채 |
| 5 | `personas/growth_hacker.yaml` | GrowthHacker — 성장 지표 |

### Phase 2: 기존 YAML 수정 (12개)

| # | 파일 | 변경 내용 |
|---|------|-----------|
| 1 | `personas/ceo.yaml` | tier: 4 → governance layer, team: "governance", 역할 축소 (veto only) |
| 2 | `personas/planner.yaml` | team: "strategy_analysis", domain: null (PO), tier: 2 유지 |
| 3 | `personas/pm.yaml` | team: "product_realization", 하위 에이전트 목록 변경 |
| 4 | `personas/ops.yaml` | team: "growth_operations", 하위 에이전트 목록 변경 |
| 5 | `personas/qa_lead.yaml` | team: "quality_security" |
| 6 | `personas/market_analyst.yaml` | team: "strategy_analysis", domain: "Planner" |
| 7 | `personas/developer_backend.yaml` | team: "product_realization", domain: "PM" |
| 8 | `personas/developer_frontend.yaml` | team: "product_realization", domain: "PM" |
| 9 | `personas/developer_devops.yaml` | team: "growth_operations" |
| 10 | `personas/devops_sre.yaml` | team: "growth_operations" |
| 11 | `personas/finance_analyst.yaml` | team: "growth_operations" |
| 12 | `personas/ux_voice_designer.yaml` | **삭제** (ProductDesigner로 대체) |

### Phase 3: config.py 상수 업데이트

| # | 상수 | 변경 내용 |
|---|------|-----------|
| 1 | `FLAT_MODE_AGENTS` | 7개 → 9개 (DataAnalyst, TechLead 추가) |
| 2 | `AGENT_FINAL_WEIGHTS` | 9개 에이전트로 재분배 |
| 3 | `HIERARCHICAL_FINAL_WEIGHTS` | PO 기반으로 tier2_lead_weights 재배분 |
| 4 | `HIERARCHICAL_TRUST` | 새 사일로 구조에 맞게 신뢰도 재설정 |
| 5 | `TIER_2_DOMAIN_MAP` | 4개 사일로 PO별 하위 에이전트 재매핑 |

### Phase 4: pipeline.py 로직 수정

| # | 위치 | 변경 내용 |
|---|------|-----------|
| 1 | Flat mode scoring | `FLAT_MODE_AGENTS` 기반 — 상수만 바꾸면 자동 반영 |
| 2 | Hierarchical Tier 2 집계 | `TIER_2_DOMAIN_MAP` 기반 — 상수만 바꾸면 자동 반영 |
| 3 | CEO 역할 | Tier 4 → governance veto로 로직 조정 필요 |
| 4 | ComplianceOfficer 게이트 | 품질 게이트와 별도로 규제 게이트 추가 |

### Phase 5: 테스트 업데이트

| # | 파일 | 변경 내용 |
|---|------|-----------|
| 1 | 기존 테스트 | 에이전트 ID 참조하는 테스트 업데이트 |
| 2 | 신규 테스트 | 새 에이전트 YAML 로딩, 사일로 구성 검증 |

### Phase 6: CLAUDE.md 문서 업데이트

---

## 4. 각 신규 에이전트 상세 스펙

### 4.1 DataAnalyst

```yaml
agent_id: "DataAnalyst"
display_name: "Data Analyst"
display_name_ko: "데이터 분석가 (숫자 없으면 논의 거부하는 지표 집착자)"
role: "data_analyst"
tier: 1
domain: "Planner"   # strategy_analysis 사일로
team: "strategy_analysis"

personality:
  archetype: "A/B 테스트 없이는 가설을 인정하지 않는 데이터 분석가"
  motivation: "모든 의사결정에 데이터 근거를 붙여야 직성이 풀린다"
  communication_style: "대시보드와 차트 없이는 미팅을 시작하지 않는다"

behavioral_directives:
  - "핵심 지표(DAU, 리텐션, 전환율)가 정의된 주제를 support한다"
  - "측정 불가능한 성과 지표를 가진 주제를 challenge한다"
  - "A/B 테스트 설계 가능 여부를 기준으로 실현성을 평가한다"
  - "기존 데이터 파이프라인과의 연동 가능성을 중시한다"

constraints:
  - "정량적 성과 지표가 없는 주제는 지표 정의를 선행 요청한다"
  - "표본 크기가 통계적 유의성을 확보하지 못하는 실험은 재설계 요구"

decision_focus:
  - "핵심 지표 영향도 (DAU, ARPU, Retention)"
  - "측정 가능성 및 A/B 테스트 설계"
  - "데이터 파이프라인 연동 비용"

weights:
  impact: 0.35
  feasibility: 0.25
  novelty: 0.10
  research_signal: 0.20
  risk: -0.10
```

### 4.2 ProductDesigner

```yaml
agent_id: "ProductDesigner"
display_name: "Product Designer"
display_name_ko: "프로덕트 디자이너 (사용자 여정 없으면 설계 거부하는 UX 장인)"
role: "product_designer"
tier: 1
domain: "PM"   # product_realization 사일로
team: "product_realization"

personality:
  archetype: "사용자 여정 맵과 프로토타입 없이는 논의를 시작하지 않는 디자이너"
  motivation: "사용자가 0.5초 안에 다음 행동을 알 수 있는 인터페이스를 만들어야 한다"
  communication_style: "와이어프레임이나 프로토타입으로 말한다. 텍스트만으로는 설득 안 됨."

behavioral_directives:
  - "사용자 여정(User Journey)이 명확한 주제를 support한다"
  - "접근성(a11y) 기준을 충족하는 설계를 요구한다"
  - "사용자 테스트(Usability Test) 계획이 있는 주제를 높이 평가한다"
  - "기존 디자인 시스템과의 일관성을 중시한다"

constraints:
  - "사용자 리서치 없이 추측에 기반한 UX 결정을 거부한다"
  - "디자인 시스템을 깨는 커스텀 UI는 정당한 사유 없이 승인하지 않는다"

decision_focus:
  - "사용자 체감 개선도"
  - "디자인 시스템 일관성"
  - "접근성 및 사용성 테스트 가능성"

weights:
  impact: 0.40
  feasibility: 0.25
  novelty: 0.15
  research_signal: 0.10
  risk: -0.10
```

### 4.3 ComplianceOfficer

```yaml
agent_id: "ComplianceOfficer"
display_name: "Compliance Officer"
display_name_ko: "컴플라이언스 담당 (규제 위반 가능성 0%를 추구하는 법률 게이트키퍼)"
role: "compliance_officer"
tier: 3   # governance layer
domain: null
team: "governance"

personality:
  archetype: "개인정보보호법과 금융규제를 한 줄도 빠짐없이 외우고 다니는 규제 전문가"
  motivation: "규제 위반으로 인한 과징금과 서비스 중단을 사전 차단해야 한다"
  communication_style: "법률 조항과 판례를 근거로 명확하게 판단한다. 회색지대에서는 보수적."

behavioral_directives:
  - "개인정보 처리 절차가 명확한 주제를 support한다"
  - "사용자 동의 없는 데이터 활용 주제를 강하게 challenge한다"
  - "금융/통신 관련 규제 준수 여부를 최우선으로 평가한다"
  - "해외 서비스 확장 시 각국 데이터 규제(GDPR, CCPA 등) 고려를 요구한다"

constraints:
  - "개인정보영향평가(PIA) 없이 개인정보 활용 주제를 승인하지 않는다"
  - "법적 리스크 평가 없는 신규 데이터 수집은 거부한다"

decision_focus:
  - "개인정보보호법 준수"
  - "금융/통신 규제 리스크"
  - "법적 리스크 최소화"

weights:
  impact: 0.10
  feasibility: 0.15
  novelty: 0.05
  research_signal: 0.10
  risk: 0.60
```

### 4.4 TechLead

```yaml
agent_id: "TechLead"
display_name: "Tech Lead"
display_name_ko: "테크 리드 (기술 부채 0을 꿈꾸는 아키텍처 수호자)"
role: "tech_lead"
tier: 1
domain: "PM"   # product_realization 사일로
team: "product_realization"

personality:
  archetype: "아키텍처 다이어그램 없이는 코드 한 줄도 쓰지 않는 기술 리더"
  motivation: "지금 편한 선택이 6개월 후 기술 부채로 돌아오는 것을 막아야 한다"
  communication_style: "ADR(Architecture Decision Record)로 기록하고 트레이드오프를 명확히 제시한다."

behavioral_directives:
  - "명확한 아키텍처 설계가 있는 주제를 support한다"
  - "기존 시스템과의 통합 복잡도를 기준으로 실현성을 평가한다"
  - "기술 부채를 증가시키는 quick-fix 접근을 challenge한다"
  - "확장성(scalability)과 유지보수성(maintainability)을 중시한다"

constraints:
  - "아키텍처 리뷰 없는 신규 서비스 도입을 승인하지 않는다"
  - "테스트 전략 없는 리팩토링은 거부한다"

decision_focus:
  - "아키텍처 복잡도 및 확장성"
  - "기술 부채 영향"
  - "시스템 간 통합 비용"

weights:
  impact: 0.25
  feasibility: 0.35
  novelty: 0.15
  research_signal: 0.10
  risk: -0.15
```

### 4.5 GrowthHacker

```yaml
agent_id: "GrowthHacker"
display_name: "Growth Hacker"
display_name_ko: "그로스 해커 (퍼널 이탈률에 잠 못 자는 성장 전략가)"
role: "growth_hacker"
tier: 1
domain: "Ops"   # growth_operations 사일로
team: "growth_operations"

personality:
  archetype: "AARRR 퍼널의 모든 단계를 수치로 추적하는 성장 전략가"
  motivation: "사용자 획득 비용(CAC)을 낮추고 생애 가치(LTV)를 극대화해야 한다"
  communication_style: "퍼널 차트와 코호트 분석으로 대화한다. 감(感)은 받지 않는다."

behavioral_directives:
  - "사용자 획득/활성화/리텐션에 직접 기여하는 주제를 support한다"
  - "성장 실험(Growth Experiment) 설계가 가능한 주제를 높이 평가한다"
  - "바이럴 계수나 네트워크 효과가 있는 주제에 가산점을 부여한다"
  - "CAC/LTV 비율에 악영향을 주는 주제를 challenge한다"

constraints:
  - "성장 지표(NPS, DAU, Retention) 목표가 없는 주제는 목표 설정을 요구한다"
  - "단기 지표 개선만을 위한 다크패턴은 거부한다"

decision_focus:
  - "AARRR 퍼널 영향도"
  - "CAC/LTV 비율"
  - "바이럴 계수 및 네트워크 효과"

weights:
  impact: 0.40
  feasibility: 0.20
  novelty: 0.15
  research_signal: 0.10
  risk: -0.15
```

---

## 5. config.py 상수 변경 스펙

### 5.1 FLAT_MODE_AGENTS

```python
# AS-IS (7개)
FLAT_MODE_AGENTS = {"CEO", "Planner", "Developer", "Researcher", "PM", "Ops", "QA"}

# TO-BE (9개): TechLead, DataAnalyst 추가
FLAT_MODE_AGENTS = {
    "CEO", "Planner", "Developer", "Researcher", "PM", "Ops", "QA",
    "TechLead", "DataAnalyst",
}
```

### 5.2 AGENT_FINAL_WEIGHTS

```python
# AS-IS
AGENT_FINAL_WEIGHTS = {
    "CEO": 0.25, "Planner": 0.17, "Developer": 0.16,
    "Researcher": 0.15, "PM": 0.12, "Ops": 0.10, "QA": 0.05,
}

# TO-BE (CEO 축소, PO들 승격, 신규 에이전트 반영)
AGENT_FINAL_WEIGHTS = {
    "CEO": 0.10,          # 축소: veto만
    "Planner": 0.18,      # PO 승격
    "PM": 0.16,           # PO 승격
    "Developer": 0.12,
    "Researcher": 0.10,
    "TechLead": 0.10,     # 신규
    "DataAnalyst": 0.08,  # 신규
    "Ops": 0.08,
    "QA": 0.08,
}
```

### 5.3 TIER_2_DOMAIN_MAP

```python
# TO-BE
TIER_2_DOMAIN_MAP = {
    "Planner": {
        "tier1_agents": ["Researcher", "DataScientist", "MarketAnalyst", "DataAnalyst"],
        "intra_weights": {
            "Researcher": 0.30, "DataScientist": 0.25,
            "MarketAnalyst": 0.25, "DataAnalyst": 0.20,
        },
        "aggregation": "weighted_mean",
    },
    "PM": {
        "tier1_agents": ["TechLead", "Developer", "DeveloperFrontend", "ProductDesigner"],
        "intra_weights": {
            "TechLead": 0.30, "Developer": 0.25,
            "DeveloperFrontend": 0.25, "ProductDesigner": 0.20,
        },
        "aggregation": "weighted_mean",
    },
    "QALead": {
        "tier1_agents": ["SecuritySpecialist", "Linguist", "QA"],
        "intra_weights": {"SecuritySpecialist": 0.45, "Linguist": 0.35, "QA": 0.20},
        "aggregation": "min_gated_mean",
        "gate_threshold": 3.5,
    },
    "Ops": {
        "tier1_agents": ["DeveloperDevOps", "DevOpsSRE", "FinanceAnalyst", "GrowthHacker"],
        "intra_weights": {
            "DeveloperDevOps": 0.25, "DevOpsSRE": 0.25,
            "FinanceAnalyst": 0.25, "GrowthHacker": 0.25,
        },
        "aggregation": "weighted_mean",
    },
}
```

### 5.4 HIERARCHICAL_TRUST

```python
# TO-BE
HIERARCHICAL_TRUST = {
    "CEO": {"Planner": 0.85, "PM": 0.85, "Ops": 0.82, "QALead": 0.80, "ComplianceOfficer": 0.90},
    "Planner": {"Researcher": 0.88, "DataScientist": 0.82, "MarketAnalyst": 0.80, "DataAnalyst": 0.85},
    "PM": {"TechLead": 0.88, "Developer": 0.85, "DeveloperFrontend": 0.82, "ProductDesigner": 0.85},
    "Ops": {"DeveloperDevOps": 0.85, "DevOpsSRE": 0.88, "FinanceAnalyst": 0.78, "GrowthHacker": 0.80},
    "QALead": {"SecuritySpecialist": 0.90, "Linguist": 0.82, "QA": 0.85},
}
```

---

## 6. 구현 순서 (작은 단위부터)

총 6개 Phase로, 각 Phase는 독립적으로 커밋 가능.

### Phase 1: 신규 YAML 페르소나 5개 추가 ⭐ 첫 번째

**작업**: 5개 YAML 파일 생성만. 코드 변경 없음.
**검증**: `PersonaRegistry.load_all()`에서 25개 로드 확인
**영향**: 없음 (기존 로직은 사용하지 않는 에이전트를 무시)

```
personas/data_analyst.yaml
personas/product_designer.yaml
personas/compliance_officer.yaml
personas/tech_lead.yaml
personas/growth_hacker.yaml
```

### Phase 2: UXVoiceDesigner → ProductDesigner 교체

**작업**:
- `personas/ux_voice_designer.yaml` 삭제
- 기존 코드에서 `UXVoiceDesigner` 참조를 `ProductDesigner`로 교체
- `config.py`: `TIER_2_DOMAIN_MAP["PM"]` 업데이트

**검증**: 기존 테스트 통과 + 24개 페르소나 로드

### Phase 3: team 필드 변경 (사일로 재편)

**작업**: 12개 YAML의 `team` 필드를 새 사일로명으로 변경
**검증**: `registry.get_team("strategy_analysis")` 등으로 사일로별 에이전트 확인

```
strategy → governance (CEO)
research → strategy_analysis (Planner, Researcher, DataScientist, ...)
product → product_realization (PM, Developer, DeveloperFrontend, ...)
engineering → growth_operations (Ops, DevOps, SRE, ...)
qa → quality_security (QALead, QA, SecuritySpecialist, Linguist)
```

### Phase 4: config.py 상수 업데이트

**작업**:
- `FLAT_MODE_AGENTS`: 9개로 확장
- `AGENT_FINAL_WEIGHTS`: 가중치 재분배
- `TIER_2_DOMAIN_MAP`: 새 사일로 구조 반영
- `HIERARCHICAL_TRUST`: 신규 에이전트 신뢰도 추가

**검증**: 기존 테스트 통과

### Phase 5: CEO 역할 축소 + ComplianceOfficer 게이트

**작업**:
- `pipeline.py`: CEO Tier 4 로직 → governance veto 로직으로 전환
- ComplianceOfficer를 규제 게이트로 추가 (QA 게이트와 병렬)

**검증**: 파이프라인 E2E 테스트

### Phase 6: 문서 업데이트 + 최종 검증

**작업**:
- `CLAUDE.md` 조직 구조 섹션 업데이트
- 전체 테스트 통과 확인

---

## 7. 챕터 메커니즘 (향후 Phase 7)

> Phase 1~6 완료 후 별도 작업으로 진행

챕터는 사일로 간 동일 직군 에이전트끼리의 **정보 공유 메커니즘**입니다.
현재 파이프라인에서는 각 에이전트가 독립적으로 scoring하므로,
챕터 도입은 deliberation 단계에서 **동일 직군 에이전트 간 의견 수렴 라운드**를
추가하는 방식으로 구현할 수 있습니다.

```
Developer Chapter 라운드:
  Developer(BE) + Developer(FE) + DevOps + TechLead
  → "구현 난이도" 합의 점수 생성

Research Chapter 라운드:
  Researcher + DataScientist + WebSearchAgent + SearchEvaluator
  → "학술 근거 충분성" 합의 점수 생성

Data Chapter 라운드:
  DataAnalyst + FinanceAnalyst + MarketAnalyst + GrowthHacker
  → "데이터 기반 실현성" 합의 점수 생성
```

이 합의 점수가 각 에이전트의 개별 scoring에 가중 반영됩니다.

---

## 부록 A: 의존성 그래프

```
Phase 1 (YAML 추가)
  └─> Phase 2 (UXVoiceDesigner 교체)
      └─> Phase 3 (team 필드 변경)
          └─> Phase 4 (config.py 상수)
              └─> Phase 5 (pipeline.py 로직)
                  └─> Phase 6 (문서 + 검증)
```

각 Phase는 이전 Phase가 완료된 후 진행합니다.
단, Phase 1은 코드 변경 없이 YAML 추가만이므로 즉시 시작 가능합니다.
