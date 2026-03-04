import { useCallback, useEffect, useRef, useState } from 'react'
import { createRun, getRun, getRunEvents, sendChatStream, type ChatHistoryMessage } from '../lib/api'
import type { ChatPlan, Message, OrchestrationEvent, OrchestrationRun } from '../types'
import MessageBubble from './MessageBubble'

interface Props {
  messages: Message[]
  onNewMessage: (msg: Message) => void
  onUpdateMessage: (id: string, updates: Partial<Message>) => void
  conversationId: string
}

const STAGE_COLORS: Record<string, string> = {
  analysis: '#3b82f6',
  deliberation: '#8b5cf6',
  execution: '#059669',
  validation: '#f59e0b',
}

export default function ChatWindow({ messages, onNewMessage, onUpdateMessage, conversationId }: Props) {
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [executingPlanId, setExecutingPlanId] = useState<string | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [runStatus, setRunStatus] = useState<OrchestrationRun | null>(null)
  const [runEvents, setRunEvents] = useState<OrchestrationEvent[]>([])
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

  // Poll active run status + events
  useEffect(() => {
    if (!activeRunId) return
    const interval = setInterval(async () => {
      try {
        const [run, events] = await Promise.all([
          getRun(activeRunId),
          getRunEvents(activeRunId, 100),
        ])
        setRunStatus(run)
        setRunEvents(events)
        if (['completed', 'error', 'cancelled'].includes(run.status)) {
          clearInterval(interval)
          setActiveRunId(null)
          setExecutingPlanId(null)
          onNewMessage({
            id: crypto.randomUUID(),
            role: 'assistant',
            content: run.status === 'completed'
              ? `Run completed successfully (**${run.target}**).`
              : `Run ${run.status}: ${run.error_message || 'unknown error'}`,
            timestamp: new Date(),
          })
        }
      } catch {
        // ignore polling errors
      }
    }, 3000)
    return () => clearInterval(interval)
  }, [activeRunId, onNewMessage])

  const handleSend = useCallback(async () => {
    const text = input.trim()
    if (!text || loading) return

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: new Date(),
    }
    onNewMessage(userMsg)
    setInput('')
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
          // Final update with cleaned reply and plan
          const updates: Partial<Message> = {}
          if (event.full_reply) {
            updates.content = event.full_reply
          }
          if (event.plan) {
            updates.plan = event.plan
          }
          onUpdateMessage(assistantId, updates)
        } else if (event.type === 'error') {
          onUpdateMessage(assistantId, {
            content: `Error: ${event.content || 'unknown error'}`,
          })
        }
      })
    } catch (e) {
      if (streamedContent) {
        // Stream was partially received, update existing message
        onUpdateMessage(assistantId, {
          content: streamedContent || `Error: ${e instanceof Error ? e.message : String(e)}`,
        })
      } else {
        // No content was streamed, update the placeholder
        onUpdateMessage(assistantId, {
          content: `Error: ${e instanceof Error ? e.message : String(e)}`,
        })
      }
    } finally {
      setLoading(false)
      setStreaming(false)
    }
  }, [input, loading, conversationId, onNewMessage, onUpdateMessage, messages])

  const handleExecute = useCallback(async (plan: ChatPlan) => {
    const lastUserMsg = [...messages].reverse().find((m) => m.role === 'user')
    const prompt = lastUserMsg?.content || `Execute ${plan.target}`

    setExecutingPlanId(plan.target)
    setRunEvents([])
    try {
      const run = await createRun(plan, prompt)
      setActiveRunId(run.id)
      setRunStatus(run)
      onNewMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `Orchestration started: **${run.target}** (run: \`${run.id}\`)`,
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
  }, [messages, onNewMessage])

  const handleDismissPlan = useCallback((msgId: string) => {
    onUpdateMessage(msgId, { plan: null })
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

  // Compute progress
  const stages = runStatus?.pipeline_stages as string[] | undefined
  const currentStage = runStatus?.current_stage
  const currentIdx = stages && currentStage ? stages.indexOf(currentStage) : -1
  const progress = stages && stages.length > 0 && currentIdx >= 0
    ? Math.round(((currentIdx + 1) / stages.length) * 100)
    : 0

  return (
    <div style={{
      flex: 1,
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
    }}>
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
            Start a conversation with Ora
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onExecute={msg.plan ? handleExecute : undefined}
            onDismissPlan={msg.plan ? () => handleDismissPlan(msg.id) : undefined}
            executing={executingPlanId === msg.plan?.target}
          />
        ))}

        {/* Run live panel */}
        {runStatus && activeRunId && (
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
                  {runStatus.target} &middot; {runStatus.status}
                  {currentStage && ` (${currentStage})`}
                </span>
                <span style={{ fontSize: 12, fontWeight: 400 }}>
                  attempt {runStatus.attempt_count}/{runStatus.max_attempts}
                </span>
              </div>
              {/* Progress bar */}
              {stages && stages.length > 0 && (
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
          onClick={handleSend}
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
    </div>
  )
}
