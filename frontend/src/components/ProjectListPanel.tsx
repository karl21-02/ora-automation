import { useEffect, useState } from 'react'
import type { LocalScanResult, UnifiedProject } from '../types'
import {
  listUnifiedProjects,
  scanLocalProjects,
  updateUnifiedProject,
} from '../lib/api'
import ProjectDetail from './ProjectDetail'

const styles = {
  container: {
    marginBottom: 24,
  } as React.CSSProperties,
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 16,
  } as React.CSSProperties,
  title: {
    fontSize: 14,
    fontWeight: 600,
    color: '#374151',
    margin: 0,
  } as React.CSSProperties,
  scanButton: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 12px',
    fontSize: 13,
    fontWeight: 500,
    color: '#374151',
    backgroundColor: '#fff',
    border: '1px solid #e5e7eb',
    borderRadius: 6,
    cursor: 'pointer',
  } as React.CSSProperties,
  filters: {
    display: 'flex',
    gap: 8,
    marginBottom: 12,
  } as React.CSSProperties,
  filterButton: {
    padding: '4px 10px',
    fontSize: 12,
    fontWeight: 500,
    border: '1px solid #e5e7eb',
    borderRadius: 4,
    cursor: 'pointer',
    backgroundColor: '#fff',
    color: '#6b7280',
  } as React.CSSProperties,
  filterButtonActive: {
    backgroundColor: '#3b82f6',
    borderColor: '#3b82f6',
    color: '#fff',
  } as React.CSSProperties,
  searchInput: {
    flex: 1,
    padding: '6px 10px',
    fontSize: 13,
    border: '1px solid #e5e7eb',
    borderRadius: 6,
    outline: 'none',
  } as React.CSSProperties,
  list: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 6,
    maxHeight: 400,
    overflowY: 'auto' as const,
  } as React.CSSProperties,
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '10px 12px',
    backgroundColor: '#f9fafb',
    borderRadius: 6,
    border: '1px solid #e5e7eb',
  } as React.CSSProperties,
  sourceIcon: {
    width: 20,
    height: 20,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: 12,
    flexShrink: 0,
  } as React.CSSProperties,
  info: {
    flex: 1,
    minWidth: 0,
  } as React.CSSProperties,
  name: {
    fontSize: 13,
    fontWeight: 500,
    color: '#1f2937',
    margin: 0,
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  } as React.CSSProperties,
  meta: {
    fontSize: 11,
    color: '#9ca3af',
    marginTop: 2,
    whiteSpace: 'nowrap' as const,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  } as React.CSSProperties,
  badge: {
    padding: '2px 6px',
    fontSize: 10,
    fontWeight: 500,
    borderRadius: 4,
    flexShrink: 0,
  } as React.CSSProperties,
  toggle: {
    position: 'relative' as const,
    width: 36,
    height: 20,
    backgroundColor: '#e5e7eb',
    borderRadius: 10,
    cursor: 'pointer',
    transition: 'background-color 0.2s',
    flexShrink: 0,
  } as React.CSSProperties,
  toggleOn: {
    backgroundColor: '#3b82f6',
  } as React.CSSProperties,
  toggleKnob: {
    position: 'absolute' as const,
    top: 2,
    left: 2,
    width: 16,
    height: 16,
    backgroundColor: '#fff',
    borderRadius: '50%',
    transition: 'left 0.2s',
    boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
  } as React.CSSProperties,
  toggleKnobOn: {
    left: 18,
  } as React.CSSProperties,
  emptyState: {
    padding: '24px 16px',
    textAlign: 'center' as const,
    color: '#6b7280',
    fontSize: 13,
    backgroundColor: '#f9fafb',
    borderRadius: 8,
    border: '1px dashed #e5e7eb',
  } as React.CSSProperties,
  scanResult: {
    padding: '8px 12px',
    marginBottom: 12,
    backgroundColor: '#dcfce7',
    borderRadius: 6,
    fontSize: 12,
    color: '#166534',
  } as React.CSSProperties,
  summary: {
    fontSize: 12,
    color: '#6b7280',
    marginBottom: 8,
  } as React.CSSProperties,
}

const sourceTypeLabels: Record<string, { icon: string; label: string; color: string; bg: string }> = {
  local: { icon: '\ud83d\udcc1', label: 'Local', color: '#166534', bg: '#dcfce7' },
  github: { icon: '\ud83d\udc19', label: 'GitHub', color: '#1e40af', bg: '#dbeafe' },
  github_only: { icon: '\u2601\ufe0f', label: 'Cloud', color: '#7c3aed', bg: '#ede9fe' },
}

type SourceFilter = 'all' | 'local' | 'github' | 'github_only'

export default function ProjectListPanel() {
  const [projects, setProjects] = useState<UnifiedProject[]>([])
  const [total, setTotal] = useState(0)
  const [filter, setFilter] = useState<SourceFilter>('all')
  const [search, setSearch] = useState('')
  const [scanning, setScanning] = useState(false)
  const [scanResult, setScanResult] = useState<LocalScanResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)

  useEffect(() => {
    loadProjects()
  }, [filter, search])

  async function loadProjects() {
    setLoading(true)
    try {
      const result = await listUnifiedProjects({
        source_type: filter === 'all' ? undefined : filter,
        search: search || undefined,
        limit: 100,
      })
      setProjects(result.items)
      setTotal(result.total)
    } catch (err) {
      console.error('Failed to load projects:', err)
    } finally {
      setLoading(false)
    }
  }

  async function handleScan() {
    setScanning(true)
    setScanResult(null)
    try {
      const result = await scanLocalProjects()
      setScanResult(result)
      await loadProjects()
    } catch (err) {
      console.error('Failed to scan:', err)
    } finally {
      setScanning(false)
    }
  }

  async function handleToggleEnabled(project: UnifiedProject) {
    try {
      await updateUnifiedProject(project.id, { enabled: !project.enabled })
      setProjects(prev =>
        prev.map(p => (p.id === project.id ? { ...p, enabled: !p.enabled } : p))
      )
    } catch (err) {
      console.error('Failed to update project:', err)
    }
  }

  const filterButtons: { key: SourceFilter; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'local', label: 'Local' },
    { key: 'github', label: 'GitHub' },
    { key: 'github_only', label: 'Cloud' },
  ]

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h3 style={styles.title}>Projects</h3>
        <button
          style={styles.scanButton}
          onClick={handleScan}
          disabled={scanning}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
            <path d="M9 12l2 2 4-4"/>
          </svg>
          {scanning ? 'Scanning...' : 'Scan Local'}
        </button>
      </div>

      {scanResult && (
        <div style={styles.scanResult}>
          Scan complete: {scanResult.created} created, {scanResult.updated} updated, {scanResult.unchanged} unchanged
        </div>
      )}

      <div style={styles.filters}>
        {filterButtons.map(btn => (
          <button
            key={btn.key}
            style={{
              ...styles.filterButton,
              ...(filter === btn.key ? styles.filterButtonActive : {}),
            }}
            onClick={() => setFilter(btn.key)}
          >
            {btn.label}
          </button>
        ))}
        <input
          type="text"
          placeholder="Search projects..."
          style={styles.searchInput}
          value={search}
          onChange={e => setSearch(e.target.value)}
        />
      </div>

      <p style={styles.summary}>{total} projects</p>

      {loading ? (
        <div style={styles.emptyState}>Loading...</div>
      ) : projects.length === 0 ? (
        <div style={styles.emptyState}>
          <p style={{ margin: 0, marginBottom: 8 }}>No projects found</p>
          <p style={{ margin: 0, fontSize: 12 }}>Click "Scan Local" to discover projects in your workspace</p>
        </div>
      ) : (
        <div style={styles.list}>
          {projects.map(project => {
            const sourceType = sourceTypeLabels[project.source_type] || sourceTypeLabels.local
            return (
              <div
                key={project.id}
                style={{
                  ...styles.item,
                  cursor: 'pointer',
                }}
                onClick={() => setSelectedProjectId(project.id)}
              >
                <span style={styles.sourceIcon}>{sourceType.icon}</span>
                <div style={styles.info}>
                  <p style={styles.name}>{project.name}</p>
                  <p style={styles.meta}>
                    {project.language && <>{project.language} &middot; </>}
                    {project.local_path || project.description || 'No path'}
                  </p>
                </div>
                <span style={{
                  ...styles.badge,
                  backgroundColor: sourceType.bg,
                  color: sourceType.color,
                }}>
                  {sourceType.label}
                </span>
                <div
                  style={{
                    ...styles.toggle,
                    ...(project.enabled ? styles.toggleOn : {}),
                  }}
                  onClick={(e) => {
                    e.stopPropagation()
                    handleToggleEnabled(project)
                  }}
                  title={project.enabled ? 'Enabled for analysis' : 'Disabled'}
                >
                  <div style={{
                    ...styles.toggleKnob,
                    ...(project.enabled ? styles.toggleKnobOn : {}),
                  }} />
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Project Detail Slide-in */}
      {selectedProjectId && (
        <ProjectDetail
          projectId={selectedProjectId}
          onClose={() => setSelectedProjectId(null)}
        />
      )}
    </div>
  )
}
