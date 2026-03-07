import { useState } from 'react'
import { updateChapter } from '../lib/api'
import type { OrgAgent, OrgChapter, OrganizationDetail } from '../types'

interface Props {
  org: OrganizationDetail
  chapter: OrgChapter
  agents: OrgAgent[]
  onBack: () => void
  onSaved: () => Promise<void>
  onSelectAgent: (agentId: string) => void
}

export default function ChapterEditor({ org, chapter, agents, onBack, onSaved, onSelectAgent }: Props) {
  const [form, setForm] = useState({
    name: chapter.name,
    icon: chapter.icon,
    color: chapter.color,
    description: chapter.description || '',
    chapter_prompt: chapter.chapter_prompt,
    shared_directives: chapter.shared_directives.join('\n'),
    shared_constraints: chapter.shared_constraints.join('\n'),
    shared_decision_focus: chapter.shared_decision_focus.join('\n'),
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const readonly = org.is_preset

  const handleSave = async () => {
    if (readonly) return
    setSaving(true)
    setError('')
    try {
      await updateChapter(org.id, chapter.id, {
        name: form.name,
        icon: form.icon,
        color: form.color,
        description: form.description || undefined,
        chapter_prompt: form.chapter_prompt,
        shared_directives: form.shared_directives.split('\n').filter(Boolean),
        shared_constraints: form.shared_constraints.split('\n').filter(Boolean),
        shared_decision_focus: form.shared_decision_focus.split('\n').filter(Boolean),
      })
      await onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    }
    setSaving(false)
  }

  const set = (key: string, value: string) => setForm(prev => ({ ...prev, [key]: value }))

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', gap: 8 }}>
        <button onClick={onBack} style={backBtnStyle}>Back</button>
        <span style={{ fontSize: 18 }}>{chapter.icon}</span>
        <span style={{ fontWeight: 600, fontSize: 15 }}>{chapter.name}</span>
        {readonly && <span style={presetBadge}>Read-only</span>}
        <div style={{ flex: 1 }} />
        {!readonly && (
          <button onClick={handleSave} disabled={saving} style={saveBtnStyle}>
            {saving ? 'Saving...' : 'Save'}
          </button>
        )}
      </div>

      {error && <div style={{ padding: '8px 16px', color: '#ef4444', fontSize: 13 }}>{error}</div>}

      <div style={{ flex: 1, overflow: 'auto', padding: '16px' }}>
        <div style={gridStyle}>
          <Field label="Name">
            <input value={form.name} onChange={e => set('name', e.target.value)} style={inputStyle} disabled={readonly} />
          </Field>
          <Field label="Icon (emoji)">
            <input value={form.icon} onChange={e => set('icon', e.target.value)} style={inputStyle} disabled={readonly} />
          </Field>
          <Field label="Color">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input type="color" value={form.color} onChange={e => set('color', e.target.value)} disabled={readonly} style={{ width: 32, height: 28, border: 'none', cursor: readonly ? 'default' : 'pointer' }} />
              <input value={form.color} onChange={e => set('color', e.target.value)} style={{ ...inputStyle, flex: 1 }} disabled={readonly} />
            </div>
          </Field>
        </div>

        <Field label="Description" full>
          <textarea value={form.description} onChange={e => set('description', e.target.value)} style={textareaStyle} rows={2} disabled={readonly} />
        </Field>

        <Field label="Chapter Prompt" full>
          <textarea value={form.chapter_prompt} onChange={e => set('chapter_prompt', e.target.value)} style={{ ...textareaStyle, fontFamily: 'monospace' }} rows={6} disabled={readonly} />
        </Field>

        <Field label="Shared Directives (one per line)" full>
          <textarea value={form.shared_directives} onChange={e => set('shared_directives', e.target.value)} style={textareaStyle} rows={4} disabled={readonly} />
        </Field>

        <Field label="Shared Constraints (one per line)" full>
          <textarea value={form.shared_constraints} onChange={e => set('shared_constraints', e.target.value)} style={textareaStyle} rows={4} disabled={readonly} />
        </Field>

        <Field label="Shared Decision Focus (one per line)" full>
          <textarea value={form.shared_decision_focus} onChange={e => set('shared_decision_focus', e.target.value)} style={textareaStyle} rows={4} disabled={readonly} />
        </Field>

        <div style={{ marginTop: 16 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>Members ({agents.length})</div>
          {agents.length === 0 ? (
            <div style={{ fontSize: 12, color: '#9ca3af' }}>No agents in this chapter</div>
          ) : (
            agents.map(agent => (
              <div
                key={agent.id}
                onClick={() => onSelectAgent(agent.id)}
                style={agentRowStyle}
              >
                <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: agent.enabled ? '#22c55e' : '#d1d5db', flexShrink: 0 }} />
                <span style={{ fontSize: 13, fontWeight: 500 }}>{agent.display_name}</span>
                <span style={{ fontSize: 11, color: '#9ca3af' }}>{agent.agent_id}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

function Field({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return (
    <div style={{ marginBottom: 12, ...(full ? {} : {}) }}>
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 4, fontWeight: 500 }}>{label}</div>
      {children}
    </div>
  )
}

const gridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr 1fr',
  gap: '0 16px',
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '6px 10px',
  borderRadius: 6,
  border: '1px solid #d1d5db',
  fontSize: 13,
  outline: 'none',
  boxSizing: 'border-box',
}

const textareaStyle: React.CSSProperties = {
  width: '100%',
  padding: '8px 10px',
  borderRadius: 6,
  border: '1px solid #d1d5db',
  fontSize: 13,
  outline: 'none',
  resize: 'vertical',
  boxSizing: 'border-box',
}

const backBtnStyle: React.CSSProperties = {
  padding: '4px 10px',
  borderRadius: 4,
  border: '1px solid #d1d5db',
  backgroundColor: '#fff',
  fontSize: 13,
  cursor: 'pointer',
}

const saveBtnStyle: React.CSSProperties = {
  padding: '6px 16px',
  borderRadius: 6,
  border: 'none',
  backgroundColor: '#2563eb',
  color: '#fff',
  fontSize: 13,
  fontWeight: 500,
  cursor: 'pointer',
}

const presetBadge: React.CSSProperties = {
  fontSize: 10,
  padding: '1px 6px',
  borderRadius: 4,
  backgroundColor: '#fef3c7',
  color: '#92400e',
  fontWeight: 500,
}

const agentRowStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  padding: '6px 10px',
  borderRadius: 6,
  cursor: 'pointer',
  marginBottom: 2,
}
