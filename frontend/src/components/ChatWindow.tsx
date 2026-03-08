import { useCallback, useEffect, useRef, useState } from 'react'
import { createBatchRuns, createRun, getRun, getRunEvents, sendChatStream, type ChatHistoryMessage } from '../lib/api'
import { APP_NAME } from '../lib/constants'
import type { ChatPlan, DialogState, Message, OrchestrationEvent, OrchestrationRun, Organization } from '../types'
import GuestAgentPicker from './GuestAgentPicker'
import MessageBubble from './MessageBubble'

interface Props {
  messages: Message[]
  onNewMessage: (msg: Message) => void
  onUpdateMessage: (id: string, updates: Partial<Message>) => void
  conversationId: string
  orgId: string | null
  orgName: string | null
  orgs: Organization[]
  onChangeOrg: (orgId: string | null) => void
}

const STAGE_COLORS: Record<string, string> = {
  analysis: '#3b82f6',
  deliberation: '#8b5cf6',
  execution: '#059669',
  validation: '#f59e0b',
}

export default function ChatWindow({ messages, onNewMessage, onUpdateMessage, conversationId, orgId, orgName: _orgName, orgs, onChangeOrg }: Props) {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [executingPlanId, setExecutingPlanId] = useState<string | null>(null)
  const [activeRunIds, setActiveRunIds] = useState<string[]>([])
  const [runStatuses, setRunStatuses] = useState<Record<string, OrchestrationRun>>({})
  const [runEvents, setRunEvents] = useState<OrchestrationEvent[]>([])
  const [showGuestPicker, setShowGuestPicker] = useState(false)
  const [selectedGuestAgents, setSelectedGuestAgents] = useState<string[]>([])
  const endRef = useRef<HTMLDivElement>(null)
  const logEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, runEvents])

  // Auto-scroll log panel
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [runEvents])

  // Poll active run statuses + events
  useEffect(() => {
    if (activeRunIds.length === 0) return
    const interval = setInterval(async () => {
      try {
        const results = await Promise.all(
          activeRunIds.map(async (id) => {
            const [run, events] = await Promise.all([getRun(id), getRunEvents(id, 100)])
            return { id, run, events }
          })
        )

        const newStatuses: Record<string, OrchestrationRun> = {}
        const allEvents: OrchestrationEvent[] = []
        const stillActive: string[] = []

        for (const { id, run, events } of results) {
          newStatuses[id] = run
          allEvents.push(...events)
          if (['completed', 'error', 'cancelled'].includes(run.status)) {
            onNewMessage({
              id: crypto.randomUUID(),
              role: 'assistant',
              content: run.status === 'completed'
                ? `Run completed successfully (**${run.target}**, \`${id.slice(0, 8)}\`).`
                : `Run ${run.status} (**${run.target}**): ${run.error_message || 'unknown error'}`,
              timestamp: new Date(),
            })
          } else {
            stillActive.push(id)
          }
        }

        setRunStatuses(newStatuses)
        setRunEvents(allEvents.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()))

        if (stillActive.length < activeRunIds.length) {
          setActiveRunIds(stillActive)
          if (stillActive.length === 0) {
            setExecutingPlanId(null)
          }
        }
      } catch {
        // ignore polling errors
      }
    }, 3000)
    return () => clearInterval(interval)
  }, [activeRunIds, onNewMessage])

  const handleSend = useCallback(async (textOverride?: string) => {
    const text = (textOverride ?? input).trim()
    if (!text || loading) return

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    }
    onNewMessage(userMsg)
    if (!textOverride) setInput('')
    setLoading(true)

    const assistantId = crypto.randomUUID()
    let streamedContent = ''

    try {
      const history: ChatHistoryMessage[] = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }))

      // Add placeholder message for streaming
      onNewMessage({
        id: assistantId,
        role: 'assistant',
        content: '',
        timestamp: new Date(),
      })

      await sendChatStream(text, history, conversationId, (event) => {
        if (event.type === 'token' && event.content) {
          if (!streamedContent) setStreaming(true)
          streamedContent += event.content
          onUpdateMessage(assistantId, { content: streamedContent })
        } else if (event.type === 'done') {
          // Final update with cleaned reply, plan, plans, choices
          const updates: Partial<Message> = {}
          if (event.full_reply) {
            updates.content = event.full_reply
          }
          if (event.plan) {
            updates.plan = event.plan
          }
          if (event.plans && event.plans.length > 0) {
            updates.plans = event.plans
          }
          if (event.choices && event.choices.length > 0) {
            updates.choices = event.choices
          }
          if (event.project_select && event.project_select.length > 0) {
            updates.projectSelect = event.project_select
          }
          if (event.org_recommend && event.org_recommend.length > 0) {
            updates.orgRecommend = event.org_recommend
          }
          if (event.dialog_state) {
            updates.dialogState = event.dialog_state as DialogState
          }
          if (event.confirmation_required) {
            updates.confirmationRequired = true
          }
          if (event.intent_summary) {
            updates.intentSummary = event.intent_summary
          }
          onUpdateMessage(assistantId, updates)
        } else if (event.type === 'error') {
          onUpdateMessage(assistantId, {
            content: `Error: ${event.content || 'unknown error'}`,
          })
        }
      }, orgId)
    } catch (e) {
      if (streamedContent) {
        onUpdateMessage(assistantId, {
          content: streamedContent || `Error: ${e instanceof Error ? e.message : String(e)}`,
        })
      } else {
        onUpdateMessage(assistantId, {
          content: `Error: ${e instanceof Error ? e.message : String(e)}`,
        })
      }
    } finally {
      setLoading(false)
      setStreaming(false)
    }
  }, [input, loading, conversationId, onNewMessage, onUpdateMessage, messages, orgId])

  const handleExecute = useCallback(async (plan: ChatPlan, confirmViaChat?: boolean, guestAgentIds?: string[]) => {
    // UPCE mode: send "확인" as a chat message instead of direct API call
    if (confirmViaChat) {
      handleSend('확인')
      return
    }

    const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user')
    const prompt = lastUserMsg?.content || `Execute ${plan.target}`

    setExecutingPlanId(plan.target)
    setRunEvents([])
    try {
      const run = await createRun(plan, prompt, orgId, guestAgentIds)
      setActiveRunIds([run.id])
      setRunStatuses({ [run.id]: run })
      setSelectedGuestAgents([])  // Clear guest selection after execution
      const guestInfo = guestAgentIds && guestAgentIds.length > 0
        ? ` with ${guestAgentIds.length} guest agent(s)`
        : ''
      onNewMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `Orchestration started: **${run.target}**${guestInfo} (run: \`${run.id}\`)`,
        runId: run.id,
        timestamp: new Date(),
      })
    } catch (e) {
      setExecutingPlanId(null)
      onNewMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `Failed to start orchestration: ${e instanceof Error ? e.message : String(e)}`,
        timestamp: new Date(),
      })
    }
  }, [messages, onNewMessage, handleSend, orgId])

  const handleExecuteBatch = useCallback(async (plans: ChatPlan[]) => {
    const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user')
    const prompt = lastUserMsg?.content || `Execute ${plans.length} projects`

    setExecutingPlanId('batch')
    setRunEvents([])
    try {
      const { runs } = await createBatchRuns(plans, prompt, orgId)
      const ids = runs.map((r) => r.id)
      setActiveRunIds(ids)
      const statuses: Record<string, OrchestrationRun> = {}
      for (const r of runs) statuses[r.id] = r
      setRunStatuses(statuses)

      const labels = plans.map((p) => p.label || p.target).join(', ')
      onNewMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `Batch started: **${runs.length} runs** (${labels})`,
        timestamp: new Date(),
      })
    } catch (e) {
      setExecutingPlanId(null)
      onNewMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `Failed to start batch: ${e instanceof Error ? e.message : String(e)}`,
        timestamp: new Date(),
      })
    }
  }, [messages, onNewMessage])

  const handleChoiceClick = useCallback((value: string) => {
    handleSend(value)
  }, [handleSend])

  const handleProjectConfirm = useCallback((selected: string[]) => {
    if (selected.length === 0) {
      onNewMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: 'Cancelled. Let me know if you want to try something else.',
        timestamp: new Date(),
      })
      return
    }
    const text = `다음 프로젝트 선택: ${selected.join(', ')}`
    handleSend(text)
  }, [handleSend, onNewMessage])

  const handleOrgRecommendSelect = useCallback((orgId: string | null) => {
    if (orgId) {
      onChangeOrg(orgId)
    }
    handleSend(`ora:org_select:${orgId ?? ''}`)
  }, [handleSend, onChangeOrg])

  const handleDismissPlan = useCallback((msgId: string) => {
    onUpdateMessage(msgId, { plan: null, plans: null })
    onNewMessage({
      id: crypto.randomUUID(),
      role: 'assistant',
      content: 'Cancelled. Let me know if you want to adjust anything or try something else.',
      timestamp: new Date(),
    })
  }, [onUpdateMessage, onNewMessage])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Compute progress for first active run (primary display)
  const primaryRunId = activeRunIds[0] || null
  const primaryRun = primaryRunId ? runStatuses[primaryRunId] : null
  const stages = primaryRun?.pipeline_stages as string[] | undefined
  const currentStage = primaryRun?.current_stage
  const currentIdx = stages && currentStage ? stages.indexOf(currentStage) : -1

  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
    }}>
      {/* Org selector bar */}
      {orgs.length > 0 && (
        <div style={{
          padding: '8px 16px',
          borderBottom: '1px solid #e5e7eb',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          backgroundColor: '#f9fafb',
        }}>
          <span style={{ fontSize: 14 }}>{'\u{1F3E2}'}</span>
          <select
            value={orgId ?? ''}
            onChange={(e) => onChangeOrg(e.target.value || null)}
            style={{
              flex: 1,
              padding: '4px 8px',
              borderRadius: 6,
              border: '1px solid #d1d5db',
              backgroundColor: '#fff',
              fontSize: 13,
              color: '#374151',
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="">{'\u{1F4CE}'} 미분류 (기본 프리셋)</option>
            {orgs.map((org) => (
              <option key={org.id} value={org.id}>{org.name}</option>
            ))}
          </select>
        </div>
      )}

      {/* Messages */}
      <div style={{
        flex: 1,
        overflow: 'auto',
        padding: '16px 0',
      }}>
        {messages.length === 0 && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            color: '#9ca3af',
            fontSize: 15,
          }}>
            Start a conversation with {APP_NAME}
          </div>
        )}
        {messages.map((msg, idx) => {
          // Only allow interactive widgets on the last assistant message
          const isLastAssistant = msg.role === 'assistant' && !messages.slice(idx + 1).some((m) => m.role === 'assistant')
          return (
            <MessageBubble
              key={msg.id}
              message={msg}
              onExecute={msg.plan ? handleExecute : undefined}
              onExecuteBatch={msg.plans && msg.plans.length > 0 ? handleExecuteBatch : undefined}
              onDismissPlan={(msg.plan || (msg.plans && msg.plans.length > 0)) ? () => handleDismissPlan(msg.id) : undefined}
              onChoiceClick={isLastAssistant && msg.choices && msg.choices.length > 0 ? handleChoiceClick : undefined}
              onProjectConfirm={isLastAssistant && msg.projectSelect && msg.projectSelect.length > 0 ? handleProjectConfirm : undefined}
              onOrgRecommendSelect={isLastAssistant && msg.orgRecommend && msg.orgRecommend.length > 0 ? handleOrgRecommendSelect : undefined}
              onConfirmDialog={isLastAssistant && msg.confirmationRequired ? () => handleSend('확인') : undefined}
              onRejectDialog={isLastAssistant && msg.confirmationRequired ? () => handleSend('취소') : undefined}
              onOpenGuestPicker={isLastAssistant && msg.plan ? () => setShowGuestPicker(true) : undefined}
              guestAgentIds={isLastAssistant && msg.plan ? selectedGuestAgents : undefined}
              executing={executingPlanId != null && (executingPlanId === msg.plan?.target || executingPlanId === 'batch')}
            />
          )
        })}

        {/* Run live panel */}
        {primaryRun && activeRunIds.length > 0 && (
          <div style={{
            margin: '0 16px 12px',
            borderRadius: 10,
            border: '1px solid #e5e7eb',
            overflow: 'hidden',
          }}>
            {/* Header + progress bar */}
            <div style={{
              padding: '10px 12px',
              backgroundColor: '#fefce8',
              borderBottom: '1px solid #e5e7eb',
            }}>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                fontSize: 13,
                fontWeight: 600,
                color: '#92400e',
                marginBottom: 6,
              }}>
                <span>
                  {activeRunIds.length > 1
                    ? `${activeRunIds.length} runs active`
                    : `${primaryRun.target} \u00b7 ${primaryRun.status}`}
                  {activeRunIds.length === 1 && currentStage && ` (${currentStage})`}
                </span>
                {activeRunIds.length === 1 && (
                  <span style={{ fontSize: 12, fontWeight: 400 }}>
                    attempt {primaryRun.attempt_count}/{primaryRun.max_attempts}
                  </span>
                )}
              </div>
              {/* Progress bar (single run) */}
              {activeRunIds.length === 1 && stages && stages.length > 0 && (
                <div style={{
                  display: 'flex',
                  gap: 2,
                  height: 4,
                  borderRadius: 2,
                  overflow: 'hidden',
                  backgroundColor: '#e5e7eb',
                }}>
                  {stages.map((stage, i) => (
                    <div
                      key={stage}
                      style={{
                        flex: 1,
                        backgroundColor: i <= currentIdx
                          ? (STAGE_COLORS[stage] || '#3b82f6')
                          : 'transparent',
                        transition: 'background-color 0.3s',
                      }}
                    />
                  ))}
                </div>
              )}
              {/* Multi-run status badges */}
              {activeRunIds.length > 1 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                  {activeRunIds.map((id) => {
                    const r = runStatuses[id]
                    return (
                      <span key={id} style={{
                        display: 'inline-block',
                        padding: '2px 8px',
                        borderRadius: 4,
                        fontSize: 11,
                        fontWeight: 500,
                        backgroundColor: r?.status === 'running' ? '#dbeafe' : '#f3f4f6',
                        color: r?.status === 'running' ? '#1e40af' : '#6b7280',
                      }}>
                        {r?.target || id.slice(0, 8)} \u00b7 {r?.status || '...'}
                      </span>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Event log */}
            {runEvents.length > 0 && (
              <div style={{
                maxHeight: 200,
                overflow: 'auto',
                padding: '8px 12px',
                backgroundColor: '#f9fafb',
                fontSize: 12,
                fontFamily: 'monospace',
                lineHeight: 1.6,
              }}>
                {runEvents.map((evt) => (
                  <div key={evt.id} style={{
                    display: 'flex',
                    gap: 8,
                    borderBottom: '1px solid #f3f4f6',
                    padding: '3px 0',
                  }}>
                    <span style={{
                      color: STAGE_COLORS[evt.stage] || '#6b7280',
                      fontWeight: 600,
                      minWidth: 80,
                    }}>
                      {evt.stage}
                    </span>
                    <span style={{
                      color: evt.event_type === 'error' ? '#ef4444' : '#6b7280',
                      minWidth: 60,
                    }}>
                      {evt.event_type}
                    </span>
                    <span style={{ color: '#374151', flex: 1 }}>
                      {evt.message}
                    </span>
                    <span style={{ color: '#9ca3af', whiteSpace: 'nowrap' }}>
                      {new Date(evt.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                ))}
                <div ref={logEndRef} />
              </div>
            )}
          </div>
        )}

        {loading && !streaming && (
          <div style={{
            padding: '8px 16px',
            color: '#9ca3af',
            fontSize: 13,
          }}>
            Thinking...
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Input */}
      <div style={{
        borderTop: '1px solid #e5e7eb',
        padding: '12px 16px',
        display: 'flex',
        gap: 8,
      }}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message... (Enter to send, Shift+Enter for newline)"
          rows={1}
          style={{
            flex: 1,
            padding: '10px 14px',
            borderRadius: 8,
            border: '1px solid #d1d5db',
            resize: 'none',
            fontSize: 14,
            lineHeight: 1.5,
            outline: 'none',
            fontFamily: 'inherit',
          }}
          onInput={(e) => {
            const el = e.target as HTMLTextAreaElement
            el.style.height = 'auto'
            el.style.height = Math.min(el.scrollHeight, 120) + 'px'
          }}
        />
        <button
          onClick={() => handleSend()}
          disabled={!input.trim() || loading}
          style={{
            padding: '10px 20px',
            borderRadius: 8,
            border: 'none',
            backgroundColor: (!input.trim() || loading) ? '#d1d5db' : '#2563eb',
            color: '#fff',
            fontWeight: 600,
            fontSize: 14,
            cursor: (!input.trim() || loading) ? 'not-allowed' : 'pointer',
            whiteSpace: 'nowrap',
          }}
        >
          Send
        </button>
      </div>

      {/* Guest Agent Picker Modal */}
      {showGuestPicker && (
        <GuestAgentPicker
          currentOrgId={orgId}
          selectedGuests={selectedGuestAgents}
          onSelect={setSelectedGuestAgents}
          onClose={() => setShowGuestPicker(false)}
        />
      )}
    </div>
  )
}
