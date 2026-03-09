import { useCallback, useEffect, useState } from 'react'
import { cloneOrg, createOrg, deleteOrg, getOrg, listOrgs } from '../lib/api'
import type { Organization, OrganizationDetail } from '../types'
import AgentEditor from './AgentEditor'
import ChapterEditor from './ChapterEditor'
import OrgChart from './OrgChart'
import OrgDesigner from './OrgDesigner'
import OrgEditor from './OrgEditor'
import OrgTemplateModal from './OrgTemplateModal'

interface OrgPanelProps {
  onOrgsChanged?: () => void
}

export default function OrgPanel({ onOrgsChanged }: OrgPanelProps = {}) {
  const [orgs, setOrgs] = useState<Organization[]>([])
  const [selectedOrg, setSelectedOrg] = useState<OrganizationDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [showTemplateModal, setShowTemplateModal] = useState(false)
  const [creatingOrg, setCreatingOrg] = useState(false)
  const [cloneName, setCloneName] = useState('')
  const [cloningId, setCloningId] = useState<string | null>(null)
  const [editingAgentId, setEditingAgentId] = useState<string | null>(null)
  const [editingChapterId, setEditingChapterId] = useState<string | null>(null)
  const [view, setView] = useState<'designer' | 'list' | 'chart'>('designer')
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const { items } = await listOrgs()
      setOrgs(items)
      onOrgsChanged?.()
    } catch {
      setError('Failed to load organizations')
    }
    setLoading(false)
  }, [onOrgsChanged])

  useEffect(() => { refresh() }, [refresh])

  const handleCreate = async (name: string, templateId: string) => {
    setError('')
    setCreatingOrg(true)
    try {
      const detail = await createOrg({ name, template_id: templateId })
      setShowTemplateModal(false)
      await refresh()
      // Automatically navigate to the new org
      setSelectedOrg(detail)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create org')
    } finally {
      setCreatingOrg(false)
    }
  }

  const handleClone = async (orgId: string) => {
    if (!cloneName.trim()) return
    setError('')
    try {
      const detail = await cloneOrg(orgId, { name: cloneName.trim() })
      setCloningId(null)
      setCloneName('')
      await refresh()
      setSelectedOrg(detail)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to clone org')
    }
  }

  const handleDelete = async (orgId: string) => {
    if (!confirm('Delete this organization?')) return
    setError('')
    try {
      await deleteOrg(orgId)
      if (selectedOrg?.id === orgId) setSelectedOrg(null)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete org')
    }
  }

  const handleSelectOrg = async (orgId: string) => {
    try {
      const detail = await getOrg(orgId)
      setSelectedOrg(detail)
      setEditingAgentId(null)
      setEditingChapterId(null)
    } catch {
      setError('Failed to load organization details')
    }
  }

  const editingAgent = selectedOrg?.agents.find(a => a.id === editingAgentId) ?? null
  const editingChapter = selectedOrg?.chapters?.find(c => c.id === editingChapterId) ?? null

  const refreshOrg = async () => {
    if (!selectedOrg) return
    const updated = await getOrg(selectedOrg.id)
    setSelectedOrg(updated)
  }

  if (loading) return <div style={{ padding: 24, color: '#9ca3af' }}>Loading...</div>

  // Chapter editor view
  if (selectedOrg && editingChapter) {
    const chapterAgents = selectedOrg.agents.filter(a => a.chapter_id === editingChapter.id)
    return (
      <ChapterEditor
        org={selectedOrg}
        chapter={editingChapter}
        agents={chapterAgents}
        onBack={() => setEditingChapterId(null)}
        onSaved={async () => {
          await refreshOrg()
          setEditingChapterId(null)
        }}
        onSelectAgent={(agentId) => {
          setEditingChapterId(null)
          setEditingAgentId(agentId)
        }}
      />
    )
  }

  // Agent editor view
  if (selectedOrg && editingAgent) {
    return (
      <AgentEditor
        org={selectedOrg}
        agent={editingAgent}
        onBack={() => setEditingAgentId(null)}
        onSaved={async () => {
          await refreshOrg()
          setEditingAgentId(null)
        }}
      />
    )
  }

  // Org detail view
  if (selectedOrg) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', gap: 8 }}>
          <button onClick={() => setSelectedOrg(null)} style={backBtnStyle}>Back</button>
          <span style={{ fontWeight: 600, fontSize: 15 }}>{selectedOrg.name}</span>
          {selectedOrg.is_preset && <span style={presetBadge}>Preset</span>}
          <div style={{ flex: 1 }} />
          <div style={{ display: 'flex', borderRadius: 6, border: '1px solid #d1d5db', overflow: 'hidden' }}>
            {(['designer', 'list', 'chart'] as const).map(v => (
              <button
                key={v}
                onClick={() => setView(v)}
                style={{
                  ...tabBtnStyle,
                  border: 'none',
                  borderRadius: 0,
                  backgroundColor: view === v ? '#2563eb' : '#fff',
                  color: view === v ? '#fff' : '#374151',
                }}
              >
                {v === 'designer' ? 'Designer' : v === 'list' ? 'Agent List' : 'Org Chart'}
              </button>
            ))}
          </div>
        </div>
        {view === 'designer' ? (
          <OrgDesigner
            org={selectedOrg}
            onSelectAgent={setEditingAgentId}
            onSelectChapter={setEditingChapterId}
            onRefresh={refreshOrg}
          />
        ) : view === 'chart' ? (
          <OrgChart org={selectedOrg} onSelectAgent={setEditingAgentId} />
        ) : (
          <OrgEditor
            org={selectedOrg}
            onSelectAgent={setEditingAgentId}
            onRefresh={refreshOrg}
          />
        )}
      </div>
    )
  }

  // Org list view
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ padding: '16px', borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontWeight: 700, fontSize: 16 }}>Organizations</span>
        <div style={{ flex: 1 }} />
        <button onClick={() => setShowTemplateModal(true)} style={createBtnStyle}>+ New</button>
      </div>

      {error && <div style={{ padding: '8px 16px', color: '#ef4444', fontSize: 13 }}>{error}</div>}

      {showTemplateModal && (
        <OrgTemplateModal
          onClose={() => setShowTemplateModal(false)}
          onCreate={handleCreate}
          creating={creatingOrg}
        />
      )}

      <div style={{ flex: 1, overflow: 'auto' }}>
        {orgs.map(org => (
          <div key={org.id} style={orgRowStyle}>
            <div
              style={{ flex: 1, cursor: 'pointer' }}
              onClick={() => handleSelectOrg(org.id)}
            >
              <div style={{ fontWeight: 500, fontSize: 14 }}>
                {org.name}
                {org.is_preset && <span style={presetBadge}>Preset</span>}
              </div>
              {org.description && (
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>{org.description}</div>
              )}
            </div>
            <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
              <button
                onClick={() => { setCloningId(org.id); setCloneName(`${org.name} (copy)`) }}
                style={smallBtnStyle}
                title="Clone"
              >Clone</button>
              {!org.is_preset && (
                <button
                  onClick={() => handleDelete(org.id)}
                  style={{ ...smallBtnStyle, color: '#ef4444' }}
                  title="Delete"
                >Delete</button>
              )}
            </div>
            {cloningId === org.id && (
              <div style={{ width: '100%', display: 'flex', gap: 8, marginTop: 8 }}>
                <input
                  type="text"
                  value={cloneName}
                  onChange={e => setCloneName(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') handleClone(org.id) }}
                  style={inputStyle}
                  autoFocus
                />
                <button onClick={() => handleClone(org.id)} style={createBtnStyle}>Clone</button>
                <button onClick={() => setCloningId(null)} style={cancelBtnStyle}>Cancel</button>
              </div>
            )}
          </div>
        ))}

        {orgs.length === 0 && (
          <div style={{ padding: 24, color: '#9ca3af', fontSize: 13, textAlign: 'center' }}>
            No organizations yet
          </div>
        )}
      </div>
    </div>
  )
}

const orgRowStyle: React.CSSProperties = {
  padding: '12px 16px',
  borderBottom: '1px solid #f3f4f6',
  display: 'flex',
  flexWrap: 'wrap',
  alignItems: 'center',
  gap: 8,
}

const presetBadge: React.CSSProperties = {
  fontSize: 10,
  padding: '1px 6px',
  marginLeft: 6,
  borderRadius: 4,
  backgroundColor: '#dbeafe',
  color: '#2563eb',
  fontWeight: 500,
}

const createBtnStyle: React.CSSProperties = {
  padding: '6px 12px',
  borderRadius: 6,
  border: 'none',
  backgroundColor: '#2563eb',
  color: '#fff',
  fontSize: 13,
  fontWeight: 500,
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

const smallBtnStyle: React.CSSProperties = {
  padding: '4px 8px',
  borderRadius: 4,
  border: '1px solid #d1d5db',
  backgroundColor: '#fff',
  fontSize: 12,
  cursor: 'pointer',
  color: '#374151',
}

const backBtnStyle: React.CSSProperties = {
  padding: '4px 10px',
  borderRadius: 4,
  border: '1px solid #d1d5db',
  backgroundColor: '#fff',
  fontSize: 13,
  cursor: 'pointer',
}

const tabBtnStyle: React.CSSProperties = {
  padding: '4px 10px',
  borderRadius: 4,
  border: '1px solid #d1d5db',
  backgroundColor: '#fff',
  fontSize: 12,
  cursor: 'pointer',
}

const inputStyle: React.CSSProperties = {
  flex: 1,
  padding: '6px 10px',
  borderRadius: 6,
  border: '1px solid #d1d5db',
  fontSize: 13,
  outline: 'none',
}
