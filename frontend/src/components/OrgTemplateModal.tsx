import { useState } from 'react'
import { ORG_TEMPLATES, type OrgTemplate } from '../lib/orgTemplates'

interface OrgTemplateModalProps {
  onClose: () => void
  onCreate: (name: string, templateId: string) => void
  creating?: boolean
}

export default function OrgTemplateModal({ onClose, onCreate, creating }: OrgTemplateModalProps) {
  const [selectedTemplate, setSelectedTemplate] = useState<string>('toss')
  const [orgName, setOrgName] = useState('')

  const handleCreate = () => {
    if (!orgName.trim()) return
    onCreate(orgName.trim(), selectedTemplate)
  }

  const selectedInfo = ORG_TEMPLATES.find(t => t.id === selectedTemplate)

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={modalStyle} onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div style={headerStyle}>
          <span style={{ fontSize: 16, fontWeight: 600 }}>Create New Organization</span>
          <button onClick={onClose} style={closeBtnStyle}>&times;</button>
        </div>

        {/* Template Selection */}
        <div style={contentStyle}>
          <div style={{ marginBottom: 16 }}>
            <label style={labelStyle}>Select Template</label>
            <div style={templateGridStyle}>
              {ORG_TEMPLATES.map(template => (
                <TemplateCard
                  key={template.id}
                  template={template}
                  selected={selectedTemplate === template.id}
                  onSelect={() => setSelectedTemplate(template.id)}
                />
              ))}
            </div>
          </div>

          {/* Template Preview */}
          {selectedInfo && selectedInfo.id !== 'empty' && (
            <div style={previewStyle}>
              <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 8 }}>
                {selectedInfo.icon} {selectedInfo.name} Preview
              </div>
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                <PreviewSection
                  title="Silos"
                  items={selectedInfo.silos.map(s => ({ name: s.name, color: s.color }))}
                />
                <PreviewSection
                  title="Chapters"
                  items={selectedInfo.chapters.map(c => ({ name: `${c.icon} ${c.name}`, color: c.color }))}
                />
              </div>
              <div style={{ marginTop: 12, fontSize: 12, color: '#6b7280' }}>
                {selectedInfo.agents.filter(a => a.is_clevel).length} C-Level + {' '}
                {selectedInfo.agents.filter(a => !a.is_clevel).length} Agents
              </div>
            </div>
          )}

          {/* Organization Name Input */}
          <div style={{ marginTop: 16 }}>
            <label style={labelStyle}>Organization Name</label>
            <input
              type="text"
              placeholder="My Company"
              value={orgName}
              onChange={e => setOrgName(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && !creating) handleCreate() }}
              style={inputStyle}
              autoFocus
            />
          </div>
        </div>

        {/* Footer */}
        <div style={footerStyle}>
          <button onClick={onClose} style={cancelBtnStyle} disabled={creating}>
            Cancel
          </button>
          <button
            onClick={handleCreate}
            style={{
              ...createBtnStyle,
              opacity: !orgName.trim() || creating ? 0.5 : 1,
              cursor: !orgName.trim() || creating ? 'not-allowed' : 'pointer',
            }}
            disabled={!orgName.trim() || creating}
          >
            {creating ? 'Creating...' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  )
}

// Template Card Component
function TemplateCard({
  template,
  selected,
  onSelect,
}: {
  template: OrgTemplate
  selected: boolean
  onSelect: () => void
}) {
  return (
    <div
      onClick={onSelect}
      style={{
        ...templateCardStyle,
        borderColor: selected ? '#2563eb' : '#e5e7eb',
        backgroundColor: selected ? '#eff6ff' : '#fff',
      }}
    >
      <div style={{ fontSize: 24, marginBottom: 8 }}>{template.icon}</div>
      <div style={{ fontWeight: 500, fontSize: 14, marginBottom: 4 }}>{template.name}</div>
      <div style={{ fontSize: 11, color: '#6b7280', lineHeight: 1.3 }}>
        {template.id === 'empty' ? (
          'Build from scratch'
        ) : (
          <>
            {template.agents.length} agents<br />
            {template.silos.length} silos, {template.chapters.length} chapters
          </>
        )}
      </div>
      {selected && (
        <div style={selectedBadgeStyle}>✓</div>
      )}
    </div>
  )
}

// Preview Section Component
function PreviewSection({
  title,
  items,
}: {
  title: string
  items: { name: string; color: string }[]
}) {
  if (items.length === 0) return null

  return (
    <div style={{ minWidth: 120 }}>
      <div style={{ fontSize: 11, color: '#9ca3af', marginBottom: 6 }}>{title}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {items.slice(0, 6).map((item, i) => (
          <span
            key={i}
            style={{
              fontSize: 11,
              padding: '2px 8px',
              borderRadius: 4,
              backgroundColor: `${item.color}20`,
              color: item.color,
              fontWeight: 500,
            }}
          >
            {item.name}
          </span>
        ))}
        {items.length > 6 && (
          <span style={{ fontSize: 11, color: '#9ca3af' }}>+{items.length - 6}</span>
        )}
      </div>
    </div>
  )
}

// Styles
const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  backgroundColor: 'rgba(0, 0, 0, 0.5)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
}

const modalStyle: React.CSSProperties = {
  backgroundColor: '#fff',
  borderRadius: 12,
  width: '90%',
  maxWidth: 560,
  maxHeight: '90vh',
  display: 'flex',
  flexDirection: 'column',
  boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
}

const headerStyle: React.CSSProperties = {
  padding: '16px 20px',
  borderBottom: '1px solid #e5e7eb',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
}

const closeBtnStyle: React.CSSProperties = {
  width: 28,
  height: 28,
  borderRadius: 6,
  border: 'none',
  backgroundColor: 'transparent',
  fontSize: 20,
  color: '#9ca3af',
  cursor: 'pointer',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
}

const contentStyle: React.CSSProperties = {
  padding: 20,
  flex: 1,
  overflow: 'auto',
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 13,
  fontWeight: 500,
  color: '#374151',
  marginBottom: 8,
}

const templateGridStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(2, 1fr)',
  gap: 12,
}

const templateCardStyle: React.CSSProperties = {
  position: 'relative',
  padding: 16,
  borderRadius: 8,
  border: '2px solid #e5e7eb',
  cursor: 'pointer',
  transition: 'all 0.15s ease',
  textAlign: 'center',
}

const selectedBadgeStyle: React.CSSProperties = {
  position: 'absolute',
  top: 8,
  right: 8,
  width: 20,
  height: 20,
  borderRadius: '50%',
  backgroundColor: '#2563eb',
  color: '#fff',
  fontSize: 12,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
}

const previewStyle: React.CSSProperties = {
  padding: 12,
  backgroundColor: '#f9fafb',
  borderRadius: 8,
  border: '1px solid #e5e7eb',
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 12px',
  borderRadius: 6,
  border: '1px solid #d1d5db',
  fontSize: 14,
  outline: 'none',
  boxSizing: 'border-box',
}

const footerStyle: React.CSSProperties = {
  padding: '16px 20px',
  borderTop: '1px solid #e5e7eb',
  display: 'flex',
  justifyContent: 'flex-end',
  gap: 8,
}

const cancelBtnStyle: React.CSSProperties = {
  padding: '8px 16px',
  borderRadius: 6,
  border: '1px solid #d1d5db',
  backgroundColor: '#fff',
  color: '#374151',
  fontSize: 13,
  fontWeight: 500,
  cursor: 'pointer',
}

const createBtnStyle: React.CSSProperties = {
  padding: '8px 20px',
  borderRadius: 6,
  border: 'none',
  backgroundColor: '#2563eb',
  color: '#fff',
  fontSize: 13,
  fontWeight: 500,
  cursor: 'pointer',
}
