"""Organization templates for quick onboarding.

Based on Toss-style silo + chapter structure.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TemplateAgent:
    agent_id: str
    display_name: str
    display_name_ko: str
    role: str
    tier: int
    silo: str  # silo name (empty for C-Level)
    chapter: str  # chapter name (empty for no chapter)
    is_clevel: bool
    team: str
    weights: dict[str, float] = field(default_factory=dict)


@dataclass
class TemplateSilo:
    name: str
    description: str
    color: str


@dataclass
class TemplateChapter:
    name: str
    description: str
    icon: str
    color: str
    shared_directives: list[str] = field(default_factory=list)


@dataclass
class OrgTemplate:
    id: str
    name: str
    name_ko: str
    icon: str
    description: str
    silos: list[TemplateSilo]
    chapters: list[TemplateChapter]
    agents: list[TemplateAgent]


# ============================================================================
# TOSS TEMPLATE - Full 24 agents, 5 silos, 8 chapters
# ============================================================================
TOSS_SILOS = [
    TemplateSilo("전략기획", "토픽 발굴, 시장·학술 근거 수집, 전략 방향 제안", "#ec4899"),
    TemplateSilo("프로덕트", "실현 가능성 평가, PoC 설계, UX 검증, 아키텍처 결정", "#8b5cf6"),
    TemplateSilo("플랫폼", "배포 전략, 비용 분석, 인프라 실현성, 성장 지표", "#3b82f6"),
    TemplateSilo("품질보증", "리스크 평가, 보안 검증, 품질 게이트, 프롬프트 품질", "#10b981"),
    TemplateSilo("리서치", "학술 연구, 시장 분석, 데이터 기반 인사이트", "#06b6d4"),
]

TOSS_CHAPTERS = [
    TemplateChapter("Engineering", "개발 구현 및 아키텍처 설계", "📐", "#3b82f6",
                    ["코드 품질과 유지보수성을 최우선으로 평가", "기술 부채 최소화"]),
    TemplateChapter("Security", "보안 및 규제 준수", "🔒", "#ef4444",
                    ["OWASP Top 10 기준 평가", "개인정보보호법 준수 검토"]),
    TemplateChapter("Research", "학술 연구 및 근거 수집", "🔬", "#06b6d4",
                    ["최신 논문 및 컨퍼런스 동향 반영", "인용 신뢰도 기반 근거 평가"]),
    TemplateChapter("Product", "제품 기획 및 UX 설계", "📦", "#8b5cf6",
                    ["사용자 중심 설계 원칙 적용", "디자인 시스템 일관성 유지"]),
    TemplateChapter("Data", "데이터 분석 및 지표 관리", "📊", "#f59e0b",
                    ["정량적 지표 기반 의사결정", "A/B 테스트 설계 가능성 평가"]),
    TemplateChapter("QA", "품질 보증 및 테스트", "🧪", "#10b981",
                    ["테스트 커버리지 80% 이상 요구", "회귀 테스트 자동화"]),
    TemplateChapter("Ops", "운영 및 인프라", "⚙️", "#6b7280",
                    ["SLO 99.9% 기준 평가", "비용 효율성 분석"]),
    TemplateChapter("Strategy", "전략 기획 및 시장 분석", "📋", "#ec4899",
                    ["시장 규모 및 성장률 기반 평가", "ROI 분석 필수"]),
]

TOSS_AGENTS = [
    # C-Level (Governance)
    TemplateAgent("CEO", "CEO", "CEO", "executive", 4, "", "", True, "governance",
                  {"impact": 0.30, "feasibility": 0.20, "novelty": 0.15, "research_signal": 0.15, "risk": 0.20}),
    TemplateAgent("ComplianceOfficer", "Compliance Officer", "컴플라이언스 담당", "compliance", 3, "", "Security", True, "governance",
                  {"impact": 0.10, "feasibility": 0.15, "novelty": 0.05, "research_signal": 0.10, "risk": 0.60}),
    # 전략기획 Silo
    TemplateAgent("Planner", "Planner", "전략 기획자", "planner", 2, "전략기획", "Strategy", False, "strategy",
                  {"impact": 0.30, "feasibility": 0.25, "novelty": 0.20, "research_signal": 0.15, "risk": -0.10}),
    TemplateAgent("Researcher", "Researcher", "연구원", "researcher", 1, "전략기획", "Research", False, "research",
                  {"impact": 0.20, "feasibility": 0.15, "novelty": 0.35, "research_signal": 0.25, "risk": -0.05}),
    TemplateAgent("DataScientist", "Data Scientist", "데이터 사이언티스트", "data_scientist", 1, "전략기획", "Data", False, "research",
                  {"impact": 0.25, "feasibility": 0.20, "novelty": 0.25, "research_signal": 0.25, "risk": -0.05}),
    TemplateAgent("MarketAnalyst", "Market Analyst", "시장 분석가", "market_analyst", 1, "전략기획", "Strategy", False, "strategy",
                  {"impact": 0.35, "feasibility": 0.20, "novelty": 0.15, "research_signal": 0.20, "risk": -0.10}),
    TemplateAgent("DataAnalyst", "Data Analyst", "데이터 분석가", "data_analyst", 1, "전략기획", "Data", False, "strategy",
                  {"impact": 0.35, "feasibility": 0.25, "novelty": 0.10, "research_signal": 0.20, "risk": -0.10}),
    # 프로덕트 Silo
    TemplateAgent("PM", "Product Manager", "프로덕트 매니저", "pm", 2, "프로덕트", "Product", False, "product",
                  {"impact": 0.35, "feasibility": 0.30, "novelty": 0.15, "research_signal": 0.10, "risk": -0.10}),
    TemplateAgent("TechLead", "Tech Lead", "테크 리드", "tech_lead", 1, "프로덕트", "Engineering", False, "product",
                  {"impact": 0.25, "feasibility": 0.35, "novelty": 0.15, "research_signal": 0.10, "risk": -0.15}),
    TemplateAgent("Developer", "Developer (BE)", "백엔드 개발자", "developer", 1, "프로덕트", "Engineering", False, "engineering",
                  {"impact": 0.20, "feasibility": 0.40, "novelty": 0.15, "research_signal": 0.10, "risk": -0.15}),
    TemplateAgent("DeveloperFrontend", "Developer (FE)", "프론트엔드 개발자", "developer_frontend", 1, "프로덕트", "Engineering", False, "engineering",
                  {"impact": 0.25, "feasibility": 0.35, "novelty": 0.20, "research_signal": 0.10, "risk": -0.10}),
    TemplateAgent("ProductDesigner", "Product Designer", "프로덕트 디자이너", "product_designer", 1, "프로덕트", "Product", False, "product",
                  {"impact": 0.40, "feasibility": 0.25, "novelty": 0.15, "research_signal": 0.10, "risk": -0.10}),
    # 플랫폼 Silo
    TemplateAgent("Ops", "Operations Lead", "운영 총괄", "ops", 2, "플랫폼", "Ops", False, "platform",
                  {"impact": 0.25, "feasibility": 0.30, "novelty": 0.10, "research_signal": 0.10, "risk": -0.25}),
    TemplateAgent("DeveloperDevOps", "DevOps Engineer", "DevOps 엔지니어", "devops", 1, "플랫폼", "Ops", False, "platform",
                  {"impact": 0.20, "feasibility": 0.35, "novelty": 0.15, "research_signal": 0.10, "risk": -0.20}),
    TemplateAgent("DevOpsSRE", "SRE", "SRE 엔지니어", "sre", 1, "플랫폼", "Ops", False, "platform",
                  {"impact": 0.20, "feasibility": 0.30, "novelty": 0.10, "research_signal": 0.10, "risk": -0.30}),
    TemplateAgent("FinanceAnalyst", "Finance Analyst", "재무 분석가", "finance_analyst", 1, "플랫폼", "Strategy", False, "platform",
                  {"impact": 0.30, "feasibility": 0.30, "novelty": 0.05, "research_signal": 0.10, "risk": -0.25}),
    TemplateAgent("GrowthHacker", "Growth Hacker", "그로스 해커", "growth_hacker", 1, "플랫폼", "Data", False, "platform",
                  {"impact": 0.40, "feasibility": 0.20, "novelty": 0.15, "research_signal": 0.10, "risk": -0.15}),
    # 품질보증 Silo
    TemplateAgent("QALead", "QA Lead", "QA 리드", "qa_lead", 2, "품질보증", "QA", False, "qa",
                  {"impact": 0.15, "feasibility": 0.25, "novelty": 0.10, "research_signal": 0.10, "risk": -0.40}),
    TemplateAgent("QA", "QA Engineer", "QA 엔지니어", "qa", 1, "품질보증", "QA", False, "qa",
                  {"impact": 0.15, "feasibility": 0.30, "novelty": 0.10, "research_signal": 0.10, "risk": -0.35}),
    TemplateAgent("SecuritySpecialist", "Security Specialist", "보안 전문가", "security", 1, "품질보증", "Security", False, "qa",
                  {"impact": 0.10, "feasibility": 0.20, "novelty": 0.10, "research_signal": 0.10, "risk": -0.50}),
    TemplateAgent("Linguist", "Linguist", "언어학자", "linguist", 1, "품질보증", "QA", False, "qa",
                  {"impact": 0.20, "feasibility": 0.25, "novelty": 0.25, "research_signal": 0.20, "risk": -0.10}),
    # 리서치 Silo
    TemplateAgent("WebSearchAgent", "Web Search Agent", "웹 검색 에이전트", "web_search", 1, "리서치", "Research", False, "research",
                  {"impact": 0.15, "feasibility": 0.30, "novelty": 0.20, "research_signal": 0.30, "risk": -0.05}),
    TemplateAgent("SearchEvaluator", "Search Evaluator", "검색 품질 평가자", "search_evaluator", 1, "리서치", "Research", False, "research",
                  {"impact": 0.15, "feasibility": 0.25, "novelty": 0.20, "research_signal": 0.35, "risk": -0.05}),
]

# ============================================================================
# RESEARCH LAB TEMPLATE - Smaller team focused on research
# ============================================================================
RESEARCH_SILOS = [
    TemplateSilo("연구팀", "학술 연구 및 시장 분석", "#06b6d4"),
    TemplateSilo("실행팀", "PoC 구현 및 검증", "#8b5cf6"),
]

RESEARCH_CHAPTERS = [
    TemplateChapter("Research", "학술 연구 및 논문 분석", "🔬", "#06b6d4",
                    ["최신 연구 동향 파악", "peer-reviewed 논문 우선"]),
    TemplateChapter("Engineering", "PoC 개발 및 검증", "📐", "#3b82f6",
                    ["빠른 프로토타이핑", "재현 가능한 실험 설계"]),
    TemplateChapter("Analysis", "데이터 분석 및 인사이트", "📊", "#f59e0b",
                    ["정량적 근거 기반 평가", "통계적 유의성 검증"]),
]

RESEARCH_AGENTS = [
    TemplateAgent("ResearchLead", "Research Lead", "연구 총괄", "research_lead", 3, "", "", True, "leadership",
                  {"impact": 0.25, "feasibility": 0.20, "novelty": 0.30, "research_signal": 0.20, "risk": -0.05}),
    TemplateAgent("Researcher", "Researcher", "연구원", "researcher", 2, "연구팀", "Research", False, "research",
                  {"impact": 0.20, "feasibility": 0.15, "novelty": 0.35, "research_signal": 0.25, "risk": -0.05}),
    TemplateAgent("DataScientist", "Data Scientist", "데이터 사이언티스트", "data_scientist", 1, "연구팀", "Analysis", False, "research",
                  {"impact": 0.25, "feasibility": 0.20, "novelty": 0.25, "research_signal": 0.25, "risk": -0.05}),
    TemplateAgent("MarketAnalyst", "Market Analyst", "시장 분석가", "market_analyst", 1, "연구팀", "Analysis", False, "research",
                  {"impact": 0.35, "feasibility": 0.20, "novelty": 0.15, "research_signal": 0.20, "risk": -0.10}),
    TemplateAgent("TechLead", "Tech Lead", "테크 리드", "tech_lead", 2, "실행팀", "Engineering", False, "engineering",
                  {"impact": 0.25, "feasibility": 0.35, "novelty": 0.15, "research_signal": 0.10, "risk": -0.15}),
    TemplateAgent("Developer", "Developer", "개발자", "developer", 1, "실행팀", "Engineering", False, "engineering",
                  {"impact": 0.20, "feasibility": 0.40, "novelty": 0.15, "research_signal": 0.10, "risk": -0.15}),
    TemplateAgent("DataAnalyst", "Data Analyst", "데이터 분석가", "data_analyst", 1, "실행팀", "Analysis", False, "research",
                  {"impact": 0.35, "feasibility": 0.25, "novelty": 0.10, "research_signal": 0.20, "risk": -0.10}),
    TemplateAgent("QA", "QA Engineer", "QA 엔지니어", "qa", 1, "실행팀", "Engineering", False, "qa",
                  {"impact": 0.15, "feasibility": 0.30, "novelty": 0.10, "research_signal": 0.10, "risk": -0.35}),
]

# ============================================================================
# SECURITY TEAM TEMPLATE - Security-focused organization
# ============================================================================
SECURITY_SILOS = [
    TemplateSilo("보안분석", "보안 위협 분석 및 취약점 평가", "#ef4444"),
]

SECURITY_CHAPTERS = [
    TemplateChapter("Security", "보안 분석 및 대응", "🔒", "#ef4444",
                    ["OWASP Top 10 기준 평가", "CVE 데이터베이스 참조"]),
    TemplateChapter("Compliance", "규제 준수 및 감사", "📋", "#f59e0b",
                    ["ISMS, ISO27001 기준 평가", "개인정보보호법 준수"]),
]

SECURITY_AGENTS = [
    TemplateAgent("CISO", "CISO", "보안 총괄 책임자", "ciso", 3, "", "", True, "leadership",
                  {"impact": 0.15, "feasibility": 0.15, "novelty": 0.05, "research_signal": 0.10, "risk": 0.55}),
    TemplateAgent("SecuritySpecialist", "Security Specialist", "보안 전문가", "security", 2, "보안분석", "Security", False, "security",
                  {"impact": 0.10, "feasibility": 0.20, "novelty": 0.10, "research_signal": 0.10, "risk": -0.50}),
    TemplateAgent("PentestEngineer", "Pentest Engineer", "모의해킹 엔지니어", "pentest", 1, "보안분석", "Security", False, "security",
                  {"impact": 0.15, "feasibility": 0.25, "novelty": 0.15, "research_signal": 0.15, "risk": -0.30}),
    TemplateAgent("ThreatAnalyst", "Threat Analyst", "위협 분석가", "threat_analyst", 1, "보안분석", "Security", False, "security",
                  {"impact": 0.20, "feasibility": 0.20, "novelty": 0.20, "research_signal": 0.25, "risk": -0.15}),
    TemplateAgent("ComplianceOfficer", "Compliance Officer", "컴플라이언스 담당", "compliance", 2, "보안분석", "Compliance", False, "compliance",
                  {"impact": 0.10, "feasibility": 0.15, "novelty": 0.05, "research_signal": 0.10, "risk": 0.60}),
    TemplateAgent("SecurityOps", "Security Ops", "보안 운영", "secops", 1, "보안분석", "Security", False, "security",
                  {"impact": 0.15, "feasibility": 0.30, "novelty": 0.10, "research_signal": 0.10, "risk": -0.35}),
]

# ============================================================================
# EMPTY TEMPLATE
# ============================================================================
EMPTY_SILOS: list[TemplateSilo] = []
EMPTY_CHAPTERS: list[TemplateChapter] = []
EMPTY_AGENTS: list[TemplateAgent] = []

# ============================================================================
# TEMPLATE REGISTRY
# ============================================================================
ORG_TEMPLATES: dict[str, OrgTemplate] = {
    "toss": OrgTemplate(
        id="toss",
        name="Toss Structure",
        name_ko="Toss 구조",
        icon="🏛️",
        description="Toss-style silo + chapter organization (23 agents, 5 silos, 8 chapters)",
        silos=TOSS_SILOS,
        chapters=TOSS_CHAPTERS,
        agents=TOSS_AGENTS,
    ),
    "research": OrgTemplate(
        id="research",
        name="Research Lab",
        name_ko="리서치 랩",
        icon="🔬",
        description="Research-focused small team (8 agents, 2 silos, 3 chapters)",
        silos=RESEARCH_SILOS,
        chapters=RESEARCH_CHAPTERS,
        agents=RESEARCH_AGENTS,
    ),
    "security": OrgTemplate(
        id="security",
        name="Security Team",
        name_ko="보안팀",
        icon="🛡️",
        description="Security-focused team (6 agents, 1 silo, 2 chapters)",
        silos=SECURITY_SILOS,
        chapters=SECURITY_CHAPTERS,
        agents=SECURITY_AGENTS,
    ),
    "empty": OrgTemplate(
        id="empty",
        name="Empty",
        name_ko="빈 조직",
        icon="📄",
        description="Start from scratch",
        silos=EMPTY_SILOS,
        chapters=EMPTY_CHAPTERS,
        agents=EMPTY_AGENTS,
    ),
}


def get_template(template_id: str | None) -> OrgTemplate | None:
    """Get a template by ID. Returns None if not found or template_id is None."""
    if not template_id:
        return None
    return ORG_TEMPLATES.get(template_id)
