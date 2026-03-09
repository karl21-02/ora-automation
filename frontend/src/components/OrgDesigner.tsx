import { useMemo, useState } from 'react'
import { createChapter, createSilo, deleteChapter, deleteSilo, updateAgent, updateOrg } from '../lib/api'
import type { OrgAgent, OrganizationDetail } from '../types'

interface Props {
  org: OrganizationDetail
  onSelectAgent: (agentId: string) => void
  onSelectChapter: (chapterId: string) => void
  onRefresh: () => Promise<void>
}

export default function OrgDesigner({ org, onSelectAgent, onSelectChapter, onRefresh }: Props) {
  const [mode, setMode] = useState<'basic' | 'advanced'>('basic')
  const [addingSilo, setAddingSilo] = useState(false)
  const [newSiloName, setNewSiloName] = useState('')
  const [addingChapter, setAddingChapter] = useState(false)
  const [newChapterName, setNewChapterName] = useState('')
  const [assignDropdown, setAssignDropdown] = useState<string | null>(null)
  const [error, setError] = useState('')

  // Drag & Drop state
  const [draggingAgentId, setDraggingAgentId] = useState<string | null>(null)
  const [dragOverTarget, setDragOverTarget] = useState<string | null>(null) // silo id or 'clevel'

  // Pipeline settings state
  const pp = org.pipeline_params || {}
  const [pipelineForm, setPipelineForm] = useState({
    l1_max_rounds: (pp.l1_max_rounds as number) ?? 5,
    l2_max_rounds: (pp.l2_max_rounds as number) ?? 3,
    l3_max_rounds: (pp.l3_max_rounds as number) ?? 3,
    convergence_threshold: (pp.convergence_threshold as number) ?? 0.15,
    top_k: (pp.top_k as number) ?? 6,
    profile: (pp.profile as string) ?? 'standard',
    service_scope: ((pp.service_scope as string[]) ?? []).join(', '),
  })

  const readonly = org.is_preset

  const clevelAgents = useMemo(() => org.agents.filter(a => a.is_clevel), [org.agents])

  const siloAgentMap = useMemo(() => {
    const map: Record<string, OrgAgent[]> = {}
    for (const silo of org.silos) map[silo.id] = []
    for (const agent of org.agents) {
      if (agent.silo_id && !agent.is_clevel && map[agent.silo_id]) {
        map[agent.silo_id].push(agent)
      }
    }
    return map
  }, [org.agents, org.silos])

  const unassignedAgents = useMemo(
    () => org.agents.filter(a => !a.silo_id && !a.is_clevel),
    [org.agents],
  )

  const chapterAgentMap = useMemo(() => {
    const map: Record<string, OrgAgent[]> = {}
    for (const ch of org.chapters) map[ch.id] = []
    for (const agent of org.agents) {
      if (agent.chapter_id && map[agent.chapter_id]) {
        map[agent.chapter_id].push(agent)
      }
    }
    return map
  }, [org.agents, org.chapters])

  const handleAssignToSilo = async (agentId: string, siloId: string) => {
    setError('')
    try {
      await updateAgent(org.id, agentId, { silo_id: siloId })
      setAssignDropdown(null)
      await onRefresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to assign')
    }
  }

  const handleUnassignFromSilo = async (agentId: string) => {
    setError('')
    try {
      await updateAgent(org.id, agentId, { silo_id: null })
      await onRefresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to unassign')
    }
  }

  // Drag & Drop handlers
  const handleDragStart = (e: React.DragEvent, agentId: string) => {
    e.dataTransfer.setData('agentId', agentId)
    e.dataTransfer.effectAllowed = 'move'
    setDraggingAgentId(agentId)
  }

  const handleDragEnd = () => {
    setDraggingAgentId(null)
    setDragOverTarget(null)
  }

  const handleDragOver = (e: React.DragEvent, targetId: string) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOverTarget(targetId)
  }

  const handleDragLeave = () => {
    setDragOverTarget(null)
  }

  const handleDropOnSilo = async (e: React.DragEvent, siloId: string) => {
    e.preventDefault()
    const agentId = e.dataTransfer.getData('agentId')
    if (!agentId) return
    setDragOverTarget(null)
    setDraggingAgentId(null)
    await handleAssignToSilo(agentId, siloId)
  }

  const handleDropOnClevel = async (e: React.DragEvent) => {
    e.preventDefault()
    const agentId = e.dataTransfer.getData('agentId')
    if (!agentId) return
    setDragOverTarget(null)
    setDraggingAgentId(null)
    setError('')
    try {
      await updateAgent(org.id, agentId, { is_clevel: true, silo_id: null })
      await onRefresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to promote to C-Level')
    }
  }

  const handleDropOnUnassigned = async (e: React.DragEvent) => {
    e.preventDefault()
    const agentId = e.dataTransfer.getData('agentId')
    if (!agentId) return
    setDragOverTarget(null)
    setDraggingAgentId(null)
    setError('')
    try {
      await updateAgent(org.id, agentId, { is_clevel: false, silo_id: null })
      await onRefresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to unassign')
    }
  }

  const handleCreateSilo = async () => {
    if (!newSiloName.trim()) return
    setError('')
    try {
      await createSilo(org.id, { name: newSiloName.trim(), sort_order: org.silos.length })
      setNewSiloName('')
      setAddingSilo(false)
      await onRefresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create silo')
    }
  }

  const handleDeleteSilo = async (siloId: string, name: string) => {
    if (!confirm(`Delete silo "${name}"? Agents will be unassigned.`)) return
    setError('')
    try {
      await deleteSilo(org.id, siloId)
      await onRefresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete silo')
    }
  }

  const handleCreateChapter = async () => {
    if (!newChapterName.trim()) return
    setError('')
    try {
      await createChapter(org.id, { name: newChapterName.trim(), sort_order: org.chapters.length })
      setNewChapterName('')
      setAddingChapter(false)
      await onRefresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create chapter')
    }
  }

  const handleDeleteChapter = async (chapterId: string, name: string) => {
    if (!confirm(`Delete chapter "${name}"? Agents will be unassigned.`)) return
    setError('')
    try {
      await deleteChapter(org.id, chapterId)
      await onRefresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete chapter')
    }
  }

  const handleSavePipelineParams = async () => {
    setError('')
    try {
      await updateOrg(org.id, {
        pipeline_params: {
          l1_max_rounds: pipelineForm.l1_max_rounds,
          l2_max_rounds: pipelineForm.l2_max_rounds,
          l3_max_rounds: pipelineForm.l3_max_rounds,
          convergence_threshold: pipelineForm.convergence_threshold,
          top_k: pipelineForm.top_k,
          profile: pipelineForm.profile,
          service_scope: pipelineForm.service_scope.split(',').map(s => s.trim()).filter(Boolean),
        },
      })
      await onRefresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save pipeline params')
    }
  }

  const setPP = (key: string, value: unknown) => setPipelineForm(prev => ({ ...prev, [key]: value }))

  return (
    <div style={{ flex: 1, overflow: 'auto', padding: '12px 16px' }}>
      {/* Header with mode toggle */}
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16, gap: 8 }}>
        <span style={{ fontWeight: 700, fontSize: 16 }}>{org.name}</span>
        {readonly && <span style={presetBadge}>Preset</span>}
        <div style={{ flex: 1 }} />
        <div style={{ display: 'flex', borderRadius: 6, border: '1px solid #d1d5db', overflow: 'hidden' }}>
          <button onClick={() => setMode('basic')} style={modeBtn(mode === 'basic')}>Basic</button>
          <button onClick={() => setMode('advanced')} style={modeBtn(mode === 'advanced')}>Advanced</button>
        </div>
      </div>

      {error && <div style={{ padding: '8px 0', color: '#ef4444', fontSize: 13 }}>{error}</div>}

      {/* C-LEVEL Section */}
      <Section title="C-LEVEL" count={clevelAgents.length}>
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: 6,
            minHeight: 40,
            padding: 8,
            borderRadius: 8,
            border: dragOverTarget === 'clevel' ? '2px dashed #2563eb' : '2px dashed transparent',
            backgroundColor: dragOverTarget === 'clevel' ? '#eff6ff' : 'transparent',
            transition: 'all 0.15s ease',
          }}
          onDragOver={!readonly ? (e) => handleDragOver(e, 'clevel') : undefined}
          onDragLeave={!readonly ? handleDragLeave : undefined}
          onDrop={!readonly ? handleDropOnClevel : undefined}
        >
          {clevelAgents.length === 0 && !draggingAgentId && (
            <span style={{ fontSize: 12, color: '#9ca3af' }}>No C-Level agents</span>
          )}
          {clevelAgents.length === 0 && draggingAgentId && (
            <span style={{ fontSize: 12, color: '#6b7280' }}>Drop here to promote to C-Level</span>
          )}
          {clevelAgents.map(agent => (
            <AgentChip
              key={agent.id}
              agent={agent}
              onClick={() => onSelectAgent(agent.id)}
              draggable={!readonly}
              dragging={draggingAgentId === agent.id}
              onDragStart={!readonly ? (e) => handleDragStart(e, agent.id) : undefined}
              onDragEnd={!readonly ? handleDragEnd : undefined}
            />
          ))}
        </div>
      </Section>

      {/* SILOS Section */}
      <Section title="SILOS" count={org.silos.length}>
        {org.silos.map(silo => (
          <div
            key={silo.id}
            style={{
              ...siloCardStyle,
              borderLeftColor: silo.color,
              border: dragOverTarget === silo.id ? '2px dashed #2563eb' : '1px solid #e5e7eb',
              borderLeft: `4px solid ${silo.color}`,
              backgroundColor: dragOverTarget === silo.id ? '#eff6ff' : '#fafafa',
              transition: 'all 0.15s ease',
            }}
            onDragOver={!readonly ? (e) => handleDragOver(e, silo.id) : undefined}
            onDragLeave={!readonly ? handleDragLeave : undefined}
            onDrop={!readonly ? (e) => handleDropOnSilo(e, silo.id) : undefined}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>{silo.name}</span>
              {silo.description && <span style={{ fontSize: 11, color: '#9ca3af' }}>{silo.description}</span>}
              <div style={{ flex: 1 }} />
              {!readonly && (
                <button onClick={() => handleDeleteSilo(silo.id, silo.name)} style={xBtnStyle} title="Delete silo">X</button>
              )}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8, minHeight: 28 }}>
              {(siloAgentMap[silo.id] || []).map(agent => (
                <AgentChip
                  key={agent.id}
                  agent={agent}
                  onClick={() => onSelectAgent(agent.id)}
                  onRemove={!readonly ? () => handleUnassignFromSilo(agent.id) : undefined}
                  draggable={!readonly}
                  dragging={draggingAgentId === agent.id}
                  onDragStart={!readonly ? (e) => handleDragStart(e, agent.id) : undefined}
                  onDragEnd={!readonly ? handleDragEnd : undefined}
                />
              ))}
              {(siloAgentMap[silo.id] || []).length === 0 && !draggingAgentId && (
                <span style={{ fontSize: 12, color: '#9ca3af' }}>No agents</span>
              )}
              {(siloAgentMap[silo.id] || []).length === 0 && draggingAgentId && (
                <span style={{ fontSize: 12, color: '#6b7280' }}>Drop here to assign</span>
              )}
            </div>
            {!readonly && !draggingAgentId && (
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                {assignDropdown === silo.id ? (
                  <>
                    <select
                      onChange={e => { if (e.target.value) handleAssignToSilo(e.target.value, silo.id) }}
                      style={selectStyle}
                      autoFocus
                    >
                      <option value="">Select agent...</option>
                      {unassignedAgents.map(a => (
                        <option key={a.id} value={a.id}>{a.display_name}</option>
                      ))}
                    </select>
                    <button onClick={() => setAssignDropdown(null)} style={xBtnStyle}>Cancel</button>
                  </>
                ) : (
                  <button onClick={() => setAssignDropdown(silo.id)} style={addSmallBtnStyle} disabled={unassignedAgents.length === 0}>
                    + Assign Agent
                  </button>
                )}
              </div>
            )}
          </div>
        ))}

        {!readonly && (
          addingSilo ? (
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <input
                value={newSiloName}
                onChange={e => setNewSiloName(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleCreateSilo() }}
                placeholder="Silo name"
                style={inputStyle}
                autoFocus
              />
              <button onClick={handleCreateSilo} style={saveBtnStyle}>Add</button>
              <button onClick={() => { setAddingSilo(false); setNewSiloName('') }} style={cancelBtnStyle}>Cancel</button>
            </div>
          ) : (
            <button onClick={() => setAddingSilo(true)} style={{ ...addSmallBtnStyle, marginTop: 8 }}>+ Add Silo</button>
          )
        )}
      </Section>

      {/* UNASSIGNED Section */}
      {(unassignedAgents.length > 0 || draggingAgentId) && (
        <Section title="UNASSIGNED" count={unassignedAgents.length}>
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 6,
              minHeight: 40,
              padding: 8,
              borderRadius: 8,
              border: dragOverTarget === 'unassigned' ? '2px dashed #2563eb' : '2px dashed transparent',
              backgroundColor: dragOverTarget === 'unassigned' ? '#eff6ff' : 'transparent',
              transition: 'all 0.15s ease',
            }}
            onDragOver={!readonly ? (e) => handleDragOver(e, 'unassigned') : undefined}
            onDragLeave={!readonly ? handleDragLeave : undefined}
            onDrop={!readonly ? handleDropOnUnassigned : undefined}
          >
            {unassignedAgents.length === 0 && draggingAgentId && (
              <span style={{ fontSize: 12, color: '#6b7280' }}>Drop here to unassign</span>
            )}
            {unassignedAgents.map(agent => (
              <AgentChip
                key={agent.id}
                agent={agent}
                onClick={() => onSelectAgent(agent.id)}
                draggable={!readonly}
                dragging={draggingAgentId === agent.id}
                onDragStart={!readonly ? (e) => handleDragStart(e, agent.id) : undefined}
                onDragEnd={!readonly ? handleDragEnd : undefined}
              />
            ))}
          </div>
        </Section>
      )}

      {/* Advanced mode sections */}
      {mode === 'advanced' && (
        <>
          {/* CHAPTERS Section */}
          <Section title="CHAPTERS" count={org.chapters.length}>
            {org.chapters.map(ch => (
              <div key={ch.id} style={{ ...chapterCardStyle, borderLeftColor: ch.color }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 16 }}>{ch.icon}</span>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{ch.name}</span>
                  <div style={{ flex: 1 }} />
                  <button onClick={() => onSelectChapter(ch.id)} style={editBtnStyle}>Edit</button>
                  {!readonly && (
                    <button onClick={() => handleDeleteChapter(ch.id, ch.name)} style={xBtnStyle} title="Delete chapter">X</button>
                  )}
                </div>
                {ch.chapter_prompt && (
                  <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4, whiteSpace: 'pre-wrap', maxHeight: 40, overflow: 'hidden' }}>
                    {ch.chapter_prompt}
                  </div>
                )}
                {(chapterAgentMap[ch.id] || []).length > 0 && (
                  <div style={{ fontSize: 11, color: '#9ca3af' }}>
                    Members: {(chapterAgentMap[ch.id] || []).map(a => a.display_name).join(', ')}
                  </div>
                )}
              </div>
            ))}

            {!readonly && (
              addingChapter ? (
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <input
                    value={newChapterName}
                    onChange={e => setNewChapterName(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') handleCreateChapter() }}
                    placeholder="Chapter name"
                    style={inputStyle}
                    autoFocus
                  />
                  <button onClick={handleCreateChapter} style={saveBtnStyle}>Add</button>
                  <button onClick={() => { setAddingChapter(false); setNewChapterName('') }} style={cancelBtnStyle}>Cancel</button>
                </div>
              ) : (
                <button onClick={() => setAddingChapter(true)} style={{ ...addSmallBtnStyle, marginTop: 8 }}>+ Add Chapter</button>
              )
            )}
          </Section>

          {/* PIPELINE SETTINGS Section */}
          <Section title="PIPELINE SETTINGS">
            <div style={pipelineGridStyle}>
              <PipelineField label="L1 Max Rounds">
                <input type="number" value={pipelineForm.l1_max_rounds} onChange={e => setPP('l1_max_rounds', Number(e.target.value))} style={inputStyle} disabled={readonly} min={1} max={20} />
              </PipelineField>
              <PipelineField label="L2 Max Rounds">
                <input type="number" value={pipelineForm.l2_max_rounds} onChange={e => setPP('l2_max_rounds', Number(e.target.value))} style={inputStyle} disabled={readonly} min={1} max={20} />
              </PipelineField>
              <PipelineField label="L3 Max Rounds">
                <input type="number" value={pipelineForm.l3_max_rounds} onChange={e => setPP('l3_max_rounds', Number(e.target.value))} style={inputStyle} disabled={readonly} min={1} max={20} />
              </PipelineField>
              <PipelineField label="Convergence">
                <input type="number" value={pipelineForm.convergence_threshold} onChange={e => setPP('convergence_threshold', Number(e.target.value))} style={inputStyle} disabled={readonly} min={0} max={1} step={0.01} />
              </PipelineField>
              <PipelineField label="Top K">
                <input type="number" value={pipelineForm.top_k} onChange={e => setPP('top_k', Number(e.target.value))} style={inputStyle} disabled={readonly} min={1} max={20} />
              </PipelineField>
              <PipelineField label="Profile">
                <select value={pipelineForm.profile} onChange={e => setPP('profile', e.target.value)} style={inputStyle} disabled={readonly}>
                  <option value="standard">standard</option>
                  <option value="strict">strict</option>
                </select>
              </PipelineField>
            </div>
            <PipelineField label="Service Scope (comma-separated)">
              <input value={pipelineForm.service_scope} onChange={e => setPP('service_scope', e.target.value)} style={inputStyle} disabled={readonly} placeholder="b2b, ai, telecom" />
            </PipelineField>
            {!readonly && (
              <button onClick={handleSavePipelineParams} style={{ ...saveBtnStyle, marginTop: 8 }}>Save Pipeline Settings</button>
            )}
          </Section>
        </>
      )}
    </div>
  )
}

// ── Sub-components ──

function Section({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
        {title}{count !== undefined && ` (${count})`}
      </div>
      {children}
    </div>
  )
}

function AgentChip({
  agent,
  onClick,
  onRemove,
  draggable,
  dragging,
  onDragStart,
  onDragEnd,
}: {
  agent: OrgAgent
  onClick: () => void
  onRemove?: () => void
  draggable?: boolean
  dragging?: boolean
  onDragStart?: (e: React.DragEvent) => void
  onDragEnd?: () => void
}) {
  return (
    <span
      style={{
        ...chipStyle,
        cursor: draggable ? 'grab' : 'default',
        opacity: dragging ? 0.5 : 1,
        transform: dragging ? 'scale(0.95)' : 'scale(1)',
        transition: 'all 0.15s ease',
      }}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
    >
      <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: agent.enabled ? '#22c55e' : '#d1d5db', display: 'inline-block' }} />
      <span onClick={onClick} style={{ cursor: 'pointer' }}>{agent.display_name}</span>
      {onRemove && (
        <span
          onClick={e => { e.stopPropagation(); onRemove() }}
          style={{ cursor: 'pointer', color: '#9ca3af', fontSize: 11, marginLeft: 2 }}
        >x</span>
      )}
    </span>
  )
}

function PipelineField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 2, fontWeight: 500 }}>{label}</div>
      {children}
    </div>
  )
}

// ── Styles ──

const modeBtn = (active: boolean): React.CSSProperties => ({
  padding: '4px 12px',
  border: 'none',
  fontSize: 12,
  fontWeight: 500,
  cursor: 'pointer',
  backgroundColor: active ? '#2563eb' : '#fff',
  color: active ? '#fff' : '#374151',
})

const presetBadge: React.CSSProperties = {
  fontSize: 10,
  padding: '1px 6px',
  borderRadius: 4,
  backgroundColor: '#dbeafe',
  color: '#2563eb',
  fontWeight: 500,
}

const siloCardStyle: React.CSSProperties = {
  padding: '10px 12px',
  borderRadius: 8,
  border: '1px solid #e5e7eb',
  borderLeft: '4px solid #6b7280',
  marginBottom: 8,
  backgroundColor: '#fafafa',
}

const chapterCardStyle: React.CSSProperties = {
  padding: '10px 12px',
  borderRadius: 8,
  border: '1px solid #e5e7eb',
  borderLeft: '4px solid #6b7280',
  marginBottom: 8,
  backgroundColor: '#fafafa',
}

const chipStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 4,
  padding: '3px 8px',
  borderRadius: 12,
  backgroundColor: '#f3f4f6',
  fontSize: 12,
  fontWeight: 500,
}

const xBtnStyle: React.CSSProperties = {
  padding: '2px 6px',
  borderRadius: 4,
  border: '1px solid #d1d5db',
  backgroundColor: '#fff',
  fontSize: 11,
  cursor: 'pointer',
  color: '#ef4444',
}

const editBtnStyle: React.CSSProperties = {
  padding: '2px 8px',
  borderRadius: 4,
  border: '1px solid #d1d5db',
  backgroundColor: '#fff',
  fontSize: 11,
  cursor: 'pointer',
  color: '#2563eb',
}

const addSmallBtnStyle: React.CSSProperties = {
  padding: '4px 10px',
  borderRadius: 4,
  border: '1px solid #d1d5db',
  backgroundColor: '#fff',
  fontSize: 12,
  cursor: 'pointer',
  color: '#374151',
}

const selectStyle: React.CSSProperties = {
  padding: '4px 8px',
  borderRadius: 4,
  border: '1px solid #d1d5db',
  fontSize: 12,
  outline: 'none',
}

const inputStyle: React.CSSProperties = {
  flex: 1,
  padding: '6px 10px',
  borderRadius: 6,
  border: '1px solid #d1d5db',
  fontSize: 13,
  outline: 'none',
  boxSizing: 'border-box' as const,
}

const saveBtnStyle: React.CSSProperties = {
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

const pipelineGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr 1fr',
  gap: '0 16px',
}
