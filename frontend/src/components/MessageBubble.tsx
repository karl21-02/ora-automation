import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import type { ChatPlan, Message } from '../types'

interface Props {
  message: Message
  onExecute?: (plan: ChatPlan) => void
  onDismissPlan?: () => void
  executing?: boolean
}

const ALLOWED_TARGETS = [
  'run', 'run-direct', 'run-cycle', 'run-loop', 'run-cycle-deep',
  'run-single', 'e2e-service', 'e2e-service-all', 'verify-sources',
]

export default function MessageBubble({ message, onExecute, onDismissPlan, executing }: Props) {
  const isUser = message.role === 'user'
  const [editing, setEditing] = useState(false)
  const [editTarget, setEditTarget] = useState(message.plan?.target || '')
  const [editEnv, setEditEnv] = useState(() =>
    message.plan ? Object.entries(message.plan.env).map(([k, v]) => `${k}=${v}`).join('\n') : ''
  )

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
