import { useMemo, useState } from 'react'
import { createAgent, deleteAgent, updateOrg } from '../lib/api'
import type { OrganizationDetail } from '../types'

interface Props {
  org: OrganizationDetail
  onSelectAgent: (agentId: string) => void
  onRefresh: () => Promise<void>
}

export default function OrgEditor({ org, onSelectAgent, onRefresh }: Props) {
  const [editingDesc, setEditingDesc] = useState(false)
  const [desc, setDesc] = useState(org.description || '')
  const [addingAgent, setAddingAgent] = useState(false)
  const [newAgentId, setNewAgentId] = useState('')
  const [newAgentName, setNewAgentName] = useState('')
  const [error, setError] = useState('')

  const teamGroups = useMemo(() => {
    const groups: Record<string, typeof org.agents> = {}
    for (const agent of org.agents) {
      const team = agent.team || 'ungrouped'
      if (!groups[team]) groups[team] = []
      groups[team].push(agent)
    }
    return groups
  }, [org.agents])

  const handleSaveDesc = async () => {
    try {
      await updateOrg(org.id, { description: desc })
      setEditingDesc(false)
      await onRefresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update')
    }
  }

  const handleAddAgent = async () => {
    if (!newAgentId.trim() || !newAgentName.trim()) return
    setError('')
    try {
      await createAgent(org.id, {
        agent_id: newAgentId.trim(),
        display_name: newAgentName.trim(),
        display_name_ko: '',
        role: '',
        tier: 1,
        domain: null,
        team: '',
        personality: {},
        behavioral_directives: [],
        constraints: [],
        decision_focus: [],
        weights: {},
        trust_map: {},
        system_prompt_template: null,
        enabled: true,
        sort_order: org.agents.length,
      })
      setAddingAgent(false)
      setNewAgentId('')
      setNewAgentName('')
      await onRefresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create agent')
    }
  }

  const handleDeleteAgent = async (agentId: string, name: string) => {
    if (!confirm(`Delete agent "${name}"?`)) return
    try {
      await deleteAgent(org.id, agentId)
      await onRefresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete agent')
    }
  }

  const tierColor = (tier: number) => {
    switch (tier) {
      case 4: return '#dc2626'
      case 3: return '#ea580c'
      case 2: return '#2563eb'
      default: return '#6b7280'
    }
  }

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: '12px 16px' }}>
      {error && <div style={{ padding: '8px 0', color: '#ef4444', fontSize: 13 }}>{error}</div>}

      {/* Description */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4 }}>Description</div>
        {editingDesc ? (
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              type="text"
              value={desc}
              onChange={e => setDesc(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') handleSaveDesc() }}
              style={inputStyle}
              autoFocus
            />
            <button onClick={handleSaveDesc} style={saveBtnStyle}>Save</button>
            <button onClick={() => setEditingDesc(false)} style={cancelBtnStyle}>Cancel</button>
          </div>
        ) : (
          <div
            onClick={() => !org.is_preset && setEditingDesc(true)}
            style={{ fontSize: 13, color: org.description ? '#374151' : '#9ca3af', cursor: org.is_preset ? 'default' : 'pointer' }}
          >
            {org.description || '(no description)'}
          </div>
        )}
      </div>

      {/* Agents by team */}
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 12 }}>
        <span style={{ fontWeight: 600, fontSize: 14 }}>Agents ({org.agents.length})</span>
        <div style={{ flex: 1 }} />
        {!org.is_preset && (
          <button onClick={() => setAddingAgent(true)} style={addBtnStyle}>+ Add Agent</button>
        )}
      </div>

      {addingAgent && (
        <div style={{ display: 'flex', gap: 8, marginBottom: 12, padding: 12, backgroundColor: '#f9fafb', borderRadius: 8 }}>
          <input
            placeholder="agent_id (e.g. Analyst)"
            value={newAgentId}
            onChange={e => setNewAgentId(e.target.value)}
            style={inputStyle}
            autoFocus
          />
          <input
            placeholder="Display name"
            value={newAgentName}
            onChange={e => setNewAgentName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleAddAgent() }}
            style={inputStyle}
          />
          <button onClick={handleAddAgent} style={saveBtnStyle}>Add</button>
          <button onClick={() => setAddingAgent(false)} style={cancelBtnStyle}>Cancel</button>
        </div>
      )}

      {Object.entries(teamGroups).sort(([a], [b]) => a.localeCompare(b)).map(([team, agents]) => (
        <div key={team} style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#6b7280', marginBottom: 6, textTransform: 'capitalize' }}>
            {team}
          </div>
          {agents.map(agent => (
            <div
              key={agent.id}
              style={agentRowStyle}
              onClick={() => onSelectAgent(agent.id)}
            >
              <div style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                backgroundColor: agent.enabled ? '#22c55e' : '#d1d5db',
                flexShrink: 0,
              }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 500 }}>
                  {agent.display_name}
                  {agent.display_name_ko && (
                    <span style={{ color: '#6b7280', fontWeight: 400, marginLeft: 4 }}>
                      {agent.display_name_ko}
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: '#9ca3af' }}>
                  {agent.agent_id} &middot; {agent.role || 'no role'}
                </div>
              </div>
              <span style={{
                fontSize: 10,
                padding: '1px 6px',
                borderRadius: 4,
                border: `1px solid ${tierColor(agent.tier)}`,
                color: tierColor(agent.tier),
                fontWeight: 600,
              }}>
                T{agent.tier}
              </span>
              {!org.is_preset && (
                <button
                  onClick={e => { e.stopPropagation(); handleDeleteAgent(agent.id, agent.display_name) }}
                  style={{ ...smallBtnStyle, color: '#ef4444' }}
                  title="Delete"
                >X</button>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

const agentRowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '8px 12px',
  borderRadius: 6,
  cursor: 'pointer',
  marginBottom: 2,
  transition: 'background-color 0.15s',
}

const inputStyle: React.CSSProperties = {
  flex: 1,
  padding: '6px 10px',
  borderRadius: 6,
  border: '1px solid #d1d5db',
  fontSize: 13,
  outline: 'none',
}

const saveBtnStyle: React.CSSProperties = {
  padding: '6px 12px',
  borderRadius: 6,
  border: 'none',
  backgroundColor: '#2563eb',
  color: '#fff',
  fontSize: 13,
  cursor: 'pointer',
}

const cancelBtnStyle: React.CSSProperties = {
  padding: '6px 12px',
  borderRadius: 6,
  border: '1px solid #d1d5db',
  backgroundColor: '#fff',
  color: '#374151',
  fontSize: 13,
  cursor: 'pointer',
}

const addBtnStyle: React.CSSProperties = {
  padding: '4px 10px',
  borderRadius: 4,
  border: '1px solid #d1d5db',
  backgroundColor: '#fff',
  fontSize: 12,
  cursor: 'pointer',
}

const smallBtnStyle: React.CSSProperties = {
  padding: '2px 6px',
  borderRadius: 4,
  border: '1px solid #d1d5db',
  backgroundColor: '#fff',
  fontSize: 11,
  cursor: 'pointer',
  color: '#374151',
}
