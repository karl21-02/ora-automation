import { useEffect, useState } from 'react'
import { Building2, FolderGit2, MessageSquarePlus, X } from 'lucide-react'
import type { Organization, ProjectInfo } from '../types'
import { listUnifiedProjects } from '../lib/api'

interface NewChatModalProps {
  open: boolean
  onClose: () => void
  onConfirm: (orgId: string | null, selectedProjects: string[]) => void
  orgs: Organization[]
  currentOrgId?: string | null
}

const sourceTypeConfig: Record<string, { icon: string; color: string; bg: string }> = {
  local: { icon: '📁', color: '#166534', bg: '#dcfce7' },
  github: { icon: '🐙', color: '#1e40af', bg: '#dbeafe' },
  github_only: { icon: '☁️', color: '#7c3aed', bg: '#ede9fe' },
}

export default function NewChatModal({
  open,
  onClose,
  onConfirm,
  orgs,
  currentOrgId,
}: NewChatModalProps) {
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(currentOrgId ?? null)
  const [projects, setProjects] = useState<ProjectInfo[]>([])
  const [selectedProjects, setSelectedProjects] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open) {
      setSelectedOrgId(currentOrgId ?? null)
      setSelectedProjects(new Set())
      loadProjects()
    }
  }, [open, currentOrgId])

  async function loadProjects() {
    setLoading(true)
    try {
      const result = await listUnifiedProjects({ enabled: true, limit: 50 })
      setProjects(result.items.map(p => ({
        id: p.id,
        name: p.name,
        path: p.local_path || '',
        has_makefile: false,
        has_dockerfile: false,
        description: p.description || '',
        source_type: p.source_type,
        language: p.language,
      })))
    } catch (err) {
      console.error('Failed to load projects:', err)
    } finally {
      setLoading(false)
    }
  }

  const toggleProject = (name: string) => {
    setSelectedProjects(prev => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const handleConfirm = () => {
    onConfirm(selectedOrgId, Array.from(selectedProjects))
    onClose()
  }

  if (!open) return null

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      backgroundColor: 'rgba(0,0,0,0.5)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
    }}>
      <div style={{
        width: '100%',
        maxWidth: 520,
        maxHeight: '80vh',
        backgroundColor: '#fff',
        borderRadius: 12,
        boxShadow: '0 20px 40px rgba(0,0,0,0.2)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 20px',
          borderBottom: '1px solid #e5e7eb',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <MessageSquarePlus size={20} color="#3b82f6" />
            <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: '#1f2937' }}>
              New Conversation
            </h2>
          </div>
          <button
            onClick={onClose}
            style={{
              padding: 4,
              border: 'none',
              backgroundColor: 'transparent',
              cursor: 'pointer',
              color: '#9ca3af',
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>
          {/* Organization Selection */}
          <div style={{ marginBottom: 20 }}>
            <label style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 13,
              fontWeight: 600,
              color: '#374151',
              marginBottom: 8,
            }}>
              <Building2 size={14} />
              Organization (Agent Configuration)
            </label>
            <select
              value={selectedOrgId || ''}
              onChange={(e) => setSelectedOrgId(e.target.value || null)}
              style={{
                width: '100%',
                padding: '10px 12px',
                fontSize: 14,
                border: '1px solid #d1d5db',
                borderRadius: 8,
                backgroundColor: '#fff',
                cursor: 'pointer',
              }}
            >
              <option value="">Default (No organization)</option>
              {orgs.map(org => (
                <option key={org.id} value={org.id}>
                  {org.name} ({org.agent_count} agents)
                </option>
              ))}
            </select>
          </div>

          {/* Project Selection */}
          <div>
            <label style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 13,
              fontWeight: 600,
              color: '#374151',
              marginBottom: 8,
            }}>
              <FolderGit2 size={14} />
              Target Projects (optional)
            </label>
            <p style={{
              fontSize: 12,
              color: '#6b7280',
              marginTop: 0,
              marginBottom: 10,
            }}>
              Pre-select projects to analyze. You can also select during conversation.
            </p>

            {loading ? (
              <div style={{
                padding: 20,
                textAlign: 'center',
                color: '#9ca3af',
                fontSize: 13,
              }}>
                Loading projects...
              </div>
            ) : projects.length === 0 ? (
              <div style={{
                padding: 20,
                textAlign: 'center',
                color: '#9ca3af',
                fontSize: 13,
                backgroundColor: '#f9fafb',
                borderRadius: 8,
                border: '1px dashed #e5e7eb',
              }}>
                No projects found. Scan local workspace in Settings.
              </div>
            ) : (
              <div style={{
                maxHeight: 240,
                overflowY: 'auto',
                border: '1px solid #e5e7eb',
                borderRadius: 8,
              }}>
                {projects.map((project) => {
                  const st = sourceTypeConfig[project.source_type || 'local'] || sourceTypeConfig.local
                  const isSelected = selectedProjects.has(project.name)
                  return (
                    <label
                      key={project.name}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 10,
                        padding: '10px 12px',
                        borderBottom: '1px solid #f3f4f6',
                        backgroundColor: isSelected ? '#eff6ff' : '#fff',
                        cursor: 'pointer',
                        transition: 'background-color 0.15s',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleProject(project.name)}
                        style={{ accentColor: '#2563eb' }}
                      />
                      <span style={{ fontSize: 14 }}>{st.icon}</span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6,
                          fontSize: 13,
                          fontWeight: 500,
                          color: '#1f2937',
                        }}>
                          {project.name}
                          {project.language && (
                            <span style={{
                              padding: '1px 5px',
                              borderRadius: 3,
                              fontSize: 10,
                              backgroundColor: '#f3f4f6',
                              color: '#6b7280',
                            }}>
                              {project.language}
                            </span>
                          )}
                        </div>
                      </div>
                      <span style={{
                        padding: '2px 6px',
                        borderRadius: 4,
                        fontSize: 10,
                        fontWeight: 500,
                        backgroundColor: st.bg,
                        color: st.color,
                      }}>
                        {project.source_type === 'github_only' ? 'Clone' : project.source_type}
                      </span>
                    </label>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div style={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: 10,
          padding: '16px 20px',
          borderTop: '1px solid #e5e7eb',
          backgroundColor: '#f9fafb',
        }}>
          <button
            onClick={onClose}
            style={{
              padding: '10px 20px',
              fontSize: 14,
              fontWeight: 500,
              border: '1px solid #d1d5db',
              borderRadius: 8,
              backgroundColor: '#fff',
              color: '#374151',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            style={{
              padding: '10px 24px',
              fontSize: 14,
              fontWeight: 600,
              border: 'none',
              borderRadius: 8,
              backgroundColor: '#2563eb',
              color: '#fff',
              cursor: 'pointer',
            }}
          >
            Start Chat
            {selectedProjects.size > 0 && ` (${selectedProjects.size} projects)`}
          </button>
        </div>
      </div>
    </div>
  )
}
