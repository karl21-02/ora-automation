import { useEffect, useState } from 'react'
import type { GithubInstallation } from '../types'
import {
  deleteGithubInstallation,
  getGithubInstallUrl,
  listGithubInstallations,
  syncGithubInstallation,
} from '../lib/api'

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
  installButton: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 6,
    padding: '6px 12px',
    fontSize: 13,
    fontWeight: 500,
    color: '#fff',
    backgroundColor: '#24292f',
    border: 'none',
    borderRadius: 6,
    cursor: 'pointer',
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
  list: {
    display: 'flex',
    flexDirection: 'column' as const,
    gap: 8,
  } as React.CSSProperties,
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: '12px 16px',
    backgroundColor: '#f9fafb',
    borderRadius: 8,
    border: '1px solid #e5e7eb',
  } as React.CSSProperties,
  avatar: {
    width: 32,
    height: 32,
    borderRadius: '50%',
    backgroundColor: '#e5e7eb',
  } as React.CSSProperties,
  info: {
    flex: 1,
    minWidth: 0,
  } as React.CSSProperties,
  name: {
    fontSize: 14,
    fontWeight: 500,
    color: '#1f2937',
    margin: 0,
  } as React.CSSProperties,
  meta: {
    fontSize: 12,
    color: '#6b7280',
    marginTop: 2,
  } as React.CSSProperties,
  actions: {
    display: 'flex',
    gap: 8,
  } as React.CSSProperties,
  actionButton: {
    padding: '4px 10px',
    fontSize: 12,
    fontWeight: 500,
    border: '1px solid #e5e7eb',
    borderRadius: 4,
    cursor: 'pointer',
    backgroundColor: '#fff',
    color: '#374151',
  } as React.CSSProperties,
  syncButton: {
    backgroundColor: '#3b82f6',
    borderColor: '#3b82f6',
    color: '#fff',
  } as React.CSSProperties,
  deleteButton: {
    backgroundColor: '#fff',
    borderColor: '#fca5a5',
    color: '#dc2626',
  } as React.CSSProperties,
  statusBadge: {
    display: 'inline-block',
    padding: '2px 6px',
    fontSize: 10,
    fontWeight: 500,
    borderRadius: 4,
    backgroundColor: '#dcfce7',
    color: '#166534',
    marginLeft: 8,
  } as React.CSSProperties,
}

export default function GitHubSettings() {
  const [installations, setInstallations] = useState<GithubInstallation[]>([])
  const [installUrl, setInstallUrl] = useState<string | null>(null)
  const [syncing, setSyncing] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    setLoading(true)
    try {
      const [installs, urlData] = await Promise.all([
        listGithubInstallations(),
        getGithubInstallUrl(),
      ])
      setInstallations(installs)
      setInstallUrl(urlData.url)
    } catch (err) {
      console.error('Failed to load GitHub data:', err)
    } finally {
      setLoading(false)
    }
  }

  async function handleSync(installationId: string) {
    setSyncing(installationId)
    try {
      await syncGithubInstallation(installationId)
      await loadData()
    } catch (err) {
      console.error('Failed to sync:', err)
    } finally {
      setSyncing(null)
    }
  }

  async function handleDelete(installationId: string) {
    if (!confirm('Are you sure you want to disconnect this installation?')) return
    try {
      await deleteGithubInstallation(installationId)
      setInstallations(prev => prev.filter(i => i.id !== installationId))
    } catch (err) {
      console.error('Failed to delete:', err)
    }
  }

  function handleInstall() {
    if (installUrl) {
      window.open(installUrl, '_blank')
    }
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h3 style={styles.title}>GitHub Integration</h3>
        <button
          style={styles.installButton}
          onClick={handleInstall}
          disabled={!installUrl}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path fillRule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"/>
          </svg>
          Install GitHub App
        </button>
      </div>

      {loading ? (
        <div style={styles.emptyState}>Loading...</div>
      ) : installations.length === 0 ? (
        <div style={styles.emptyState}>
          <p style={{ margin: 0, marginBottom: 8 }}>No GitHub organizations connected</p>
          <p style={{ margin: 0, fontSize: 12 }}>Click "Install GitHub App" to connect your repositories</p>
        </div>
      ) : (
        <div style={styles.list}>
          {installations.map(inst => (
            <div key={inst.id} style={styles.item}>
              {inst.avatar_url ? (
                <img src={inst.avatar_url} alt="" style={styles.avatar} />
              ) : (
                <div style={styles.avatar} />
              )}
              <div style={styles.info}>
                <p style={styles.name}>
                  {inst.account_login}
                  <span style={{
                    ...styles.statusBadge,
                    ...(inst.status !== 'active' && {
                      backgroundColor: '#fef3c7',
                      color: '#92400e',
                    }),
                  }}>
                    {inst.status}
                  </span>
                </p>
                <p style={styles.meta}>
                  {inst.account_type} &middot; {inst.repos_count ?? 0} repos
                  {inst.synced_at && (
                    <> &middot; Last synced {new Date(inst.synced_at).toLocaleDateString()}</>
                  )}
                </p>
              </div>
              <div style={styles.actions}>
                <button
                  style={{ ...styles.actionButton, ...styles.syncButton }}
                  onClick={() => handleSync(inst.id)}
                  disabled={syncing === inst.id}
                >
                  {syncing === inst.id ? 'Syncing...' : 'Sync'}
                </button>
                <button
                  style={{ ...styles.actionButton, ...styles.deleteButton }}
                  onClick={() => handleDelete(inst.id)}
                >
                  Disconnect
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
