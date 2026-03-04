export interface ChatPlan {
  target: string
  env: Record<string, string>
}

export interface ChatResponse {
  reply: string
  plan: ChatPlan | null
  run_id: string | null
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
  runId?: string | null
  timestamp: Date
}

export interface Conversation {
  id: string
  title: string
  messages: Message[]
  createdAt: Date
}
