import { useEffect, useState } from 'react'
import { listReports } from '../lib/api'
import type { ReportListItem } from '../types'
import { SkeletonList } from './Skeleton'

interface Props {
  onSelectReport: (filename: string) => void
}

export default function ReportList({ onSelectReport }: Props) {
  const [reports, setReports] = useState<ReportListItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    listReports()
      .then(setReports)
      .catch(() => setReports([]))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="sidebar-content">
      <div style={{ flex: 1, overflow: 'auto', padding: '4px 0' }}>
        {loading ? (
          <div style={{ padding: '8px 12px' }}>
            <SkeletonList count={4} itemHeight={44} gap={4} />
          </div>
        ) : reports.length === 0 ? (
          <div className="sidebar-empty-state">
            No reports found
          </div>
        ) : (
          reports.map((r) => (
            <div
              key={r.filename}
              onClick={() => onSelectReport(r.filename)}
              className="sidebar-conv-item"
              title={r.filename}
            >
              <div style={{ overflow: 'hidden' }}>
                <div className="report-item-title">
                  {r.filename.split('/').pop()}
                </div>
                <div className="report-item-meta">
                  {r.report_type} &middot; {(r.size_bytes / 1024).toFixed(1)}KB
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
