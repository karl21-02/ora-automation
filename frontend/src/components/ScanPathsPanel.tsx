import { FolderPlus, FolderSync, Play, Plus, ToggleLeft, ToggleRight, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import {
  createScanPath,
  deleteScanPath,
  executeScanAll,
  executeScanPath,
  listScanPaths,
  updateScanPath,
} from '../lib/api'
import type { ScanPath, ScanResult } from '../types'

interface Props {
  onPathsChanged?: () => void
}

export default function ScanPathsPanel({ onPathsChanged }: Props) {
  const [scanPaths, setScanPaths] = useState<ScanPath[]>([])
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState<string | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [newPath, setNewPath] = useState('')
  const [newName, setNewName] = useState('')
  const [newRecursive, setNewRecursive] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastResult, setLastResult] = useState<ScanResult | null>(null)

  const loadPaths = useCallback(async () => {
    try {
      const { items } = await listScanPaths()
      setScanPaths(items)
    } catch (e) {
      setError('Failed to load scan paths')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadPaths()
  }, [loadPaths])

  const handleAdd = async () => {
    if (!newPath.trim()) return
    setError(null)
    try {
      const created = await createScanPath({
        path: newPath.trim(),
        name: newName.trim() || undefined,
        recursive: newRecursive,
      })
      setScanPaths((prev) => [created, ...prev])
      setNewPath('')
      setNewName('')
      setNewRecursive(false)
      setShowAddForm(false)
      onPathsChanged?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add path')
    }
  }

  const handleToggleEnabled = async (sp: ScanPath) => {
    try {
      const updated = await updateScanPath(sp.id, { enabled: !sp.enabled })
      setScanPaths((prev) => prev.map((p) => (p.id === sp.id ? updated : p)))
    } catch (e) {
      setError('Failed to update path')
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this scan path?')) return
    try {
      await deleteScanPath(id)
      setScanPaths((prev) => prev.filter((p) => p.id !== id))
      onPathsChanged?.()
    } catch (e) {
      setError('Failed to delete path')
    }
  }

  const handleScan = async (id: string) => {
    setScanning(id)
    setError(null)
    setLastResult(null)
    try {
      const result = await executeScanPath(id)
      setLastResult(result)
      await loadPaths()
      onPathsChanged?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Scan failed')
    } finally {
      setScanning(null)
    }
  }

  const handleScanAll = async () => {
    setScanning('all')
    setError(null)
    setLastResult(null)
    try {
      const results = await executeScanAll()
      const total = results.reduce(
        (acc, r) => ({
          projects_found: acc.projects_found + r.projects_found,
          projects_created: acc.projects_created + r.projects_created,
          projects_updated: acc.projects_updated + r.projects_updated,
        }),
        { projects_found: 0, projects_created: 0, projects_updated: 0 }
      )
      setLastResult({
        scan_path_id: 'all',
        duration_ms: results.reduce((acc, r) => acc + r.duration_ms, 0),
        ...total,
      })
      await loadPaths()
      onPathsChanged?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Scan all failed')
    } finally {
      setScanning(null)
    }
  }

  if (loading) {
    return (
      <div style={{ padding: 24, color: '#9ca3af' }}>
        Loading scan paths...
      </div>
    )
  }

  return (
    <div style={{ padding: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
          <FolderPlus size={20} />
          Scan Paths
        </h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={handleScanAll}
            disabled={scanning !== null || scanPaths.length === 0}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '6px 12px',
              border: 'none',
              borderRadius: 6,
              background: '#3b82f6',
              color: '#fff',
              fontSize: 13,
              cursor: scanning ? 'not-allowed' : 'pointer',
              opacity: scanning ? 0.6 : 1,
            }}
          >
            <FolderSync size={14} />
            {scanning === 'all' ? 'Scanning...' : 'Scan All'}
          </button>
          <button
            onClick={() => setShowAddForm(true)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '6px 12px',
              border: '1px solid #e5e7eb',
              borderRadius: 6,
              background: '#fff',
              fontSize: 13,
              cursor: 'pointer',
            }}
          >
            <Plus size={14} />
            Add Path
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div style={{
          padding: '8px 12px',
          marginBottom: 12,
          background: '#fef2f2',
          border: '1px solid #fecaca',
          borderRadius: 6,
          color: '#dc2626',
          fontSize: 13,
        }}>
          {error}
        </div>
      )}

      {/* Last Result */}
      {lastResult && (
        <div style={{
          padding: '8px 12px',
          marginBottom: 12,
          background: '#f0fdf4',
          border: '1px solid #bbf7d0',
          borderRadius: 6,
          color: '#16a34a',
          fontSize: 13,
        }}>
          Found {lastResult.projects_found} projects
          {lastResult.projects_created > 0 && `, ${lastResult.projects_created} new`}
          {lastResult.projects_updated > 0 && `, ${lastResult.projects_updated} updated`}
          {' '}({lastResult.duration_ms}ms)
        </div>
      )}

      {/* Add Form */}
      {showAddForm && (
        <div style={{
          padding: 16,
          marginBottom: 16,
          background: '#f9fafb',
          borderRadius: 8,
          border: '1px solid #e5e7eb',
        }}>
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>
              Path *
            </label>
            <input
              type="text"
              value={newPath}
              onChange={(e) => setNewPath(e.target.value)}
              placeholder="/workspace/projects"
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1px solid #d1d5db',
                borderRadius: 6,
                fontSize: 14,
              }}
            />
          </div>
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', marginBottom: 4, fontSize: 13, fontWeight: 500 }}>
              Name (optional)
            </label>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Company Projects"
              style={{
                width: '100%',
                padding: '8px 12px',
                border: '1px solid #d1d5db',
                borderRadius: 6,
                fontSize: 14,
              }}
            />
          </div>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={newRecursive}
                onChange={(e) => setNewRecursive(e.target.checked)}
              />
              Recursive scan
            </label>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={handleAdd}
              style={{
                padding: '6px 16px',
                border: 'none',
                borderRadius: 6,
                background: '#3b82f6',
                color: '#fff',
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              Add
            </button>
            <button
              onClick={() => {
                setShowAddForm(false)
                setNewPath('')
                setNewName('')
                setNewRecursive(false)
              }}
              style={{
                padding: '6px 16px',
                border: '1px solid #d1d5db',
                borderRadius: 6,
                background: '#fff',
                fontSize: 13,
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* List */}
      {scanPaths.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 32, color: '#9ca3af' }}>
          <FolderPlus size={32} style={{ marginBottom: 8, opacity: 0.5 }} />
          <p style={{ margin: 0 }}>No scan paths configured</p>
          <p style={{ margin: '4px 0 0', fontSize: 13 }}>Add a path to scan for local projects</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {scanPaths.map((sp) => (
            <div
              key={sp.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '12px 16px',
                background: sp.enabled ? '#fff' : '#f9fafb',
                border: '1px solid #e5e7eb',
                borderRadius: 8,
                opacity: sp.enabled ? 1 : 0.7,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontWeight: 500, fontSize: 14 }}>
                    {sp.name || sp.path.split('/').pop()}
                  </span>
                  {sp.recursive && (
                    <span style={{
                      padding: '2px 6px',
                      background: '#dbeafe',
                      color: '#1d4ed8',
                      fontSize: 10,
                      borderRadius: 4,
                    }}>
                      recursive
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                  {sp.path}
                </div>
                <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4 }}>
                  {sp.project_count} projects
                  {sp.last_scanned_at && (
                    <> · Last scan: {new Date(sp.last_scanned_at).toLocaleDateString()}</>
                  )}
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <button
                  onClick={() => handleScan(sp.id)}
                  disabled={scanning !== null || !sp.enabled}
                  title="Scan now"
                  style={{
                    padding: 6,
                    border: 'none',
                    background: 'transparent',
                    cursor: scanning || !sp.enabled ? 'not-allowed' : 'pointer',
                    opacity: scanning || !sp.enabled ? 0.4 : 1,
                    borderRadius: 4,
                  }}
                >
                  <Play size={16} color={scanning === sp.id ? '#3b82f6' : '#6b7280'} />
                </button>
                <button
                  onClick={() => handleToggleEnabled(sp)}
                  title={sp.enabled ? 'Disable' : 'Enable'}
                  style={{
                    padding: 6,
                    border: 'none',
                    background: 'transparent',
                    cursor: 'pointer',
                    borderRadius: 4,
                  }}
                >
                  {sp.enabled ? (
                    <ToggleRight size={18} color="#22c55e" />
                  ) : (
                    <ToggleLeft size={18} color="#9ca3af" />
                  )}
                </button>
                <button
                  onClick={() => handleDelete(sp.id)}
                  title="Delete"
                  style={{
                    padding: 6,
                    border: 'none',
                    background: 'transparent',
                    cursor: 'pointer',
                    borderRadius: 4,
                  }}
                >
                  <Trash2 size={16} color="#ef4444" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
