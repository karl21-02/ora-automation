import type { ChatChoice, ChatPlan, ChatResponse, OrchestrationEvent, OrchestrationRun, ProjectInfo, ReportListItem, ScheduledJob, ScheduledJobCreate } from '../types'

const BASE = '/api/v1'

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  return res.json() as Promise<T>
}

export interface ChatHistoryMessage {
  role: 'user' | 'assistant'
  content: string
}

export async function sendChat(
  message: string,
  history: ChatHistoryMessage[] = [],
  conversationId?: string,
): Promise<ChatResponse> {
  return request<ChatResponse>(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history, conversation_id: conversationId }),
  })
}

export interface StreamEvent {
  type: 'token' | 'done' | 'error'
  content?: string
  full_reply?: string
  plan?: { target: string; env: Record<string, string>; label?: string } | null
  plans?: { target: string; env: Record<string, string>; label?: string }[] | null
  choices?: ChatChoice[] | null
  project_select?: ProjectInfo[] | null
  dialog_state?: string | null
  confirmation_required?: boolean
  intent_summary?: string | null
}

export async function sendChatStream(
  message: string,
  history: ChatHistoryMessage[] = [],
  conversationId?: string,
  onEvent: (event: StreamEvent) => void = () => {},
): Promise<void> {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history, conversation_id: conversationId }),
  })
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data: ')) continue
      const data = trimmed.slice(6)
      if (data === '[DONE]') return
      try {
        const event: StreamEvent = JSON.parse(data)
        onEvent(event)
      } catch {
        // skip malformed SSE data
      }
    }
  }
}

export async function listReports(): Promise<ReportListItem[]> {
  return request<ReportListItem[]>(`${BASE}/reports`)
}

export async function getReport(filename: string): Promise<string> {
  const res = await fetch(`${BASE}/reports/${encodeURIComponent(filename)}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.text()
}

export async function createRun(plan: ChatPlan, userPrompt: string): Promise<OrchestrationRun> {
  return request<OrchestrationRun>(`${BASE}/orchestrations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_prompt: userPrompt,
      target: plan.target,
      env: plan.env,
    }),
  })
}

export async function createBatchRuns(
  plans: ChatPlan[],
  userPrompt: string,
): Promise<{ runs: OrchestrationRun[] }> {
  return request<{ runs: OrchestrationRun[] }>(`${BASE}/orchestrations/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_prompt: userPrompt, plans }),
  })
}

export async function getRun(runId: string): Promise<OrchestrationRun> {
  return request<OrchestrationRun>(`${BASE}/orchestrations/${runId}`)
}

export async function getRunEvents(runId: string, limit = 50): Promise<OrchestrationEvent[]> {
  return request<OrchestrationEvent[]>(`${BASE}/orchestrations/${runId}/events?limit=${limit}`)
}

export async function listRuns(): Promise<{ items: OrchestrationRun[]; total: number }> {
  return request<{ items: OrchestrationRun[]; total: number }>(`${BASE}/orchestrations?limit=20`)
}

// ── Conversations ──────────────────────────────────────────────────

export interface ConversationSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ConversationDetail extends ConversationSummary {
  messages: {
    id: number
    conversation_id: string
    role: 'user' | 'assistant'
    content: string
    plan: Record<string, unknown> | null
    run_id: string | null
    created_at: string
  }[]
}

export async function listConversations(limit = 50): Promise<{ items: ConversationSummary[]; total: number }> {
  return request<{ items: ConversationSummary[]; total: number }>(`${BASE}/conversations?limit=${limit}`)
}

export async function createConversation(id?: string, title = ''): Promise<ConversationSummary> {
  return request<ConversationSummary>(`${BASE}/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, title }),
  })
}

export async function getConversation(conversationId: string): Promise<ConversationDetail> {
  return request<ConversationDetail>(`${BASE}/conversations/${conversationId}`)
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await fetch(`${BASE}/conversations/${conversationId}`, { method: 'DELETE' })
}

export async function renameConversation(id: string, title: string): Promise<ConversationSummary> {
  return request<ConversationSummary>(`${BASE}/conversations/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
}

// ── Projects ──────────────────────────────────────────────────────

export async function listProjects(): Promise<ProjectInfo[]> {
  return request<ProjectInfo[]>(`${BASE}/projects`)
}

// ── Scheduler ──────────────────────────────────────────────────────

export async function getScheduledJobs(): Promise<ScheduledJob[]> {
  return request<ScheduledJob[]>(`${BASE}/scheduler/jobs`)
}

export async function createScheduledJob(data: ScheduledJobCreate): Promise<ScheduledJob> {
  return request<ScheduledJob>(`${BASE}/scheduler/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function updateScheduledJob(id: string, data: Partial<ScheduledJobCreate>): Promise<ScheduledJob> {
  return request<ScheduledJob>(`${BASE}/scheduler/jobs/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function deleteScheduledJob(id: string): Promise<void> {
  await fetch(`${BASE}/scheduler/jobs/${id}`, { method: 'DELETE' })
}

export async function triggerScheduledJob(id: string): Promise<OrchestrationRun> {
  return request<OrchestrationRun>(`${BASE}/scheduler/jobs/${id}/run`, {
    method: 'POST',
  })
}
