/**
 * Organization templates for quick onboarding.
 * Based on Toss-style silo + chapter structure.
 */

export interface OrgTemplateAgent {
  agent_id: string
  display_name: string
  display_name_ko: string
  role: string
  tier: number
  silo: string       // silo name (empty string for C-Level)
  chapter: string    // chapter name (empty string for no chapter)
  is_clevel: boolean
  team: string
  weights: Record<string, number>
}

export interface OrgTemplateSilo {
  name: string
  description: string
  color: string
}

export interface OrgTemplateChapter {
  name: string
  description: string
  icon: string
  color: string
  shared_directives: string[]
}

export interface OrgTemplate {
  id: string
  name: string
  name_ko: string
  icon: string
  description: string
  description_ko: string
  silos: OrgTemplateSilo[]
  chapters: OrgTemplateChapter[]
  agents: OrgTemplateAgent[]
}

// ============================================================================
// TOSS TEMPLATE - Full 24 agents, 5 silos, 8 chapters
// ============================================================================
const TOSS_SILOS: OrgTemplateSilo[] = [
  { name: '전략기획', description: '토픽 발굴, 시장·학술 근거 수집, 전략 방향 제안', color: '#ec4899' },
  { name: '프로덕트', description: '실현 가능성 평가, PoC 설계, UX 검증, 아키텍처 결정', color: '#8b5cf6' },
  { name: '플랫폼', description: '배포 전략, 비용 분석, 인프라 실현성, 성장 지표', color: '#3b82f6' },
  { name: '품질보증', description: '리스크 평가, 보안 검증, 품질 게이트, 프롬프트 품질', color: '#10b981' },
  { name: '리서치', description: '학술 연구, 시장 분석, 데이터 기반 인사이트', color: '#06b6d4' },
]

const TOSS_CHAPTERS: OrgTemplateChapter[] = [
  {
    name: 'Engineering',
    description: '개발 구현 및 아키텍처 설계',
    icon: '📐',
    color: '#3b82f6',
    shared_directives: ['코드 품질과 유지보수성을 최우선으로 평가', '기술 부채 최소화'],
  },
  {
    name: 'Security',
    description: '보안 및 규제 준수',
    icon: '🔒',
    color: '#ef4444',
    shared_directives: ['OWASP Top 10 기준 평가', '개인정보보호법 준수 검토'],
  },
  {
    name: 'Research',
    description: '학술 연구 및 근거 수집',
    icon: '🔬',
    color: '#06b6d4',
    shared_directives: ['최신 논문 및 컨퍼런스 동향 반영', '인용 신뢰도 기반 근거 평가'],
  },
  {
    name: 'Product',
    description: '제품 기획 및 UX 설계',
    icon: '📦',
    color: '#8b5cf6',
    shared_directives: ['사용자 중심 설계 원칙 적용', '디자인 시스템 일관성 유지'],
  },
  {
    name: 'Data',
    description: '데이터 분석 및 지표 관리',
    icon: '📊',
    color: '#f59e0b',
    shared_directives: ['정량적 지표 기반 의사결정', 'A/B 테스트 설계 가능성 평가'],
  },
  {
    name: 'QA',
    description: '품질 보증 및 테스트',
    icon: '🧪',
    color: '#10b981',
    shared_directives: ['테스트 커버리지 80% 이상 요구', '회귀 테스트 자동화'],
  },
  {
    name: 'Ops',
    description: '운영 및 인프라',
    icon: '⚙️',
    color: '#6b7280',
    shared_directives: ['SLO 99.9% 기준 평가', '비용 효율성 분석'],
  },
  {
    name: 'Strategy',
    description: '전략 기획 및 시장 분석',
    icon: '📋',
    color: '#ec4899',
    shared_directives: ['시장 규모 및 성장률 기반 평가', 'ROI 분석 필수'],
  },
]

const TOSS_AGENTS: OrgTemplateAgent[] = [
  // C-Level (Governance)
  {
    agent_id: 'CEO',
    display_name: 'CEO',
    display_name_ko: 'CEO',
    role: 'executive',
    tier: 4,
    silo: '',
    chapter: '',
    is_clevel: true,
    team: 'governance',
    weights: { impact: 0.30, feasibility: 0.20, novelty: 0.15, research_signal: 0.15, risk: 0.20 },
  },
  {
    agent_id: 'ComplianceOfficer',
    display_name: 'Compliance Officer',
    display_name_ko: '컴플라이언스 담당',
    role: 'compliance',
    tier: 3,
    silo: '',
    chapter: 'Security',
    is_clevel: true,
    team: 'governance',
    weights: { impact: 0.10, feasibility: 0.15, novelty: 0.05, research_signal: 0.10, risk: 0.60 },
  },
  // 전략기획 Silo
  {
    agent_id: 'Planner',
    display_name: 'Planner',
    display_name_ko: '전략 기획자',
    role: 'planner',
    tier: 2,
    silo: '전략기획',
    chapter: 'Strategy',
    is_clevel: false,
    team: 'strategy',
    weights: { impact: 0.30, feasibility: 0.25, novelty: 0.20, research_signal: 0.15, risk: -0.10 },
  },
  {
    agent_id: 'Researcher',
    display_name: 'Researcher',
    display_name_ko: '연구원',
    role: 'researcher',
    tier: 1,
    silo: '전략기획',
    chapter: 'Research',
    is_clevel: false,
    team: 'research',
    weights: { impact: 0.20, feasibility: 0.15, novelty: 0.35, research_signal: 0.25, risk: -0.05 },
  },
  {
    agent_id: 'DataScientist',
    display_name: 'Data Scientist',
    display_name_ko: '데이터 사이언티스트',
    role: 'data_scientist',
    tier: 1,
    silo: '전략기획',
    chapter: 'Data',
    is_clevel: false,
    team: 'research',
    weights: { impact: 0.25, feasibility: 0.20, novelty: 0.25, research_signal: 0.25, risk: -0.05 },
  },
  {
    agent_id: 'MarketAnalyst',
    display_name: 'Market Analyst',
    display_name_ko: '시장 분석가',
    role: 'market_analyst',
    tier: 1,
    silo: '전략기획',
    chapter: 'Strategy',
    is_clevel: false,
    team: 'strategy',
    weights: { impact: 0.35, feasibility: 0.20, novelty: 0.15, research_signal: 0.20, risk: -0.10 },
  },
  {
    agent_id: 'DataAnalyst',
    display_name: 'Data Analyst',
    display_name_ko: '데이터 분석가',
    role: 'data_analyst',
    tier: 1,
    silo: '전략기획',
    chapter: 'Data',
    is_clevel: false,
    team: 'strategy',
    weights: { impact: 0.35, feasibility: 0.25, novelty: 0.10, research_signal: 0.20, risk: -0.10 },
  },
  // 프로덕트 Silo
  {
    agent_id: 'PM',
    display_name: 'Product Manager',
    display_name_ko: '프로덕트 매니저',
    role: 'pm',
    tier: 2,
    silo: '프로덕트',
    chapter: 'Product',
    is_clevel: false,
    team: 'product',
    weights: { impact: 0.35, feasibility: 0.30, novelty: 0.15, research_signal: 0.10, risk: -0.10 },
  },
  {
    agent_id: 'TechLead',
    display_name: 'Tech Lead',
    display_name_ko: '테크 리드',
    role: 'tech_lead',
    tier: 1,
    silo: '프로덕트',
    chapter: 'Engineering',
    is_clevel: false,
    team: 'product',
    weights: { impact: 0.25, feasibility: 0.35, novelty: 0.15, research_signal: 0.10, risk: -0.15 },
  },
  {
    agent_id: 'Developer',
    display_name: 'Developer (BE)',
    display_name_ko: '백엔드 개발자',
    role: 'developer',
    tier: 1,
    silo: '프로덕트',
    chapter: 'Engineering',
    is_clevel: false,
    team: 'engineering',
    weights: { impact: 0.20, feasibility: 0.40, novelty: 0.15, research_signal: 0.10, risk: -0.15 },
  },
  {
    agent_id: 'DeveloperFrontend',
    display_name: 'Developer (FE)',
    display_name_ko: '프론트엔드 개발자',
    role: 'developer_frontend',
    tier: 1,
    silo: '프로덕트',
    chapter: 'Engineering',
    is_clevel: false,
    team: 'engineering',
    weights: { impact: 0.25, feasibility: 0.35, novelty: 0.20, research_signal: 0.10, risk: -0.10 },
  },
  {
    agent_id: 'ProductDesigner',
    display_name: 'Product Designer',
    display_name_ko: '프로덕트 디자이너',
    role: 'product_designer',
    tier: 1,
    silo: '프로덕트',
    chapter: 'Product',
    is_clevel: false,
    team: 'product',
    weights: { impact: 0.40, feasibility: 0.25, novelty: 0.15, research_signal: 0.10, risk: -0.10 },
  },
  // 플랫폼 Silo
  {
    agent_id: 'Ops',
    display_name: 'Operations Lead',
    display_name_ko: '운영 총괄',
    role: 'ops',
    tier: 2,
    silo: '플랫폼',
    chapter: 'Ops',
    is_clevel: false,
    team: 'platform',
    weights: { impact: 0.25, feasibility: 0.30, novelty: 0.10, research_signal: 0.10, risk: -0.25 },
  },
  {
    agent_id: 'DeveloperDevOps',
    display_name: 'DevOps Engineer',
    display_name_ko: 'DevOps 엔지니어',
    role: 'devops',
    tier: 1,
    silo: '플랫폼',
    chapter: 'Ops',
    is_clevel: false,
    team: 'platform',
    weights: { impact: 0.20, feasibility: 0.35, novelty: 0.15, research_signal: 0.10, risk: -0.20 },
  },
  {
    agent_id: 'DevOpsSRE',
    display_name: 'SRE',
    display_name_ko: 'SRE 엔지니어',
    role: 'sre',
    tier: 1,
    silo: '플랫폼',
    chapter: 'Ops',
    is_clevel: false,
    team: 'platform',
    weights: { impact: 0.20, feasibility: 0.30, novelty: 0.10, research_signal: 0.10, risk: -0.30 },
  },
  {
    agent_id: 'FinanceAnalyst',
    display_name: 'Finance Analyst',
    display_name_ko: '재무 분석가',
    role: 'finance_analyst',
    tier: 1,
    silo: '플랫폼',
    chapter: 'Strategy',
    is_clevel: false,
    team: 'platform',
    weights: { impact: 0.30, feasibility: 0.30, novelty: 0.05, research_signal: 0.10, risk: -0.25 },
  },
  {
    agent_id: 'GrowthHacker',
    display_name: 'Growth Hacker',
    display_name_ko: '그로스 해커',
    role: 'growth_hacker',
    tier: 1,
    silo: '플랫폼',
    chapter: 'Data',
    is_clevel: false,
    team: 'platform',
    weights: { impact: 0.40, feasibility: 0.20, novelty: 0.15, research_signal: 0.10, risk: -0.15 },
  },
  // 품질보증 Silo
  {
    agent_id: 'QALead',
    display_name: 'QA Lead',
    display_name_ko: 'QA 리드',
    role: 'qa_lead',
    tier: 2,
    silo: '품질보증',
    chapter: 'QA',
    is_clevel: false,
    team: 'qa',
    weights: { impact: 0.15, feasibility: 0.25, novelty: 0.10, research_signal: 0.10, risk: -0.40 },
  },
  {
    agent_id: 'QA',
    display_name: 'QA Engineer',
    display_name_ko: 'QA 엔지니어',
    role: 'qa',
    tier: 1,
    silo: '품질보증',
    chapter: 'QA',
    is_clevel: false,
    team: 'qa',
    weights: { impact: 0.15, feasibility: 0.30, novelty: 0.10, research_signal: 0.10, risk: -0.35 },
  },
  {
    agent_id: 'SecuritySpecialist',
    display_name: 'Security Specialist',
    display_name_ko: '보안 전문가',
    role: 'security',
    tier: 1,
    silo: '품질보증',
    chapter: 'Security',
    is_clevel: false,
    team: 'qa',
    weights: { impact: 0.10, feasibility: 0.20, novelty: 0.10, research_signal: 0.10, risk: -0.50 },
  },
  {
    agent_id: 'Linguist',
    display_name: 'Linguist',
    display_name_ko: '언어학자',
    role: 'linguist',
    tier: 1,
    silo: '품질보증',
    chapter: 'QA',
    is_clevel: false,
    team: 'qa',
    weights: { impact: 0.20, feasibility: 0.25, novelty: 0.25, research_signal: 0.20, risk: -0.10 },
  },
  // 리서치 Silo (Research specialists)
  {
    agent_id: 'WebSearchAgent',
    display_name: 'Web Search Agent',
    display_name_ko: '웹 검색 에이전트',
    role: 'web_search',
    tier: 1,
    silo: '리서치',
    chapter: 'Research',
    is_clevel: false,
    team: 'research',
    weights: { impact: 0.15, feasibility: 0.30, novelty: 0.20, research_signal: 0.30, risk: -0.05 },
  },
  {
    agent_id: 'SearchEvaluator',
    display_name: 'Search Evaluator',
    display_name_ko: '검색 품질 평가자',
    role: 'search_evaluator',
    tier: 1,
    silo: '리서치',
    chapter: 'Research',
    is_clevel: false,
    team: 'research',
    weights: { impact: 0.15, feasibility: 0.25, novelty: 0.20, research_signal: 0.35, risk: -0.05 },
  },
]

// ============================================================================
// RESEARCH LAB TEMPLATE - Smaller team focused on research
// ============================================================================
const RESEARCH_SILOS: OrgTemplateSilo[] = [
  { name: '연구팀', description: '학술 연구 및 시장 분석', color: '#06b6d4' },
  { name: '실행팀', description: 'PoC 구현 및 검증', color: '#8b5cf6' },
]

const RESEARCH_CHAPTERS: OrgTemplateChapter[] = [
  {
    name: 'Research',
    description: '학술 연구 및 논문 분석',
    icon: '🔬',
    color: '#06b6d4',
    shared_directives: ['최신 연구 동향 파악', 'peer-reviewed 논문 우선'],
  },
  {
    name: 'Engineering',
    description: 'PoC 개발 및 검증',
    icon: '📐',
    color: '#3b82f6',
    shared_directives: ['빠른 프로토타이핑', '재현 가능한 실험 설계'],
  },
  {
    name: 'Analysis',
    description: '데이터 분석 및 인사이트',
    icon: '📊',
    color: '#f59e0b',
    shared_directives: ['정량적 근거 기반 평가', '통계적 유의성 검증'],
  },
]

const RESEARCH_AGENTS: OrgTemplateAgent[] = [
  {
    agent_id: 'ResearchLead',
    display_name: 'Research Lead',
    display_name_ko: '연구 총괄',
    role: 'research_lead',
    tier: 3,
    silo: '',
    chapter: '',
    is_clevel: true,
    team: 'leadership',
    weights: { impact: 0.25, feasibility: 0.20, novelty: 0.30, research_signal: 0.20, risk: -0.05 },
  },
  {
    agent_id: 'Researcher',
    display_name: 'Researcher',
    display_name_ko: '연구원',
    role: 'researcher',
    tier: 2,
    silo: '연구팀',
    chapter: 'Research',
    is_clevel: false,
    team: 'research',
    weights: { impact: 0.20, feasibility: 0.15, novelty: 0.35, research_signal: 0.25, risk: -0.05 },
  },
  {
    agent_id: 'DataScientist',
    display_name: 'Data Scientist',
    display_name_ko: '데이터 사이언티스트',
    role: 'data_scientist',
    tier: 1,
    silo: '연구팀',
    chapter: 'Analysis',
    is_clevel: false,
    team: 'research',
    weights: { impact: 0.25, feasibility: 0.20, novelty: 0.25, research_signal: 0.25, risk: -0.05 },
  },
  {
    agent_id: 'MarketAnalyst',
    display_name: 'Market Analyst',
    display_name_ko: '시장 분석가',
    role: 'market_analyst',
    tier: 1,
    silo: '연구팀',
    chapter: 'Analysis',
    is_clevel: false,
    team: 'research',
    weights: { impact: 0.35, feasibility: 0.20, novelty: 0.15, research_signal: 0.20, risk: -0.10 },
  },
  {
    agent_id: 'TechLead',
    display_name: 'Tech Lead',
    display_name_ko: '테크 리드',
    role: 'tech_lead',
    tier: 2,
    silo: '실행팀',
    chapter: 'Engineering',
    is_clevel: false,
    team: 'engineering',
    weights: { impact: 0.25, feasibility: 0.35, novelty: 0.15, research_signal: 0.10, risk: -0.15 },
  },
  {
    agent_id: 'Developer',
    display_name: 'Developer',
    display_name_ko: '개발자',
    role: 'developer',
    tier: 1,
    silo: '실행팀',
    chapter: 'Engineering',
    is_clevel: false,
    team: 'engineering',
    weights: { impact: 0.20, feasibility: 0.40, novelty: 0.15, research_signal: 0.10, risk: -0.15 },
  },
  {
    agent_id: 'DataAnalyst',
    display_name: 'Data Analyst',
    display_name_ko: '데이터 분석가',
    role: 'data_analyst',
    tier: 1,
    silo: '실행팀',
    chapter: 'Analysis',
    is_clevel: false,
    team: 'research',
    weights: { impact: 0.35, feasibility: 0.25, novelty: 0.10, research_signal: 0.20, risk: -0.10 },
  },
  {
    agent_id: 'QA',
    display_name: 'QA Engineer',
    display_name_ko: 'QA 엔지니어',
    role: 'qa',
    tier: 1,
    silo: '실행팀',
    chapter: 'Engineering',
    is_clevel: false,
    team: 'qa',
    weights: { impact: 0.15, feasibility: 0.30, novelty: 0.10, research_signal: 0.10, risk: -0.35 },
  },
]

// ============================================================================
// SECURITY TEAM TEMPLATE - Security-focused organization
// ============================================================================
const SECURITY_SILOS: OrgTemplateSilo[] = [
  { name: '보안분석', description: '보안 위협 분석 및 취약점 평가', color: '#ef4444' },
]

const SECURITY_CHAPTERS: OrgTemplateChapter[] = [
  {
    name: 'Security',
    description: '보안 분석 및 대응',
    icon: '🔒',
    color: '#ef4444',
    shared_directives: ['OWASP Top 10 기준 평가', 'CVE 데이터베이스 참조'],
  },
  {
    name: 'Compliance',
    description: '규제 준수 및 감사',
    icon: '📋',
    color: '#f59e0b',
    shared_directives: ['ISMS, ISO27001 기준 평가', '개인정보보호법 준수'],
  },
]

const SECURITY_AGENTS: OrgTemplateAgent[] = [
  {
    agent_id: 'CISO',
    display_name: 'CISO',
    display_name_ko: '보안 총괄 책임자',
    role: 'ciso',
    tier: 3,
    silo: '',
    chapter: '',
    is_clevel: true,
    team: 'leadership',
    weights: { impact: 0.15, feasibility: 0.15, novelty: 0.05, research_signal: 0.10, risk: 0.55 },
  },
  {
    agent_id: 'SecuritySpecialist',
    display_name: 'Security Specialist',
    display_name_ko: '보안 전문가',
    role: 'security',
    tier: 2,
    silo: '보안분석',
    chapter: 'Security',
    is_clevel: false,
    team: 'security',
    weights: { impact: 0.10, feasibility: 0.20, novelty: 0.10, research_signal: 0.10, risk: -0.50 },
  },
  {
    agent_id: 'PentestEngineer',
    display_name: 'Pentest Engineer',
    display_name_ko: '모의해킹 엔지니어',
    role: 'pentest',
    tier: 1,
    silo: '보안분석',
    chapter: 'Security',
    is_clevel: false,
    team: 'security',
    weights: { impact: 0.15, feasibility: 0.25, novelty: 0.15, research_signal: 0.15, risk: -0.30 },
  },
  {
    agent_id: 'ThreatAnalyst',
    display_name: 'Threat Analyst',
    display_name_ko: '위협 분석가',
    role: 'threat_analyst',
    tier: 1,
    silo: '보안분석',
    chapter: 'Security',
    is_clevel: false,
    team: 'security',
    weights: { impact: 0.20, feasibility: 0.20, novelty: 0.20, research_signal: 0.25, risk: -0.15 },
  },
  {
    agent_id: 'ComplianceOfficer',
    display_name: 'Compliance Officer',
    display_name_ko: '컴플라이언스 담당',
    role: 'compliance',
    tier: 2,
    silo: '보안분석',
    chapter: 'Compliance',
    is_clevel: false,
    team: 'compliance',
    weights: { impact: 0.10, feasibility: 0.15, novelty: 0.05, research_signal: 0.10, risk: 0.60 },
  },
  {
    agent_id: 'SecurityOps',
    display_name: 'Security Ops',
    display_name_ko: '보안 운영',
    role: 'secops',
    tier: 1,
    silo: '보안분석',
    chapter: 'Security',
    is_clevel: false,
    team: 'security',
    weights: { impact: 0.15, feasibility: 0.30, novelty: 0.10, research_signal: 0.10, risk: -0.35 },
  },
]

// ============================================================================
// EMPTY TEMPLATE - Start from scratch
// ============================================================================
const EMPTY_SILOS: OrgTemplateSilo[] = []
const EMPTY_CHAPTERS: OrgTemplateChapter[] = []
const EMPTY_AGENTS: OrgTemplateAgent[] = []

// ============================================================================
// EXPORTED TEMPLATES
// ============================================================================
export const ORG_TEMPLATES: OrgTemplate[] = [
  {
    id: 'toss',
    name: 'Toss Structure',
    name_ko: 'Toss 구조',
    icon: '🏛️',
    description: 'Toss-style silo + chapter organization (23 agents, 5 silos, 8 chapters)',
    description_ko: '토스 스타일 사일로 + 챕터 조직 (23 에이전트, 5 사일로, 8 챕터)',
    silos: TOSS_SILOS,
    chapters: TOSS_CHAPTERS,
    agents: TOSS_AGENTS,
  },
  {
    id: 'research',
    name: 'Research Lab',
    name_ko: '리서치 랩',
    icon: '🔬',
    description: 'Research-focused small team (8 agents, 2 silos, 3 chapters)',
    description_ko: '연구 중심 소규모 팀 (8 에이전트, 2 사일로, 3 챕터)',
    silos: RESEARCH_SILOS,
    chapters: RESEARCH_CHAPTERS,
    agents: RESEARCH_AGENTS,
  },
  {
    id: 'security',
    name: 'Security Team',
    name_ko: '보안팀',
    icon: '🛡️',
    description: 'Security-focused team (6 agents, 1 silo, 2 chapters)',
    description_ko: '보안 특화 팀 (6 에이전트, 1 사일로, 2 챕터)',
    silos: SECURITY_SILOS,
    chapters: SECURITY_CHAPTERS,
    agents: SECURITY_AGENTS,
  },
  {
    id: 'empty',
    name: 'Empty',
    name_ko: '빈 조직',
    icon: '📄',
    description: 'Start from scratch',
    description_ko: '처음부터 직접 구성',
    silos: EMPTY_SILOS,
    chapters: EMPTY_CHAPTERS,
    agents: EMPTY_AGENTS,
  },
]

export function getTemplateById(id: string): OrgTemplate | undefined {
  return ORG_TEMPLATES.find(t => t.id === id)
}
