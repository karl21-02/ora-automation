import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { ChatChoice, ChatPlan, Message } from '../types'
import ProjectSelectCard from './ProjectSelectCard'

interface Props {
  message: Message
  onExecute?: (plan: ChatPlan) => void
  onExecuteBatch?: (plans: ChatPlan[]) => void
  onDismissPlan?: () => void
  onChoiceClick?: (value: string) => void
  onProjectConfirm?: (selected: string[]) => void
  executing?: boolean
}

const ALLOWED_TARGETS = [
  'run', 'run-direct', 'run-cycle', 'run-loop', 'run-cycle-deep',
  'run-single', 'e2e-service', 'e2e-service-all', 'verify-sources',
]

export default function MessageBubble({ message, onExecute, onExecuteBatch, onDismissPlan, onChoiceClick, onProjectConfirm, executing }: Props) {
  const isUser = message.role === 'user'
  const [editing, setEditing] = useState(false)
  const [editTarget, setEditTarget] = useState(message.plan?.target || '')
  const [editEnv, setEditEnv] = useState(() =>
    message.plan ? Object.entries(message.plan.env).map(([k, v]) => `${k}=${v}`).join('\n') : ''
  )
  const [selectedPlans, setSelectedPlans] = useState<Set<number>>(() => {
    if (message.plans) return new Set(message.plans.map((_, i) => i))
    return new Set()
  })
  const [choiceClicked, setChoiceClicked] = useState(false)

  const parseEnv = (text: string): Record<string, string> => {
    const env: Record<string, string> = {}
    for (const line of text.split('\n')) {
      const trimmed = line.trim()
      if (!trimmed) continue
      const eqIdx = trimmed.indexOf('=')
      if (eqIdx <= 0) continue
      env[trimmed.slice(0, eqIdx).trim()] = trimmed.slice(eqIdx + 1).trim()
    }
    return env
  }

  const handleExecuteEdited = () => {
    if (!onExecute) return
    onExecute({ target: editTarget, env: parseEnv(editEnv) })
    setEditing(false)
  }

  const togglePlan = (idx: number) => {
    setSelectedPlans((prev) => {
      const next = new Set(prev)
      if (next.has(idx)) next.delete(idx)
      else next.add(idx)
      return next
    })
  }

  const handleExecuteBatchClick = () => {
    if (!onExecuteBatch || !message.plans) return
    const selected = message.plans.filter((_, i) => selectedPlans.has(i))
    if (selected.length > 0) onExecuteBatch(selected)
  }

  const handleChoiceSelect = (choice: ChatChoice) => {
    if (choiceClicked || !onChoiceClick) return
    setChoiceClicked(true)
    onChoiceClick(choice.value)
  }

  const envSummary = (env: Record<string, string>) => {
    const entries = Object.entries(env)
    if (entries.length === 0) return ''
    return entries.map(([k, v]) => {
      const short = v.length > 20 ? v.slice(0, 20) + '...' : v
      return `${k}=${short}`
    }).join('  ')
  }

  return (
    <div style={{
      display: 'flex',
      justifyContent: isUser ? 'flex-end' : 'flex-start',
      marginBottom: 12,
      padding: '0 16px',
    }}>
      <div style={{
        maxWidth: '70%',
        padding: '10px 14px',
        borderRadius: 12,
        backgroundColor: isUser ? '#2563eb' : '#f3f4f6',
        color: isUser ? '#fff' : '#1f2937',
        fontSize: 14,
        lineHeight: 1.6,
        wordBreak: 'break-word',
      }}>
        {isUser ? (
          <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{message.content}</p>
        ) : message.content ? (
          <div className="markdown-body">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        ) : (
          <span style={{ color: '#9ca3af', fontSize: 13 }}>&#9608;</span>
        )}

        {/* ── Multi-plan card ── */}
        {message.plans && message.plans.length > 0 && (
          <div style={{
            marginTop: 12,
            padding: '12px 14px',
            borderRadius: 10,
            backgroundColor: '#fff',
            border: '1px solid #d1d5db',
            fontSize: 13,
          }}>
            {/* Header */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontWeight: 700,
              fontSize: 13,
              color: '#374151',
              marginBottom: 10,
            }}>
              <span style={{
                display: 'inline-block',
                width: 8,
                height: 8,
                borderRadius: '50%',
                backgroundColor: '#f59e0b',
              }} />
              Confirm execution ({message.plans.length} projects)
            </div>

            {/* Plan rows */}
            {message.plans.map((plan, idx) => (
              <label
                key={idx}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 8,
                  padding: '8px 10px',
                  borderRadius: 6,
                  backgroundColor: selectedPlans.has(idx) ? '#f0fdf4' : '#f9fafb',
                  border: `1px solid ${selectedPlans.has(idx) ? '#86efac' : '#e5e7eb'}`,
                  marginBottom: 4,
                  cursor: executing ? 'not-allowed' : 'pointer',
                  transition: 'background-color 0.15s, border-color 0.15s',
                }}
              >
                <input
                  type="checkbox"
                  checked={selectedPlans.has(idx)}
                  onChange={() => togglePlan(idx)}
                  disabled={executing}
                  style={{ marginTop: 2, accentColor: '#059669' }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, color: '#1f2937' }}>
                    {plan.label || plan.target}
                  </div>
                  <div style={{
                    fontSize: 12,
                    color: '#6b7280',
                    fontFamily: 'monospace',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}>
                    {plan.target}
                    {envSummary(plan.env) && <span style={{ marginLeft: 8 }}>{envSummary(plan.env)}</span>}
                  </div>
                </div>
              </label>
            ))}

            {/* Action buttons */}
            {onExecuteBatch && (
              <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                <button
                  onClick={handleExecuteBatchClick}
                  disabled={executing || selectedPlans.size === 0}
                  style={{
                    flex: 1,
                    padding: '8px 0',
                    borderRadius: 7,
                    border: 'none',
                    backgroundColor: (executing || selectedPlans.size === 0) ? '#9ca3af' : '#059669',
                    color: '#fff',
                    fontWeight: 600,
                    fontSize: 13,
                    cursor: (executing || selectedPlans.size === 0) ? 'not-allowed' : 'pointer',
                  }}
                >
                  {executing ? 'Executing...' : `Execute All (${selectedPlans.size})`}
                </button>
                {!executing && onDismissPlan && (
                  <button
                    onClick={onDismissPlan}
                    style={{
                      padding: '8px 16px',
                      borderRadius: 7,
                      border: '1px solid #d1d5db',
                      backgroundColor: '#fff',
                      color: '#6b7280',
                      fontWeight: 500,
                      fontSize: 13,
                      cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── Single plan card (backward compat) ── */}
        {message.plan && (
          <div style={{
            marginTop: 12,
            padding: '12px 14px',
            borderRadius: 10,
            backgroundColor: '#fff',
            border: '1px solid #d1d5db',
            fontSize: 13,
          }}>
            {/* Header */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 8,
            }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontWeight: 700,
                fontSize: 13,
                color: '#374151',
              }}>
                <span style={{
                  display: 'inline-block',
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  backgroundColor: '#f59e0b',
                }} />
                Confirm execution
              </div>
              {!executing && !editing && (
                <button
                  onClick={() => setEditing(true)}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: '#6b7280',
                    fontSize: 12,
                    cursor: 'pointer',
                    textDecoration: 'underline',
                    padding: 0,
                  }}
                >
                  Edit
                </button>
              )}
            </div>

            {editing ? (
              /* Edit mode */
              <div>
                {/* Target select */}
                <div style={{ marginBottom: 8 }}>
                  <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>
                    Target
                  </label>
                  <select
                    value={editTarget}
                    onChange={(e) => setEditTarget(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '6px 8px',
                      borderRadius: 6,
                      border: '1px solid #d1d5db',
                      fontSize: 13,
                      fontFamily: 'monospace',
                      outline: 'none',
                    }}
                  >
                    {ALLOWED_TARGETS.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>

                {/* Env textarea */}
                <div style={{ marginBottom: 8 }}>
                  <label style={{ fontSize: 12, color: '#6b7280', display: 'block', marginBottom: 4 }}>
                    Environment (KEY=VALUE per line)
                  </label>
                  <textarea
                    value={editEnv}
                    onChange={(e) => setEditEnv(e.target.value)}
                    rows={3}
                    style={{
                      width: '100%',
                      padding: '6px 8px',
                      borderRadius: 6,
                      border: '1px solid #d1d5db',
                      fontSize: 12,
                      fontFamily: 'monospace',
                      lineHeight: 1.5,
                      resize: 'vertical',
                      outline: 'none',
                      boxSizing: 'border-box',
                    }}
                    placeholder="ORCHESTRATION_PROFILE=strict"
                  />
                </div>

                {/* Edit action buttons */}
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={handleExecuteEdited}
                    style={{
                      flex: 1,
                      padding: '8px 0',
                      borderRadius: 7,
                      border: 'none',
                      backgroundColor: '#059669',
                      color: '#fff',
                      fontWeight: 600,
                      fontSize: 13,
                      cursor: 'pointer',
                    }}
                  >
                    Execute
                  </button>
                  <button
                    onClick={() => {
                      setEditing(false)
                      setEditTarget(message.plan!.target)
                      setEditEnv(Object.entries(message.plan!.env).map(([k, v]) => `${k}=${v}`).join('\n'))
                    }}
                    style={{
                      padding: '8px 16px',
                      borderRadius: 7,
                      border: '1px solid #d1d5db',
                      backgroundColor: '#fff',
                      color: '#6b7280',
                      fontWeight: 500,
                      fontSize: 13,
                      cursor: 'pointer',
                    }}
                  >
                    Back
                  </button>
                </div>
              </div>
            ) : (
              /* View mode */
              <>
                {/* Target */}
                <div style={{
                  padding: '6px 10px',
                  borderRadius: 6,
                  backgroundColor: '#f3f4f6',
                  marginBottom: 6,
                }}>
                  <span style={{ color: '#6b7280', fontSize: 12 }}>Target: </span>
                  <code style={{
                    fontWeight: 600,
                    color: '#1f2937',
                    backgroundColor: 'transparent',
                    padding: 0,
                  }}>
                    {message.plan.target}
                  </code>
                </div>

                {/* Env vars */}
                {Object.keys(message.plan.env).length > 0 && (
                  <div style={{
                    padding: '6px 10px',
                    borderRadius: 6,
                    backgroundColor: '#f3f4f6',
                    marginBottom: 8,
                    fontFamily: 'monospace',
                    fontSize: 12,
                    lineHeight: 1.6,
                  }}>
                    {Object.entries(message.plan.env).map(([k, v]) => (
                      <div key={k}>
                        <span style={{ color: '#6b7280' }}>{k}</span>
                        <span style={{ color: '#9ca3af' }}>=</span>
                        <span style={{ color: '#1f2937' }}>{v}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Action buttons */}
                {onExecute && (
                  <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                    <button
                      onClick={() => onExecute(message.plan!)}
                      disabled={executing}
                      style={{
                        flex: 1,
                        padding: '8px 0',
                        borderRadius: 7,
                        border: 'none',
                        backgroundColor: executing ? '#9ca3af' : '#059669',
                        color: '#fff',
                        fontWeight: 600,
                        fontSize: 13,
                        cursor: executing ? 'not-allowed' : 'pointer',
                      }}
                    >
                      {executing ? 'Executing...' : 'Execute'}
                    </button>
                    {!executing && onDismissPlan && (
                      <button
                        onClick={onDismissPlan}
                        style={{
                          padding: '8px 16px',
                          borderRadius: 7,
                          border: '1px solid #d1d5db',
                          backgroundColor: '#fff',
                          color: '#6b7280',
                          fontWeight: 500,
                          fontSize: 13,
                          cursor: 'pointer',
                        }}
                      >
                        Cancel
                      </button>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ── Choices buttons ── */}
        {message.choices && message.choices.length > 0 && (
          <div style={{
            marginTop: 12,
            display: 'flex',
            flexWrap: 'wrap',
            gap: 8,
          }}>
            {message.choices.map((choice, idx) => {
              const disabled = choiceClicked || !onChoiceClick
              return (
                <button
                  key={idx}
                  onClick={() => handleChoiceSelect(choice)}
                  disabled={disabled}
                  style={{
                    flex: '1 1 140px',
                    padding: '10px 14px',
                    borderRadius: 10,
                    border: '1px solid #d1d5db',
                    backgroundColor: disabled ? '#f9fafb' : '#fff',
                    color: disabled ? '#9ca3af' : '#1f2937',
                    cursor: disabled ? 'not-allowed' : 'pointer',
                    textAlign: 'left',
                    transition: 'all 0.15s',
                  }}
                  onMouseEnter={(e) => {
                    if (!disabled) {
                      e.currentTarget.style.borderColor = '#2563eb'
                      e.currentTarget.style.backgroundColor = '#eff6ff'
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!disabled) {
                      e.currentTarget.style.borderColor = '#d1d5db'
                      e.currentTarget.style.backgroundColor = '#fff'
                    }
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{choice.label}</div>
                  {choice.description && (
                    <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                      {choice.description}
                    </div>
                  )}
                </button>
              )
            })}
          </div>
        )}

        {/* ── Project select card ── */}
        {message.projectSelect && message.projectSelect.length > 0 && (
          <ProjectSelectCard
            projects={message.projectSelect}
            onConfirm={onProjectConfirm ?? (() => {})}
            onDismiss={onProjectConfirm ? () => onProjectConfirm([]) : () => {}}
            disabled={!onProjectConfirm}
          />
        )}

        {message.runId && (
          <div style={{ marginTop: 6, fontSize: 12, opacity: 0.7 }}>
            Run: {message.runId}
          </div>
        )}

        <div style={{
          marginTop: 6,
          fontSize: 11,
          opacity: 0.5,
          textAlign: isUser ? 'right' : 'left',
        }}>
          {message.timestamp.toLocaleTimeString()}
        </div>
      </div>
    </div>
  )
}
