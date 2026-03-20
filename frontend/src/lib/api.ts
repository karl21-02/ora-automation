import type { ChatChoice, ChatPlan, ChatResponse, GithubInstallation, GithubRepo, LocalScanResult, OrgAgent, OrgChapter, OrgRecommendOption, OrgSilo, OrchestrationEvent, OrchestrationRun, Organization, OrganizationDetail, ProjectConfigResponse, ProjectEnvResponse, ProjectHistoryResponse, ProjectInfo, ProjectList, ProjectPrepareResponse, ReportListItem, ScanPath, ScanPathCreate, ScanPathList, ScanPathUpdate, ScanResult, ScheduledJob, ScheduledJobCreate, UnifiedProject } from '../types'

// Use GCP server in production, localhost in development
const API_HOST = import.meta.env.PROD
  ? 'https://api.mimir.wollenlabs.com'
  : ''
const BASE = `${API_HOST}/api/v1`

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
  org_recommend?: OrgRecommendOption[] | null
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

export async function createRun(
  plan: ChatPlan,
  userPrompt: string,
  orgId?: string | null,
  guestAgentIds?: string[],
  projectId?: string | null,
): Promise<OrchestrationRun> {
  return request<OrchestrationRun>(`${BASE}/orchestrations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_prompt: userPrompt,
      target: plan.target,
      env: plan.env,
      org_id: orgId ?? undefined,
      project_id: projectId ?? undefined,
      guest_agent_ids: guestAgentIds && guestAgentIds.length > 0 ? guestAgentIds : undefined,
    }),
  })
}

export async function createProjectRun(
  projectId: string,
  target: string = 'run-cycle',
  focus?: string,
): Promise<OrchestrationRun> {
  const env: Record<string, string> = {}
  if (focus) {
    env['FOCUS'] = focus
  }
  return request<OrchestrationRun>(`${BASE}/orchestrations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      user_prompt: `Analyze project ${projectId}`,
      target,
      env,
      project_id: projectId,
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
  template_id?: string
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

// ── GitHub Integration ──────────────────────────────────────────────

export async function getGithubInstallUrl(): Promise<{ url: string }> {
  return request<{ url: string }>(`${BASE}/github/install-url`)
}

export async function listGithubInstallations(): Promise<GithubInstallation[]> {
  return request<GithubInstallation[]>(`${BASE}/github/installations`)
}

export async function syncGithubInstallation(installationId: string): Promise<{ synced: number }> {
  return request<{ synced: number }>(`${BASE}/github/installations/${installationId}/sync`, {
    method: 'POST',
  })
}

export async function deleteGithubInstallation(installationId: string): Promise<void> {
  await fetch(`${BASE}/github/installations/${installationId}`, { method: 'DELETE' })
}

export async function listGithubRepos(installationId?: string): Promise<GithubRepo[]> {
  const params = installationId ? `?installation_id=${installationId}` : ''
  return request<GithubRepo[]>(`${BASE}/github/repos${params}`)
}

// ── Unified Projects ──────────────────────────────────────────────

export async function listUnifiedProjects(params?: {
  source_type?: string
  enabled?: boolean
  search?: string
  limit?: number
  offset?: number
}): Promise<ProjectList> {
  const searchParams = new URLSearchParams()
  if (params?.source_type) searchParams.set('source_type', params.source_type)
  if (params?.enabled !== undefined) searchParams.set('enabled', String(params.enabled))
  if (params?.search) searchParams.set('search', params.search)
  if (params?.limit) searchParams.set('limit', String(params.limit))
  if (params?.offset) searchParams.set('offset', String(params.offset))
  const query = searchParams.toString()
  return request<ProjectList>(`${BASE}/unified-projects${query ? `?${query}` : ''}`)
}

export async function getUnifiedProject(projectId: string): Promise<UnifiedProject> {
  return request<UnifiedProject>(`${BASE}/unified-projects/${projectId}`)
}

export async function createUnifiedProject(data: {
  name: string
  description?: string
  source_type?: string
  local_path?: string
  github_repo_id?: string
  enabled?: boolean
  language?: string
  default_branch?: string
}): Promise<UnifiedProject> {
  return request<UnifiedProject>(`${BASE}/unified-projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function updateUnifiedProject(projectId: string, data: Partial<{
  name: string
  description: string
  enabled: boolean
  language: string
  default_branch: string
}>): Promise<UnifiedProject> {
  return request<UnifiedProject>(`${BASE}/unified-projects/${projectId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function deleteUnifiedProject(projectId: string): Promise<void> {
  await fetch(`${BASE}/unified-projects/${projectId}`, { method: 'DELETE' })
}

export async function scanLocalProjects(workspacePath?: string): Promise<LocalScanResult> {
  const params = workspacePath ? `?workspace_path=${encodeURIComponent(workspacePath)}` : ''
  return request<LocalScanResult>(`${BASE}/unified-projects/scan-local${params}`, {
    method: 'POST',
  })
}

export async function prepareProject(projectId: string, forcePull = false): Promise<ProjectPrepareResponse> {
  return request<ProjectPrepareResponse>(`${BASE}/unified-projects/${projectId}/prepare?force_pull=${forcePull}`, {
    method: 'POST',
  })
}

export async function getProjectEnv(projectId: string): Promise<ProjectEnvResponse> {
  return request<ProjectEnvResponse>(`${BASE}/unified-projects/${projectId}/env`)
}

export async function getProjectConfig(projectId: string): Promise<ProjectConfigResponse> {
  return request<ProjectConfigResponse>(`${BASE}/unified-projects/${projectId}/config`)
}

export async function getProjectHistory(projectId: string, limit = 20, offset = 0): Promise<ProjectHistoryResponse> {
  return request<ProjectHistoryResponse>(`${BASE}/unified-projects/${projectId}/history?limit=${limit}&offset=${offset}`)
}

// ── Scan Paths ──────────────────────────────────────────────────────

export async function listScanPaths(enabled?: boolean): Promise<ScanPathList> {
  const params = enabled !== undefined ? `?enabled=${enabled}` : ''
  return request<ScanPathList>(`${BASE}/scan-paths${params}`)
}

export async function createScanPath(data: ScanPathCreate): Promise<ScanPath> {
  return request<ScanPath>(`${BASE}/scan-paths`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function getScanPath(scanPathId: string): Promise<ScanPath> {
  return request<ScanPath>(`${BASE}/scan-paths/${scanPathId}`)
}

export async function updateScanPath(scanPathId: string, data: ScanPathUpdate): Promise<ScanPath> {
  return request<ScanPath>(`${BASE}/scan-paths/${scanPathId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function deleteScanPath(scanPathId: string): Promise<void> {
  await fetch(`${BASE}/scan-paths/${scanPathId}`, { method: 'DELETE' })
}

export async function executeScanPath(scanPathId: string): Promise<ScanResult> {
  return request<ScanResult>(`${BASE}/scan-paths/${scanPathId}/scan`, {
    method: 'POST',
  })
}

export async function executeScanAll(): Promise<ScanResult[]> {
  return request<ScanResult[]>(`${BASE}/scan-paths/scan-all`, {
    method: 'POST',
  })
}
