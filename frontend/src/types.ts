export interface ChatPlan {
  target: string
  env: Record<string, string>
  label?: string
}

export interface ChatChoice {
  label: string
  description: string
  value: string
}

export interface ProjectInfo {
  name: string
  path: string
  has_makefile: boolean
  has_dockerfile: boolean
  description: string
}

export interface OrgRecommendOption {
  org_id: string
  org_name: string
  description: string
  score: number
  reason: string
  is_recommended: boolean
}

export type DialogState = 'idle' | 'understanding' | 'slot_filling' | 'confirming' | 'executing' | 'reporting'

export interface ChatResponse {
  reply: string
  plan: ChatPlan | null
  plans: ChatPlan[] | null
  choices: ChatChoice[] | null
  project_select: ProjectInfo[] | null
  run_id: string | null
  dialog_state: DialogState | null
  confirmation_required: boolean
  intent_summary: string | null
}

export interface ReportListItem {
  filename: string
  created_at: string
  size_bytes: number
  report_type: 'markdown' | 'json'
}

export interface OrchestrationRun {
  id: string
  user_prompt: string
  target: string
  agent_role: string
  status: string
  fail_label: string
  attempt_count: number
  max_attempts: number
  current_stage: string | null
  pause_requested: boolean
  cancel_requested: boolean
  pipeline_stages: string[] | null
  guest_agent_ids: string[]
  exit_code: number | null
  error_message: string | null
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
}

export interface OrchestrationEvent {
  id: number
  run_id: string
  stage: string
  event_type: string
  message: string
  payload: Record<string, unknown>
  created_at: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  plan?: ChatPlan | null
  plans?: ChatPlan[] | null
  choices?: ChatChoice[] | null
  projectSelect?: ProjectInfo[] | null
  orgRecommend?: OrgRecommendOption[] | null
  runId?: string | null
  dialogState?: DialogState | null
  confirmationRequired?: boolean | null
  intentSummary?: string | null
  timestamp: Date
}

export interface Conversation {
  id: string
  title: string
  messages: Message[]
  createdAt: Date
  orgId?: string | null
  orgName?: string | null
}

// ── Scheduler ──────────────────────────────────────────────────────

export interface ScheduledJob {
  id: string
  name: string
  description: string | null
  target: string
  env: Record<string, string>
  interval_minutes: number | null
  cron_expression: string | null
  enabled: boolean
  auto_publish_notion: boolean
  last_run_at: string | null
  last_run_status: string | null
  last_run_id: string | null
  next_run_at: string | null
  created_at: string
  updated_at: string
}

export interface ScheduledJobCreate {
  name: string
  description?: string
  target?: string
  env?: Record<string, string>
  interval_minutes?: number
  cron_expression?: string
  enabled?: boolean
  auto_publish_notion?: boolean
}

// ── Organizations ──────────────────────────────────────────────────

export interface OrgAgent {
  id: string
  org_id: string
  agent_id: string
  silo_id: string | null
  chapter_id: string | null
  is_clevel: boolean
  weight_score: number
  display_name: string
  display_name_ko: string
  role: string
  tier: number
  domain: string | null
  team: string
  personality: Record<string, string>
  behavioral_directives: string[]
  constraints: string[]
  decision_focus: string[]
  weights: Record<string, number>
  trust_map: Record<string, number>
  system_prompt_template: string | null
  enabled: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

export interface OrgSilo {
  id: string
  org_id: string
  name: string
  description: string | null
  color: string
  sort_order: number
  created_at: string
  updated_at: string
}

export interface OrgChapter {
  id: string
  org_id: string
  name: string
  description: string | null
  shared_directives: string[]
  shared_constraints: string[]
  shared_decision_focus: string[]
  chapter_prompt: string
  color: string
  icon: string
  sort_order: number
  created_at: string
  updated_at: string
}

export interface Organization {
  id: string
  name: string
  description: string | null
  is_preset: boolean
  teams: Record<string, string[]>
  flat_mode_agents: string[]
  agent_final_weights: Record<string, number>
  pipeline_params: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface OrganizationDetail extends Organization {
  agents: OrgAgent[]
  silos: OrgSilo[]
  chapters: OrgChapter[]
}
