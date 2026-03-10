import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  const [focusedIndex, setFocusedIndex] = useState(-1)
  const [searchQuery, setSearchQuery] = useState('')
  const ref = useRef<HTMLDivElement>(null)
  const searchInputRef = useRef<HTMLInputElement>(null)

  const current = orgs.find(o => o.id === currentOrgId)

  // Filter orgs based on search query
  const filteredOrgs = useMemo(() => {
    if (!searchQuery.trim()) return orgs
    const q = searchQuery.toLowerCase()
    return orgs.filter(o => o.name.toLowerCase().includes(q))
  }, [orgs, searchQuery])

  // Build list of selectable options: [null (unclassified), ...filtered org ids, 'create' if onCreateNew]
  const options = useMemo(() => {
    const list: (string | null)[] = [null, ...filteredOrgs.map(o => o.id)]
    if (onCreateNew) list.push('__create__')
    return list
  }, [filteredOrgs, onCreateNew])

  // Reset focus and search when dropdown opens/closes
  useEffect(() => {
    if (open) {
      // Focus on current selection
      const idx = options.indexOf(currentOrgId)
      setFocusedIndex(idx >= 0 ? idx : 0)
      setSearchQuery('')
      // Focus search input when dropdown opens (if many orgs)
      if (orgs.length > 5) {
        setTimeout(() => searchInputRef.current?.focus(), 50)
      }
    } else {
      setFocusedIndex(-1)
      setSearchQuery('')
    }
  }, [open, currentOrgId, options, orgs.length])

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

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
        e.preventDefault()
        setOpen(true)
      }
      return
    }

    switch (e.key) {
      case 'Escape':
        e.preventDefault()
        setOpen(false)
        break
      case 'ArrowDown':
        e.preventDefault()
        setFocusedIndex(prev => Math.min(prev + 1, options.length - 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setFocusedIndex(prev => Math.max(prev - 1, 0))
        break
      case 'Enter':
        e.preventDefault()
        if (focusedIndex >= 0 && focusedIndex < options.length) {
          const option = options[focusedIndex]
          if (option === '__create__') {
            onCreateNew?.()
          } else {
            onSelect(option)
          }
          setOpen(false)
        }
        break
    }
  }, [open, focusedIndex, options, onSelect, onCreateNew])

  // Get index of an option in the options array
  const getOptionIndex = (id: string | null) => options.indexOf(id)
  const createIndex = options.indexOf('__create__')

  return (
    <div ref={ref} style={switcherStyle} onKeyDown={handleKeyDown}>
      <button
        onClick={() => setOpen(!open)}
        style={triggerStyle}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
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
        <div style={dropdownStyle} role="listbox">
          {/* Search input (only show if many orgs) */}
          {orgs.length > 5 && (
            <div style={searchContainerStyle}>
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="조직 검색..."
                style={searchInputStyle}
                onClick={(e) => e.stopPropagation()}
              />
            </div>
          )}

          {/* Unclassified option */}
          <button
            onClick={() => { onSelect(null); setOpen(false) }}
            style={{
              ...itemStyle,
              backgroundColor: focusedIndex === 0 ? '#dbeafe' : currentOrgId === null ? '#f3f4f6' : 'transparent',
              outline: focusedIndex === 0 ? '2px solid #2563eb' : 'none',
            }}
            role="option"
            aria-selected={currentOrgId === null}
          >
            <span style={{ width: 16, display: 'flex', justifyContent: 'center' }}>
              {currentOrgId === null && <Check size={14} color="#2563eb" />}
            </span>
            <span style={{ color: '#6b7280' }}>📎 미분류 (기본 프리셋)</span>
          </button>

          {filteredOrgs.length > 0 && <div style={dividerStyle} />}

          {/* Org list */}
          {filteredOrgs.map((org) => {
            const optionIdx = getOptionIndex(org.id)
            const isFocused = focusedIndex === optionIdx
            const isSelected = currentOrgId === org.id
            return (
              <button
                key={org.id}
                onClick={() => { onSelect(org.id); setOpen(false) }}
                style={{
                  ...itemStyle,
                  backgroundColor: isFocused ? '#dbeafe' : isSelected ? '#f3f4f6' : 'transparent',
                  outline: isFocused ? '2px solid #2563eb' : 'none',
                }}
                role="option"
                aria-selected={isSelected}
              >
                <span style={{ width: 16, display: 'flex', justifyContent: 'center' }}>
                  {isSelected && <Check size={14} color="#2563eb" />}
                </span>
                <span style={{ flex: 1 }}>{org.name}</span>
                <span style={agentCountBadge}>{org.agent_count}</span>
                {org.is_preset && <span style={presetBadgeSmall}>Preset</span>}
              </button>
            )
          })}

          {/* Empty state hint */}
          {orgs.length === 0 && onCreateNew && (
            <div style={emptyHintStyle}>
              아직 조직이 없습니다. 나만의 AI 조직을 만들어보세요!
            </div>
          )}

          {/* No search results */}
          {searchQuery && filteredOrgs.length === 0 && orgs.length > 0 && (
            <div style={emptyHintStyle}>
              "{searchQuery}"에 해당하는 조직이 없습니다
            </div>
          )}

          {/* Create new option */}
          {onCreateNew && (
            <>
              {filteredOrgs.length > 0 && <div style={dividerStyle} />}
              <button
                onClick={() => { onCreateNew(); setOpen(false) }}
                style={{
                  ...itemStyle,
                  color: '#2563eb',
                  backgroundColor: focusedIndex === createIndex ? '#dbeafe' : 'transparent',
                  outline: focusedIndex === createIndex ? '2px solid #2563eb' : 'none',
                }}
              >
                <Plus size={14} />
                <span>새 조직 만들기</span>
              </button>
            </>
          )}

          {/* Keyboard hint */}
          <div style={keyboardHintStyle}>
            ↑↓ 이동 · Enter 선택 · Esc 닫기
          </div>
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

const emptyHintStyle: React.CSSProperties = {
  padding: '12px 16px',
  fontSize: 12,
  color: '#6b7280',
  textAlign: 'center',
  backgroundColor: '#f9fafb',
  borderRadius: 6,
  margin: '4px 8px',
}

const keyboardHintStyle: React.CSSProperties = {
  padding: '6px 12px',
  fontSize: 10,
  color: '#9ca3af',
  textAlign: 'center',
  borderTop: '1px solid #f3f4f6',
  marginTop: 4,
}

const searchContainerStyle: React.CSSProperties = {
  padding: '8px 8px 4px',
  borderBottom: '1px solid #f3f4f6',
}

const searchInputStyle: React.CSSProperties = {
  width: '100%',
  padding: '6px 10px',
  borderRadius: 6,
  border: '1px solid #e5e7eb',
  fontSize: 13,
  outline: 'none',
  boxSizing: 'border-box',
}

const agentCountBadge: React.CSSProperties = {
  fontSize: 10,
  padding: '1px 6px',
  borderRadius: 10,
  backgroundColor: '#f3f4f6',
  color: '#6b7280',
  fontWeight: 500,
}
