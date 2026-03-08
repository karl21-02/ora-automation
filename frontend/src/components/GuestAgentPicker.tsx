import { useEffect, useState } from 'react'
import { getOrg, listOrgs } from '../lib/api'
import type { OrgAgent, Organization, OrganizationDetail } from '../types'

interface Props {
  currentOrgId: string | null
  selectedGuests: string[]  // ["org_id:agent_id", ...]
  onSelect: (guests: string[]) => void
  onClose: () => void
}

export default function GuestAgentPicker({ currentOrgId, selectedGuests, onSelect, onClose }: Props) {
  const [orgs, setOrgs] = useState<Organization[]>([])
  const [expandedOrgId, setExpandedOrgId] = useState<string | null>(null)
  const [orgDetails, setOrgDetails] = useState<Record<string, OrganizationDetail>>({})
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Set<string>>(new Set(selectedGuests))

  useEffect(() => {
    listOrgs().then(({ items }) => {
      // Filter out current org
      const filtered = items.filter((o) => o.id !== currentOrgId)
      setOrgs(filtered)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [currentOrgId])

  const loadOrgDetail = async (orgId: string) => {
    if (orgDetails[orgId]) return
    try {
      const detail = await getOrg(orgId)
      setOrgDetails((prev) => ({ ...prev, [orgId]: detail }))
    } catch {
      // ignore
    }
  }

  const toggleOrg = (orgId: string) => {
    if (expandedOrgId === orgId) {
      setExpandedOrgId(null)
    } else {
      setExpandedOrgId(orgId)
      loadOrgDetail(orgId)
    }
  }

  const toggleAgent = (orgId: string, agentId: string) => {
    const key = `${orgId}:${agentId}`
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  const handleConfirm = () => {
    onSelect(Array.from(selected))
    onClose()
  }

  if (loading) {
    return (
      <div style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}>
        <div style={{ padding: 20, backgroundColor: '#fff', borderRadius: 10 }}>
          Loading...
        </div>
      </div>
    )
  }

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      backgroundColor: 'rgba(0,0,0,0.4)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
    }}>
      <div style={{
        width: 400,
        maxHeight: '80vh',
        backgroundColor: '#fff',
        borderRadius: 12,
        boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          padding: '14px 16px',
          borderBottom: '1px solid #e5e7eb',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div style={{ fontWeight: 700, fontSize: 15, color: '#1f2937' }}>
            {'\u{1F465}'} 게스트 에이전트 선택
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              fontSize: 18,
              color: '#9ca3af',
              cursor: 'pointer',
              padding: 4,
            }}
          >
            {'\u00D7'}
          </button>
        </div>

        {/* Body */}
        <div style={{
          flex: 1,
          overflow: 'auto',
          padding: '12px 16px',
        }}>
          {orgs.length === 0 ? (
            <div style={{ color: '#9ca3af', fontSize: 13, textAlign: 'center', padding: 20 }}>
              다른 조직이 없습니다
            </div>
          ) : (
            orgs.map((org) => {
              const detail = orgDetails[org.id]
              const isExpanded = expandedOrgId === org.id
              const enabledAgents = detail?.agents.filter((a) => a.enabled) || []

              return (
                <div key={org.id} style={{ marginBottom: 8 }}>
                  {/* Org header */}
                  <button
                    onClick={() => toggleOrg(org.id)}
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      borderRadius: 8,
                      border: '1px solid #e5e7eb',
                      backgroundColor: isExpanded ? '#f3f4f6' : '#fff',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      textAlign: 'left',
                    }}
                  >
                    <span style={{ fontSize: 14 }}>{isExpanded ? '\u25BC' : '\u25B6'}</span>
                    <span style={{ fontWeight: 600, fontSize: 13, color: '#374151', flex: 1 }}>
                      {'\u{1F3E2}'} {org.name}
                    </span>
                    {org.is_preset && (
                      <span style={{
                        fontSize: 10,
                        padding: '2px 6px',
                        borderRadius: 4,
                        backgroundColor: '#dbeafe',
                        color: '#1e40af',
                      }}>
                        프리셋
                      </span>
                    )}
                  </button>

                  {/* Agent list */}
                  {isExpanded && (
                    <div style={{
                      marginTop: 4,
                      marginLeft: 16,
                      padding: '8px 0',
                      borderLeft: '2px solid #e5e7eb',
                      paddingLeft: 12,
                    }}>
                      {!detail ? (
                        <div style={{ fontSize: 12, color: '#9ca3af' }}>Loading...</div>
                      ) : enabledAgents.length === 0 ? (
                        <div style={{ fontSize: 12, color: '#9ca3af' }}>활성화된 에이전트 없음</div>
                      ) : (
                        enabledAgents.map((agent) => {
                          const key = `${org.id}:${agent.agent_id}`
                          const isSelected = selected.has(key)

                          return (
                            <label
                              key={agent.id}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: 8,
                                padding: '6px 8px',
                                borderRadius: 6,
                                backgroundColor: isSelected ? '#f0fdf4' : 'transparent',
                                cursor: 'pointer',
                                marginBottom: 2,
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={() => toggleAgent(org.id, agent.agent_id)}
                                style={{ accentColor: '#059669' }}
                              />
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{
                                  fontSize: 13,
                                  fontWeight: 500,
                                  color: '#1f2937',
                                }}>
                                  {agent.display_name}
                                  {agent.is_clevel && (
                                    <span style={{
                                      marginLeft: 4,
                                      fontSize: 10,
                                      color: '#f59e0b',
                                    }}>
                                      {'\u2B50'}
                                    </span>
                                  )}
                                </div>
                                <div style={{
                                  fontSize: 11,
                                  color: '#6b7280',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                }}>
                                  {agent.role || agent.agent_id}
                                </div>
                              </div>
                            </label>
                          )
                        })
                      )}
                    </div>
                  )}
                </div>
              )
            })
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '12px 16px',
          borderTop: '1px solid #e5e7eb',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
        }}>
          <span style={{ fontSize: 12, color: '#6b7280' }}>
            {selected.size}개 선택됨
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={onClose}
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
              취소
            </button>
            <button
              onClick={handleConfirm}
              style={{
                padding: '8px 16px',
                borderRadius: 7,
                border: 'none',
                backgroundColor: '#2563eb',
                color: '#fff',
                fontWeight: 600,
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              확인
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
