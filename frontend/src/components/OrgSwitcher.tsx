import { useEffect, useRef, useState } from 'react'
import type { Organization } from '../types'
import { Building2, Check, ChevronDown, Plus } from 'lucide-react'

interface OrgSwitcherProps {
  currentOrgId: string | null
  orgs: Organization[]
  onSelect: (orgId: string | null) => void
  onCreateNew?: () => void
}

export default function OrgSwitcher({ currentOrgId, orgs, onSelect, onCreateNew }: OrgSwitcherProps) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const current = orgs.find(o => o.id === currentOrgId)

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClickOutside)
      return () => document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [open])

  // Close on Escape
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    if (open) {
      document.addEventListener('keydown', handleEscape)
      return () => document.removeEventListener('keydown', handleEscape)
    }
  }, [open])

  return (
    <div ref={ref} style={switcherStyle}>
      <button onClick={() => setOpen(!open)} style={triggerStyle}>
        <Building2 size={16} color="#6b7280" />
        <span style={{ flex: 1, textAlign: 'left', color: current ? '#374151' : '#9ca3af' }}>
          {current?.name || '조직 미선택'}
        </span>
        {current?.is_preset && <span style={presetBadge}>Preset</span>}
        <ChevronDown
          size={14}
          color="#9ca3af"
          style={{
            transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.2s ease',
          }}
        />
      </button>

      {open && (
        <div style={dropdownStyle}>
          {/* Unclassified option */}
          <button
            onClick={() => { onSelect(null); setOpen(false) }}
            style={{
              ...itemStyle,
              backgroundColor: currentOrgId === null ? '#f3f4f6' : 'transparent',
            }}
          >
            <span style={{ width: 16, display: 'flex', justifyContent: 'center' }}>
              {currentOrgId === null && <Check size={14} color="#2563eb" />}
            </span>
            <span style={{ color: '#6b7280' }}>📎 미분류 (기본 프리셋)</span>
          </button>

          {orgs.length > 0 && <div style={dividerStyle} />}

          {/* Org list */}
          {orgs.map(org => (
            <button
              key={org.id}
              onClick={() => { onSelect(org.id); setOpen(false) }}
              style={{
                ...itemStyle,
                backgroundColor: currentOrgId === org.id ? '#f3f4f6' : 'transparent',
              }}
            >
              <span style={{ width: 16, display: 'flex', justifyContent: 'center' }}>
                {currentOrgId === org.id && <Check size={14} color="#2563eb" />}
              </span>
              <span style={{ flex: 1 }}>{org.name}</span>
              {org.is_preset && <span style={presetBadgeSmall}>Preset</span>}
            </button>
          ))}

          {/* Create new option */}
          {onCreateNew && (
            <>
              <div style={dividerStyle} />
              <button
                onClick={() => { onCreateNew(); setOpen(false) }}
                style={{ ...itemStyle, color: '#2563eb' }}
              >
                <Plus size={14} />
                <span>새 조직 만들기</span>
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// Styles
const switcherStyle: React.CSSProperties = {
  position: 'relative',
  flex: 1,
  maxWidth: 280,
}

const triggerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  width: '100%',
  padding: '8px 12px',
  borderRadius: 8,
  border: '1px solid #e5e7eb',
  backgroundColor: '#fff',
  cursor: 'pointer',
  fontSize: 14,
  fontWeight: 500,
  transition: 'all 0.15s ease',
}

const dropdownStyle: React.CSSProperties = {
  position: 'absolute',
  top: 'calc(100% + 4px)',
  left: 0,
  right: 0,
  backgroundColor: '#fff',
  borderRadius: 8,
  border: '1px solid #e5e7eb',
  boxShadow: '0 4px 12px rgba(0, 0, 0, 0.1)',
  zIndex: 100,
  maxHeight: 320,
  overflow: 'auto',
  padding: 4,
}

const itemStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 8,
  width: '100%',
  padding: '8px 12px',
  borderRadius: 6,
  border: 'none',
  backgroundColor: 'transparent',
  cursor: 'pointer',
  fontSize: 13,
  color: '#374151',
  textAlign: 'left',
  transition: 'background-color 0.1s ease',
}

const dividerStyle: React.CSSProperties = {
  height: 1,
  backgroundColor: '#e5e7eb',
  margin: '4px 8px',
}

const presetBadge: React.CSSProperties = {
  fontSize: 10,
  padding: '1px 6px',
  borderRadius: 4,
  backgroundColor: '#dbeafe',
  color: '#2563eb',
  fontWeight: 500,
}

const presetBadgeSmall: React.CSSProperties = {
  fontSize: 9,
  padding: '1px 5px',
  borderRadius: 3,
  backgroundColor: '#dbeafe',
  color: '#2563eb',
  fontWeight: 500,
}
