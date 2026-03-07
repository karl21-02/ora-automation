import { useState } from 'react'
import { updateAgent } from '../lib/api'
import type { OrgAgent, OrganizationDetail } from '../types'

interface Props {
  org: OrganizationDetail
  agent: OrgAgent
  onBack: () => void
  onSaved: () => Promise<void>
}

export default function AgentEditor({ org, agent, onBack, onSaved }: Props) {
  const [form, setForm] = useState({
    display_name: agent.display_name,
    display_name_ko: agent.display_name_ko,
    role: agent.role,
    tier: agent.tier,
    domain: agent.domain || '',
    team: agent.team,
    silo_id: agent.silo_id || '',
    chapter_id: agent.chapter_id || '',
    is_clevel: agent.is_clevel ?? false,
    weight_score: agent.weight_score ?? 1.0,
    enabled: agent.enabled,
    behavioral_directives: agent.behavioral_directives.join('\n'),
    constraints: agent.constraints.join('\n'),
    decision_focus: agent.decision_focus.join('\n'),
    weights_json: JSON.stringify(agent.weights, null, 2),
    trust_map_json: JSON.stringify(agent.trust_map, null, 2),
    system_prompt_template: agent.system_prompt_template || '',
  })

  const selectedChapter = org.chapters?.find(c => c.id === form.chapter_id)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const readonly = org.is_preset

  const handleSave = async () => {
    if (readonly) return
    setSaving(true)
    setError('')
    try {
      let weights: Record<string, number> = {}
      let trust_map: Record<string, number> = {}
      try { weights = JSON.parse(form.weights_json) } catch { setError('Invalid weights JSON'); setSaving(false); return }
      try { trust_map = JSON.parse(form.trust_map_json) } catch { setError('Invalid trust_map JSON'); setSaving(false); return }

      await updateAgent(org.id, agent.id, {
        display_name: form.display_name,
        display_name_ko: form.display_name_ko,
        role: form.role,
        tier: form.tier,
        domain: form.domain || null,
        team: form.team,
        silo_id: form.silo_id || null,
        chapter_id: form.chapter_id || null,
        is_clevel: form.is_clevel,
        weight_score: form.weight_score,
        enabled: form.enabled,
        behavioral_directives: form.behavioral_directives.split('\n').filter(Boolean),
        constraints: form.constraints.split('\n').filter(Boolean),
        decision_focus: form.decision_focus.split('\n').filter(Boolean),
        weights,
        trust_map,
        system_prompt_template: form.system_prompt_template || null,
      })
      await onSaved()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    }
    setSaving(false)
  }

  const set = (key: string, value: unknown) => setForm(prev => ({ ...prev, [key]: value }))

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid #e5e7eb', display: 'flex', alignItems: 'center', gap: 8 }}>
        <button onClick={onBack} style={backBtnStyle}>Back</button>
        <span style={{ fontWeight: 600, fontSize: 15 }}>{agent.agent_id}</span>
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
          <Field label="Display Name">
            <input value={form.display_name} onChange={e => set('display_name', e.target.value)} style={inputStyle} disabled={readonly} />
          </Field>
          <Field label="Display Name (KO)">
            <input value={form.display_name_ko} onChange={e => set('display_name_ko', e.target.value)} style={inputStyle} disabled={readonly} />
          </Field>
          <Field label="Role">
            <input value={form.role} onChange={e => set('role', e.target.value)} style={inputStyle} disabled={readonly} />
          </Field>
          <Field label="Tier (1-4)">
            <select value={form.tier} onChange={e => set('tier', Number(e.target.value))} style={inputStyle} disabled={readonly}>
              {[1, 2, 3, 4].map(t => <option key={t} value={t}>Tier {t}</option>)}
            </select>
          </Field>
          <Field label="Team">
            <input value={form.team} onChange={e => set('team', e.target.value)} style={inputStyle} disabled={readonly} />
          </Field>
          <Field label="Domain">
            <input value={form.domain} onChange={e => set('domain', e.target.value)} style={inputStyle} disabled={readonly} />
          </Field>
          <Field label="Silo">
            <select value={form.silo_id} onChange={e => set('silo_id', e.target.value)} style={inputStyle} disabled={readonly}>
              <option value="">-- None --</option>
              {(org.silos || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </Field>
          <Field label="Chapter">
            <select value={form.chapter_id} onChange={e => set('chapter_id', e.target.value)} style={inputStyle} disabled={readonly}>
              <option value="">-- None --</option>
              {(org.chapters || []).map(c => <option key={c.id} value={c.id}>{c.icon} {c.name}</option>)}
            </select>
          </Field>
          <Field label="C-Level">
            <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <input type="checkbox" checked={form.is_clevel} onChange={e => set('is_clevel', e.target.checked)} disabled={readonly} />
              {form.is_clevel ? 'Yes' : 'No'}
            </label>
          </Field>
          <Field label="Weight Score (0~10)">
            <input type="number" value={form.weight_score} onChange={e => set('weight_score', Number(e.target.value))} style={inputStyle} disabled={readonly} min={0} max={10} step={0.1} />
          </Field>
          <Field label="Enabled">
            <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <input type="checkbox" checked={form.enabled} onChange={e => set('enabled', e.target.checked)} disabled={readonly} />
              {form.enabled ? 'Yes' : 'No'}
            </label>
          </Field>
        </div>

        <Field label="Behavioral Directives (one per line)" full>
          <textarea value={form.behavioral_directives} onChange={e => set('behavioral_directives', e.target.value)} style={textareaStyle} rows={4} disabled={readonly} />
        </Field>

        {selectedChapter && selectedChapter.shared_directives.length > 0 && (
          <Field label="Chapter Directives (inherited)" full>
            <textarea value={selectedChapter.shared_directives.join('\n')} style={{ ...textareaStyle, backgroundColor: '#f9fafb', color: '#6b7280' }} rows={3} disabled />
          </Field>
        )}

        <Field label="Constraints (one per line)" full>
          <textarea value={form.constraints} onChange={e => set('constraints', e.target.value)} style={textareaStyle} rows={3} disabled={readonly} />
        </Field>

        {selectedChapter && selectedChapter.shared_constraints.length > 0 && (
          <Field label="Chapter Constraints (inherited)" full>
            <textarea value={selectedChapter.shared_constraints.join('\n')} style={{ ...textareaStyle, backgroundColor: '#f9fafb', color: '#6b7280' }} rows={3} disabled />
          </Field>
        )}

        <Field label="Decision Focus (one per line)" full>
          <textarea value={form.decision_focus} onChange={e => set('decision_focus', e.target.value)} style={textareaStyle} rows={3} disabled={readonly} />
        </Field>

        <Field label="Weights (JSON)" full>
          <textarea value={form.weights_json} onChange={e => set('weights_json', e.target.value)} style={{ ...textareaStyle, fontFamily: 'monospace' }} rows={5} disabled={readonly} />
        </Field>

        <Field label="Trust Map (JSON)" full>
          <textarea value={form.trust_map_json} onChange={e => set('trust_map_json', e.target.value)} style={{ ...textareaStyle, fontFamily: 'monospace' }} rows={5} disabled={readonly} />
        </Field>

        <Field label="System Prompt Template" full>
          <textarea value={form.system_prompt_template} onChange={e => set('system_prompt_template', e.target.value)} style={{ ...textareaStyle, fontFamily: 'monospace' }} rows={10} disabled={readonly} />
        </Field>
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
  gridTemplateColumns: '1fr 1fr',
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
