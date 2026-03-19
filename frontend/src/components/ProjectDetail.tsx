import { Clock, Code, FileCode, FileText, Key, Settings, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { getProjectConfig, getProjectEnv, getProjectHistory, getUnifiedProject } from '../lib/api'
import type { AnalysisHistoryItem, ConfigFile, ProjectConfigResponse, ProjectEnvResponse, UnifiedProject } from '../types'

type TabId = 'overview' | 'env' | 'config' | 'history'

interface Props {
  projectId: string
  onClose: () => void
  embedded?: boolean
}

export default function ProjectDetail({ projectId, onClose, embedded = false }: Props) {
  const [project, setProject] = useState<UnifiedProject | null>(null)
  const [activeTab, setActiveTab] = useState<TabId>('overview')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Tab-specific data
  const [envData, setEnvData] = useState<ProjectEnvResponse | null>(null)
  const [configData, setConfigData] = useState<ProjectConfigResponse | null>(null)
  const [historyData, setHistoryData] = useState<AnalysisHistoryItem[]>([])

  const loadProject = useCallback(async () => {
    try {
      const p = await getUnifiedProject(projectId)
      setProject(p)
    } catch (e) {
      setError('Failed to load project')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    loadProject()
  }, [loadProject])

  // Load tab data when switching
  useEffect(() => {
    if (!project?.local_path) return

    const loadTabData = async () => {
      try {
        if (activeTab === 'env' && !envData) {
          const data = await getProjectEnv(projectId)
          setEnvData(data)
        } else if (activeTab === 'config' && !configData) {
          const data = await getProjectConfig(projectId)
          setConfigData(data)
        } else if (activeTab === 'history' && historyData.length === 0) {
          const data = await getProjectHistory(projectId)
          setHistoryData(data.items)
        }
      } catch {
        // Tab data load failed - will show empty state
      }
    }

    loadTabData()
  }, [activeTab, projectId, project?.local_path, envData, configData, historyData.length])

  if (loading) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <span>Loading...</span>
          <button onClick={onClose} style={styles.closeBtn}><X size={18} /></button>
        </div>
      </div>
    )
  }

  if (error || !project) {
    return (
      <div style={styles.container}>
        <div style={styles.header}>
          <span style={{ color: '#ef4444' }}>{error || 'Project not found'}</span>
          <button onClick={onClose} style={styles.closeBtn}><X size={18} /></button>
        </div>
      </div>
    )
  }

  const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: 'overview', label: 'Overview', icon: <FileText size={14} /> },
    { id: 'env', label: 'Environment', icon: <Key size={14} /> },
    { id: 'config', label: 'Config', icon: <Settings size={14} /> },
    { id: 'history', label: 'History', icon: <Clock size={14} /> },
  ]

  const containerStyle = embedded
    ? { ...styles.container, position: 'relative' as const, width: '100%', boxShadow: 'none', borderLeft: 'none' }
    : styles.container

  return (
    <div style={containerStyle}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>{project.name}</h2>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 4 }}>
            {project.local_path || 'No local path'}
          </div>
        </div>
        {!embedded && <button onClick={onClose} style={styles.closeBtn}><X size={18} /></button>}
      </div>

      {/* Tabs */}
      <div style={styles.tabs}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              ...styles.tab,
              borderBottom: activeTab === tab.id ? '2px solid #3b82f6' : '2px solid transparent',
              color: activeTab === tab.id ? '#3b82f6' : '#6b7280',
            }}
          >
            {tab.icon}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div style={styles.content}>
        {activeTab === 'overview' && <OverviewTab project={project} />}
        {activeTab === 'env' && <EnvTab data={envData} hasLocalPath={!!project.local_path} />}
        {activeTab === 'config' && <ConfigTab data={configData} hasLocalPath={!!project.local_path} />}
        {activeTab === 'history' && <HistoryTab items={historyData} />}
      </div>
    </div>
  )
}

// ── Overview Tab ────────────────────────────────────────────────────

function OverviewTab({ project }: { project: UnifiedProject }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <InfoRow label="Source Type" value={project.source_type} />
      <InfoRow label="Language" value={project.language || 'Unknown'} />
      <InfoRow label="Default Branch" value={project.default_branch} />
      <InfoRow label="Analysis Count" value={String(project.analysis_count)} />
      <InfoRow
        label="Last Analyzed"
        value={project.last_analyzed_at ? new Date(project.last_analyzed_at).toLocaleString() : 'Never'}
      />
      {project.description && <InfoRow label="Description" value={project.description} />}
    </div>
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 14 }}>{value}</div>
    </div>
  )
}

// ── Env Tab ────────────────────────────────────────────────────

function EnvTab({ data, hasLocalPath }: { data: ProjectEnvResponse | null; hasLocalPath: boolean }) {
  if (!hasLocalPath) {
    return <EmptyState message="Project has no local path. Clone it first." />
  }

  if (!data) {
    return <div style={{ color: '#9ca3af' }}>Loading...</div>
  }

  if (!data.has_env && !data.has_env_example) {
    return <EmptyState message="No .env or .env.example file found" />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {data.has_env && (
        <div>
          <h4 style={{ margin: '0 0 8px', fontSize: 14, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Key size={14} />
            .env
            <span style={{ fontSize: 11, color: '#9ca3af', fontWeight: 400 }}>(sensitive values masked)</span>
          </h4>
          <EnvTable entries={Object.entries(data.env_content)} />
        </div>
      )}

      {data.has_env_example && data.env_example_content && (
        <div>
          <h4 style={{ margin: '0 0 8px', fontSize: 14, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 6 }}>
            <FileCode size={14} />
            .env.example
          </h4>
          <EnvTable entries={Object.entries(data.env_example_content)} />
        </div>
      )}
    </div>
  )
}

function EnvTable({ entries }: { entries: [string, string][] }) {
  if (entries.length === 0) {
    return <div style={{ color: '#9ca3af', fontSize: 13 }}>Empty file</div>
  }

  return (
    <div style={{
      border: '1px solid #e5e7eb',
      borderRadius: 6,
      overflow: 'hidden',
      fontSize: 13,
      fontFamily: 'monospace',
    }}>
      {entries.map(([key, value], i) => (
        <div
          key={key}
          style={{
            display: 'flex',
            borderBottom: i < entries.length - 1 ? '1px solid #e5e7eb' : 'none',
          }}
        >
          <div style={{
            padding: '6px 10px',
            background: '#f9fafb',
            fontWeight: 500,
            minWidth: 180,
            borderRight: '1px solid #e5e7eb',
          }}>
            {key}
          </div>
          <div style={{ padding: '6px 10px', flex: 1, color: '#6b7280' }}>
            {value || <span style={{ opacity: 0.5 }}>(empty)</span>}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Config Tab ────────────────────────────────────────────────────

function ConfigTab({ data, hasLocalPath }: { data: ProjectConfigResponse | null; hasLocalPath: boolean }) {
  const [expanded, setExpanded] = useState<string | null>(null)

  if (!hasLocalPath) {
    return <EmptyState message="Project has no local path. Clone it first." />
  }

  if (!data) {
    return <div style={{ color: '#9ca3af' }}>Loading...</div>
  }

  if (data.files.length === 0) {
    return <EmptyState message="No config files found" />
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {data.files.map((file) => (
        <div key={file.path} style={{ border: '1px solid #e5e7eb', borderRadius: 6, overflow: 'hidden' }}>
          <button
            onClick={() => setExpanded(expanded === file.name ? null : file.name)}
            style={{
              width: '100%',
              padding: '10px 12px',
              border: 'none',
              background: '#f9fafb',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: 500,
              textAlign: 'left',
            }}
          >
            <Code size={14} />
            {file.name}
            <span style={{ marginLeft: 'auto', fontSize: 11, color: '#9ca3af' }}>{file.type}</span>
          </button>
          {expanded === file.name && (
            <pre style={{
              margin: 0,
              padding: 12,
              background: '#1f2937',
              color: '#e5e7eb',
              fontSize: 12,
              overflow: 'auto',
              maxHeight: 300,
            }}>
              {typeof file.content === 'string'
                ? file.content
                : JSON.stringify(file.content, null, 2)}
            </pre>
          )}
        </div>
      ))}
    </div>
  )
}

// ── History Tab ────────────────────────────────────────────────────

function HistoryTab({ items }: { items: AnalysisHistoryItem[] }) {
  if (items.length === 0) {
    return <EmptyState message="No analysis history yet" />
  }

  const statusColors: Record<string, string> = {
    completed: '#22c55e',
    running: '#3b82f6',
    error: '#ef4444',
    queued: '#f59e0b',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {items.map((item) => (
        <div
          key={item.id}
          style={{
            padding: '10px 12px',
            border: '1px solid #e5e7eb',
            borderRadius: 6,
            fontSize: 13,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{
              padding: '2px 6px',
              borderRadius: 4,
              fontSize: 11,
              background: statusColors[item.status] || '#9ca3af',
              color: '#fff',
            }}>
              {item.status}
            </span>
            <span style={{ fontWeight: 500 }}>{item.run_type}</span>
            <span style={{ marginLeft: 'auto', fontSize: 11, color: '#9ca3af' }}>
              {item.started_at ? new Date(item.started_at).toLocaleString() : '—'}
            </span>
          </div>
          {item.user_prompt && (
            <div style={{ color: '#6b7280', fontSize: 12 }}>
              {item.user_prompt}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Empty State ────────────────────────────────────────────────────

function EmptyState({ message }: { message: string }) {
  return (
    <div style={{ textAlign: 'center', padding: 32, color: '#9ca3af' }}>
      {message}
    </div>
  )
}

// ── Styles ────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  container: {
    position: 'fixed',
    top: 0,
    right: 0,
    width: 480,
    height: '100vh',
    background: '#fff',
    borderLeft: '1px solid #e5e7eb',
    display: 'flex',
    flexDirection: 'column',
    zIndex: 100,
    boxShadow: '-4px 0 12px rgba(0,0,0,0.1)',
  },
  header: {
    display: 'flex',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    padding: '16px 20px',
    borderBottom: '1px solid #e5e7eb',
  },
  closeBtn: {
    padding: 4,
    border: 'none',
    background: 'transparent',
    cursor: 'pointer',
    borderRadius: 4,
  },
  tabs: {
    display: 'flex',
    borderBottom: '1px solid #e5e7eb',
    padding: '0 16px',
  },
  tab: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '10px 12px',
    border: 'none',
    background: 'transparent',
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 500,
  },
  content: {
    flex: 1,
    padding: 20,
    overflow: 'auto',
  },
}
