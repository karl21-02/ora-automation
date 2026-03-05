import { useCallback, useEffect, useState } from 'react'
import {
  createScheduledJob,
  deleteScheduledJob,
  getScheduledJobs,
  triggerScheduledJob,
  updateScheduledJob,
} from '../lib/api'
import type { ScheduledJob, ScheduledJobCreate } from '../types'

const STATUS_COLORS: Record<string, string> = {
  running: '#3b82f6',
  completed: '#22c55e',
  failed: '#ef4444',
}

function formatDate(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('ko-KR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const EMPTY_FORM: ScheduledJobCreate = {
  name: '',
  target: 'run-cycle',
  interval_minutes: 120,
  enabled: true,
  auto_publish_notion: false,
}

export default function SchedulerPanel() {
  const [jobs, setJobs] = useState<ScheduledJob[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState<ScheduledJobCreate>({ ...EMPTY_FORM })
  const [error, setError] = useState<string | null>(null)

  const loadJobs = useCallback(async () => {
    try {
      const data = await getScheduledJobs()
      setJobs(data)
    } catch {
      setError('Failed to load jobs')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadJobs() }, [loadJobs])

  const handleCreate = async () => {
    if (!form.name.trim()) return
    setError(null)
    try {
      await createScheduledJob(form)
      setShowForm(false)
      setForm({ ...EMPTY_FORM })
      await loadJobs()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Create failed')
    }
  }

  const handleToggle = async (job: ScheduledJob) => {
    try {
      await updateScheduledJob(job.id, { enabled: !job.enabled })
      await loadJobs()
    } catch {
      setError('Toggle failed')
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteScheduledJob(id)
      await loadJobs()
    } catch {
      setError('Delete failed')
    }
  }

  const handleTrigger = async (id: string) => {
    try {
      await triggerScheduledJob(id)
      await loadJobs()
    } catch {
      setError('Trigger failed')
    }
  }

  if (loading) {
    return <div style={styles.container}><p style={{ color: '#9ca3af' }}>Loading scheduler...</p></div>
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h3 style={styles.title}>Scheduler</h3>
        <button style={styles.addBtn} onClick={() => setShowForm(!showForm)}>
          {showForm ? 'Cancel' : '+ New Job'}
        </button>
      </div>

      {error && <div style={styles.error}>{error}</div>}

      {showForm && (
        <div style={styles.form}>
          <input
            style={styles.input}
            placeholder="Job name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <select
            style={styles.input}
            value={form.target}
            onChange={(e) => setForm({ ...form, target: e.target.value })}
          >
            <option value="run-cycle">run-cycle</option>
            <option value="run-cycle-deep">run-cycle-deep</option>
            <option value="run">run</option>
            <option value="qa-program">qa-program</option>
          </select>
          <input
            style={styles.input}
            type="number"
            placeholder="Interval (minutes)"
            value={form.interval_minutes ?? ''}
            onChange={(e) => setForm({ ...form, interval_minutes: e.target.value ? Number(e.target.value) : undefined })}
          />
          <input
            style={styles.input}
            placeholder="Cron (e.g. 0 2,10,18 * * *)"
            value={form.cron_expression ?? ''}
            onChange={(e) => setForm({ ...form, cron_expression: e.target.value || undefined })}
          />
          <label style={styles.checkbox}>
            <input
              type="checkbox"
              checked={form.auto_publish_notion}
              onChange={(e) => setForm({ ...form, auto_publish_notion: e.target.checked })}
            />
            Auto-publish to Notion
          </label>
          <button style={styles.submitBtn} onClick={handleCreate}>Create</button>
        </div>
      )}

      {jobs.length === 0 ? (
        <p style={{ color: '#9ca3af', fontSize: 13, textAlign: 'center', padding: 20 }}>
          No scheduled jobs yet
        </p>
      ) : (
        <div style={styles.jobList}>
          {jobs.map((job) => (
            <div key={job.id} style={styles.jobCard}>
              <div style={styles.jobHeader}>
                <span style={{ fontWeight: 600, fontSize: 13 }}>{job.name}</span>
                <button
                  style={{
                    ...styles.toggleBtn,
                    background: job.enabled ? '#22c55e' : '#6b7280',
                  }}
                  onClick={() => handleToggle(job)}
                >
                  {job.enabled ? 'ON' : 'OFF'}
                </button>
              </div>
              <div style={styles.jobMeta}>
                <span>Target: {job.target}</span>
                {job.interval_minutes && <span>Every {job.interval_minutes}m</span>}
                {job.cron_expression && <span>Cron: {job.cron_expression}</span>}
              </div>
              <div style={styles.jobMeta}>
                <span>Next: {formatDate(job.next_run_at)}</span>
                <span>Last: {formatDate(job.last_run_at)}</span>
                {job.last_run_status && (
                  <span style={{ color: STATUS_COLORS[job.last_run_status] ?? '#9ca3af' }}>
                    {job.last_run_status}
                  </span>
                )}
              </div>
              {job.auto_publish_notion && (
                <div style={{ fontSize: 11, color: '#8b5cf6', marginTop: 2 }}>Notion auto-publish</div>
              )}
              <div style={styles.jobActions}>
                <button style={styles.actionBtn} onClick={() => handleTrigger(job.id)}>Run Now</button>
                <button style={{ ...styles.actionBtn, color: '#ef4444' }} onClick={() => handleDelete(job.id)}>Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: 16,
    height: '100%',
    overflowY: 'auto',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  title: {
    margin: 0,
    fontSize: 15,
    fontWeight: 600,
    color: '#1f2937',
  },
  addBtn: {
    background: '#3b82f6',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    padding: '4px 10px',
    fontSize: 12,
    cursor: 'pointer',
  },
  error: {
    background: '#fef2f2',
    color: '#ef4444',
    padding: '6px 10px',
    borderRadius: 6,
    fontSize: 12,
    marginBottom: 8,
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    marginBottom: 12,
    padding: 12,
    background: '#f9fafb',
    borderRadius: 8,
  },
  input: {
    padding: '6px 8px',
    border: '1px solid #d1d5db',
    borderRadius: 6,
    fontSize: 13,
    outline: 'none',
  },
  checkbox: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    fontSize: 13,
    color: '#374151',
  },
  submitBtn: {
    background: '#22c55e',
    color: '#fff',
    border: 'none',
    borderRadius: 6,
    padding: '6px 12px',
    fontSize: 13,
    cursor: 'pointer',
  },
  jobList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  jobCard: {
    padding: 10,
    background: '#f9fafb',
    borderRadius: 8,
    border: '1px solid #e5e7eb',
  },
  jobHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  toggleBtn: {
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    padding: '2px 8px',
    fontSize: 11,
    cursor: 'pointer',
    fontWeight: 600,
  },
  jobMeta: {
    display: 'flex',
    gap: 12,
    fontSize: 11,
    color: '#6b7280',
    marginTop: 2,
  },
  jobActions: {
    display: 'flex',
    gap: 8,
    marginTop: 6,
  },
  actionBtn: {
    background: 'none',
    border: '1px solid #d1d5db',
    borderRadius: 4,
    padding: '2px 8px',
    fontSize: 11,
    cursor: 'pointer',
    color: '#374151',
  },
}
