import { useState } from 'react'
import type { ProjectInfo } from '../types'

interface Props {
  projects: ProjectInfo[]
  onConfirm: (selected: string[]) => void
  onDismiss: () => void
  disabled?: boolean
}

const sourceTypeConfig: Record<string, { icon: string; label: string; color: string; bg: string }> = {
  local: { icon: '📁', label: 'Local', color: '#166534', bg: '#dcfce7' },
  github: { icon: '🐙', label: 'GitHub', color: '#1e40af', bg: '#dbeafe' },
  github_only: { icon: '☁️', label: 'Clone', color: '#7c3aed', bg: '#ede9fe' },
}

export default function ProjectSelectCard({ projects, onConfirm, onDismiss, disabled = false }: Props) {
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(projects.map((p) => p.name))
  )
  const [submitted, setSubmitted] = useState(disabled)

  const toggle = (name: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const allSelected = selected.size === projects.length
  const toggleAll = () => {
    if (allSelected) {
      setSelected(new Set())
    } else {
      setSelected(new Set(projects.map((p) => p.name)))
    }
  }

  const handleConfirm = () => {
    setSubmitted(true)
    onConfirm(Array.from(selected))
  }

  const handleDismiss = () => {
    setSubmitted(true)
    onDismiss()
  }

  return (
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
        gap: 6,
        fontWeight: 700,
        fontSize: 13,
        color: '#374151',
        marginBottom: 10,
      }}>
        <span style={{
          display: 'inline-block',
          width: 8,
          height: 8,
          borderRadius: '50%',
          backgroundColor: '#3b82f6',
        }} />
        Select projects
      </div>

      {/* Project rows */}
      {projects.map((project) => {
        const sourceType = sourceTypeConfig[project.source_type || 'local'] || sourceTypeConfig.local
        return (
          <label
            key={project.name}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              padding: '8px 10px',
              borderRadius: 6,
              backgroundColor: selected.has(project.name) ? '#eff6ff' : '#f9fafb',
              border: `1px solid ${selected.has(project.name) ? '#93c5fd' : '#e5e7eb'}`,
              marginBottom: 4,
              cursor: submitted ? 'not-allowed' : 'pointer',
              transition: 'background-color 0.15s, border-color 0.15s',
            }}
          >
            <input
              type="checkbox"
              checked={selected.has(project.name)}
              onChange={() => toggle(project.name)}
              disabled={submitted}
              style={{ marginTop: 1, accentColor: '#2563eb' }}
            />

            {/* Source type icon */}
            <span style={{ fontSize: 14, flexShrink: 0 }}>{sourceType.icon}</span>

            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontWeight: 600,
                color: '#1f2937'
              }}>
                {project.name}
                {project.language && (
                  <span style={{
                    padding: '1px 5px',
                    borderRadius: 3,
                    fontSize: 10,
                    fontWeight: 500,
                    backgroundColor: '#f3f4f6',
                    color: '#6b7280',
                  }}>
                    {project.language}
                  </span>
                )}
              </div>
              {project.description && (
                <div style={{
                  fontSize: 11,
                  color: '#9ca3af',
                  marginTop: 2,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}>
                  {project.description}
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
              {/* Source type badge */}
              <span style={{
                padding: '1px 6px',
                borderRadius: 4,
                fontSize: 10,
                fontWeight: 500,
                backgroundColor: sourceType.bg,
                color: sourceType.color,
              }}>
                {sourceType.label}
              </span>
              {project.has_makefile && (
                <span style={{
                  padding: '1px 6px',
                  borderRadius: 4,
                  fontSize: 10,
                  fontWeight: 500,
                  backgroundColor: '#dbeafe',
                  color: '#1e40af',
                }}>
                  Make
                </span>
              )}
              {project.has_dockerfile && (
                <span style={{
                  padding: '1px 6px',
                  borderRadius: 4,
                  fontSize: 10,
                  fontWeight: 500,
                  backgroundColor: '#e0e7ff',
                  color: '#3730a3',
                }}>
                  Docker
                </span>
              )}
            </div>
          </label>
        )
      })}

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
        <button
          onClick={toggleAll}
          disabled={submitted}
          style={{
            padding: '8px 12px',
            borderRadius: 7,
            border: '1px solid #d1d5db',
            backgroundColor: '#fff',
            color: submitted ? '#9ca3af' : '#374151',
            fontWeight: 500,
            fontSize: 13,
            cursor: submitted ? 'not-allowed' : 'pointer',
          }}
        >
          {allSelected ? 'None' : 'Select All'}
        </button>
        <button
          onClick={handleConfirm}
          disabled={submitted || selected.size === 0}
          style={{
            flex: 1,
            padding: '8px 0',
            borderRadius: 7,
            border: 'none',
            backgroundColor: (submitted || selected.size === 0) ? '#9ca3af' : '#2563eb',
            color: '#fff',
            fontWeight: 600,
            fontSize: 13,
            cursor: (submitted || selected.size === 0) ? 'not-allowed' : 'pointer',
          }}
        >
          {submitted ? `Confirmed (${selected.size})` : `Confirm (${selected.size})`}
        </button>
        <button
          onClick={handleDismiss}
          disabled={submitted}
          style={{
            padding: '8px 16px',
            borderRadius: 7,
            border: '1px solid #d1d5db',
            backgroundColor: '#fff',
            color: submitted ? '#9ca3af' : '#6b7280',
            fontWeight: 500,
            fontSize: 13,
            cursor: submitted ? 'not-allowed' : 'pointer',
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
