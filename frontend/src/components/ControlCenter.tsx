import { FolderSync, Search } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import {
  executeScanAll,
  listGithubInstallations,
  listScanPaths,
  listUnifiedProjects,
} from '../lib/api'
import type { GithubInstallation, ScanPath, UnifiedProject } from '../types'
import ProjectDetail from './ProjectDetail'

type SourceFilter = 'all' | 'local' | 'github' | 'github_only'

export default function ControlCenter() {
  const [scanPaths, setScanPaths] = useState<ScanPath[]>([])
  const [githubInstalls, setGithubInstalls] = useState<GithubInstallation[]>([])
  const [projects, setProjects] = useState<UnifiedProject[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [filter, setFilter] = useState<SourceFilter>('all')
  const [search, setSearch] = useState('')

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [pathsRes, projectsRes, installsRes] = await Promise.all([
        listScanPaths(),
        listUnifiedProjects({
          source_type: filter === 'all' ? undefined : filter,
          search: search || undefined,
          limit: 200,
        }),
        listGithubInstallations().catch(() => [] as GithubInstallation[]),
      ])
      setScanPaths(pathsRes.items)
      setProjects(projectsRes.items)
      setGithubInstalls(installsRes)
    } catch {
      // Failed to load
    } finally {
      setLoading(false)
    }
  }, [filter, search])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleScanAll = async () => {
    setScanning(true)
    try {
      await executeScanAll()
      await loadData()
    } catch {
      // Failed to scan
    } finally {
      setScanning(false)
    }
  }

  const sourceTypeLabels: Record<string, { icon: string; color: string; bg: string }> = {
    local: { icon: '📁', color: '#166534', bg: '#dcfce7' },
    github: { icon: '🐙', color: '#1e40af', bg: '#dbeafe' },
    github_only: { icon: '☁️', color: '#7c3aed', bg: '#ede9fe' },
  }

  return (
    <div style={styles.container}>
      {/* Sub Panel (left) */}
      <div style={styles.subPanel}>
        {/* Sources Section */}
        <div style={styles.section}>
          <div style={styles.sectionHeader}>
            <span style={styles.sectionTitle}>SOURCES</span>
            <button
              onClick={handleScanAll}
              disabled={scanning}
              style={styles.scanAllBtn}
              title="Scan all paths"
            >
              <FolderSync size={14} />
            </button>
          </div>

          {/* Scan Paths */}
          <div style={styles.sourceGroup}>
            <div style={styles.sourceGroupTitle}>📁 Local Paths ({scanPaths.length})</div>
            {scanPaths.map((sp) => (
              <div key={sp.id} style={styles.sourceItem}>
                <span style={{ opacity: sp.enabled ? 1 : 0.5 }}>
                  {sp.name || sp.path.split('/').pop()}
                </span>
                <span style={styles.sourceCount}>{sp.project_count}</span>
              </div>
            ))}
            {scanPaths.length === 0 && (
              <div style={styles.emptyHint}>No paths configured</div>
            )}
          </div>

          {/* GitHub Installs */}
          <div style={styles.sourceGroup}>
            <div style={styles.sourceGroupTitle}>🐙 GitHub ({githubInstalls.length})</div>
            {githubInstalls.map((gi) => (
              <div key={gi.id} style={styles.sourceItem}>
                <span>{gi.account_login}</span>
              </div>
            ))}
            {githubInstalls.length === 0 && (
              <div style={styles.emptyHint}>Not connected</div>
            )}
          </div>
        </div>

        <div style={styles.divider} />

        {/* Projects Section */}
        <div style={{ ...styles.section, flex: 1, minHeight: 0 }}>
          <div style={styles.sectionHeader}>
            <span style={styles.sectionTitle}>PROJECTS ({projects.length})</span>
          </div>

          {/* Search */}
          <div style={styles.searchWrapper}>
            <Search size={14} style={{ color: '#9ca3af' }} />
            <input
              type="text"
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={styles.searchInput}
            />
          </div>

          {/* Filters */}
          <div style={styles.filters}>
            {(['all', 'local', 'github', 'github_only'] as SourceFilter[]).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                style={{
                  ...styles.filterBtn,
                  ...(filter === f ? styles.filterBtnActive : {}),
                }}
              >
                {f === 'all' ? 'All' : f === 'github_only' ? 'Cloud' : f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>

          {/* Project List */}
          <div style={styles.projectList}>
            {loading ? (
              <div style={styles.emptyHint}>Loading...</div>
            ) : projects.length === 0 ? (
              <div style={styles.emptyHint}>No projects found</div>
            ) : (
              projects.map((p) => {
                const sourceType = sourceTypeLabels[p.source_type] || sourceTypeLabels.local
                return (
                  <div
                    key={p.id}
                    onClick={() => setSelectedProjectId(p.id)}
                    style={{
                      ...styles.projectItem,
                      borderLeft: selectedProjectId === p.id ? '3px solid #3b82f6' : '3px solid transparent',
                      backgroundColor: selectedProjectId === p.id ? '#eff6ff' : 'transparent',
                    }}
                  >
                    <span style={styles.projectIcon}>{sourceType.icon}</span>
                    <div style={styles.projectInfo}>
                      <div style={styles.projectName}>{p.name}</div>
                      <div style={styles.projectMeta}>
                        {p.language && <span>{p.language}</span>}
                      </div>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </div>
      </div>

      {/* Main Content (right) */}
      <div style={styles.mainContent}>
        {selectedProjectId ? (
          <ProjectDetail
            projectId={selectedProjectId}
            onClose={() => setSelectedProjectId(null)}
            embedded
          />
        ) : (
          <div style={styles.emptyState}>
            <FolderSync size={48} style={{ opacity: 0.3, marginBottom: 16 }} />
            <p style={{ margin: 0, fontSize: 15, fontWeight: 500 }}>Select a project</p>
            <p style={{ margin: '8px 0 0', fontSize: 13, color: '#9ca3af' }}>
              Click a project from the list to view details
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flex: 1,
    height: '100%',
    overflow: 'hidden',
  },
  subPanel: {
    width: 260,
    borderRight: '1px solid #e5e7eb',
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: '#fafafa',
    overflow: 'hidden',
  },
  section: {
    padding: '12px 16px',
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: 600,
    color: '#6b7280',
    letterSpacing: '0.05em',
  },
  scanAllBtn: {
    padding: 4,
    border: 'none',
    background: 'transparent',
    cursor: 'pointer',
    borderRadius: 4,
    color: '#6b7280',
  },
  sourceGroup: {
    marginBottom: 12,
  },
  sourceGroupTitle: {
    fontSize: 12,
    fontWeight: 500,
    color: '#374151',
    marginBottom: 6,
  },
  sourceItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '4px 8px',
    fontSize: 12,
    color: '#4b5563',
    borderRadius: 4,
  },
  sourceCount: {
    fontSize: 11,
    color: '#9ca3af',
  },
  emptyHint: {
    fontSize: 12,
    color: '#9ca3af',
    padding: '4px 8px',
    fontStyle: 'italic',
  },
  divider: {
    height: 1,
    backgroundColor: '#e5e7eb',
    margin: '0 16px',
  },
  searchWrapper: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 10px',
    backgroundColor: '#fff',
    border: '1px solid #e5e7eb',
    borderRadius: 6,
    marginBottom: 8,
  },
  searchInput: {
    flex: 1,
    border: 'none',
    outline: 'none',
    fontSize: 13,
    backgroundColor: 'transparent',
  },
  filters: {
    display: 'flex',
    gap: 4,
    marginBottom: 8,
    flexWrap: 'wrap',
  },
  filterBtn: {
    padding: '3px 8px',
    fontSize: 11,
    fontWeight: 500,
    border: '1px solid #e5e7eb',
    borderRadius: 4,
    cursor: 'pointer',
    backgroundColor: '#fff',
    color: '#6b7280',
  },
  filterBtnActive: {
    backgroundColor: '#3b82f6',
    borderColor: '#3b82f6',
    color: '#fff',
  },
  projectList: {
    flex: 1,
    overflowY: 'auto',
    marginTop: 4,
  },
  projectItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    padding: '8px 10px',
    cursor: 'pointer',
    borderRadius: 4,
    transition: 'background-color 0.1s',
  },
  projectIcon: {
    fontSize: 14,
    flexShrink: 0,
  },
  projectInfo: {
    flex: 1,
    minWidth: 0,
  },
  projectName: {
    fontSize: 13,
    fontWeight: 500,
    color: '#1f2937',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  projectMeta: {
    fontSize: 11,
    color: '#9ca3af',
  },
  mainContent: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  emptyState: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#6b7280',
  },
}
