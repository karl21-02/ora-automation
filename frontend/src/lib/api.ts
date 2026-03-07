import type { ChatChoice, ChatPlan, ChatResponse, OrgAgent, OrgChapter, OrgSilo, OrchestrationEvent, OrchestrationRun, Organization, OrganizationDetail, ProjectInfo, ReportListItem, ScheduledJob, ScheduledJobCreate } from '../types'

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
  orgId?: string | null,
): Promise<void> {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history, conversation_id: conversationId, org_id: orgId ?? undefined }),
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

export async function createRun(plan: ChatPlan, userPrompt: string, orgId?: string | null): Promise<OrchestrationRun> {
  return request<OrchestrationRun>(`${BASE}/orchestrations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_prompt: userPrompt,
      target: plan.target,
      env: plan.env,
      org_id: orgId ?? undefined,
    }),
  })
}

export async function createBatchRuns(
  plans: ChatPlan[],
  userPrompt: string,
  orgId?: string | null,
): Promise<{ runs: OrchestrationRun[] }> {
  return request<{ runs: OrchestrationRun[] }>(`${BASE}/orchestrations/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_prompt: userPrompt, plans, org_id: orgId ?? undefined }),
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
  org_id: string | null
  org_name: string | null
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

export async function createConversation(id?: string, title = '', orgId?: string | null): Promise<ConversationSummary> {
  return request<ConversationSummary>(`${BASE}/conversations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id, title, org_id: orgId ?? undefined }),
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

export async function updateConversationOrg(id: string, orgId: string | null): Promise<ConversationSummary> {
  return request<ConversationSummary>(`${BASE}/conversations/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ org_id: orgId ?? '' }),
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

// ── Organizations ──────────────────────────────────────────────────

export async function listOrgs(): Promise<{ items: Organization[]; total: number }> {
  return request<{ items: Organization[]; total: number }>(`${BASE}/orgs`)
}

export async function getOrg(orgId: string): Promise<OrganizationDetail> {
  return request<OrganizationDetail>(`${BASE}/orgs/${orgId}`)
}

export async function createOrg(data: {
  name: string
  description?: string
  teams?: Record<string, string[]>
  flat_mode_agents?: string[]
  agent_final_weights?: Record<string, number>
  pipeline_params?: Record<string, unknown>
}): Promise<OrganizationDetail> {
  return request<OrganizationDetail>(`${BASE}/orgs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function updateOrg(orgId: string, data: Partial<{
  name: string
  description: string
  teams: Record<string, string[]>
  flat_mode_agents: string[]
  agent_final_weights: Record<string, number>
  pipeline_params: Record<string, unknown>
}>): Promise<Organization> {
  return request<Organization>(`${BASE}/orgs/${orgId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function deleteOrg(orgId: string): Promise<void> {
  await fetch(`${BASE}/orgs/${orgId}`, { method: 'DELETE' })
}

export async function cloneOrg(orgId: string, data: {
  name: string
  description?: string
}): Promise<OrganizationDetail> {
  return request<OrganizationDetail>(`${BASE}/orgs/${orgId}/clone`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function createAgent(orgId: string, data: Omit<OrgAgent, 'id' | 'org_id' | 'created_at' | 'updated_at'>): Promise<OrgAgent> {
  return request<OrgAgent>(`${BASE}/orgs/${orgId}/agents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function updateAgent(orgId: string, agentId: string, data: Partial<OrgAgent>): Promise<OrgAgent> {
  return request<OrgAgent>(`${BASE}/orgs/${orgId}/agents/${agentId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function deleteAgent(orgId: string, agentId: string): Promise<void> {
  await fetch(`${BASE}/orgs/${orgId}/agents/${agentId}`, { method: 'DELETE' })
}

// ── Silos ──────────────────────────────────────────────────────

export async function createSilo(orgId: string, data: {
  name: string
  description?: string
  color?: string
  sort_order?: number
}): Promise<OrgSilo> {
  return request<OrgSilo>(`${BASE}/orgs/${orgId}/silos`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function updateSilo(orgId: string, siloId: string, data: Partial<{
  name: string
  description: string
  color: string
  sort_order: number
}>): Promise<OrgSilo> {
  return request<OrgSilo>(`${BASE}/orgs/${orgId}/silos/${siloId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function deleteSilo(orgId: string, siloId: string): Promise<void> {
  await fetch(`${BASE}/orgs/${orgId}/silos/${siloId}`, { method: 'DELETE' })
}

// ── Chapters ──────────────────────────────────────────────────────

export async function createChapter(orgId: string, data: {
  name: string
  description?: string
  shared_directives?: string[]
  shared_constraints?: string[]
  shared_decision_focus?: string[]
  chapter_prompt?: string
  color?: string
  icon?: string
  sort_order?: number
}): Promise<OrgChapter> {
  return request<OrgChapter>(`${BASE}/orgs/${orgId}/chapters`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function updateChapter(orgId: string, chapterId: string, data: Partial<{
  name: string
  description: string
  shared_directives: string[]
  shared_constraints: string[]
  shared_decision_focus: string[]
  chapter_prompt: string
  color: string
  icon: string
  sort_order: number
}>): Promise<OrgChapter> {
  return request<OrgChapter>(`${BASE}/orgs/${orgId}/chapters/${chapterId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function deleteChapter(orgId: string, chapterId: string): Promise<void> {
  await fetch(`${BASE}/orgs/${orgId}/chapters/${chapterId}`, { method: 'DELETE' })
}
