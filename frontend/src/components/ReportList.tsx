import { useEffect, useState } from 'react'
import { listReports } from '../lib/api'
import type { ReportListItem } from '../types'

interface Props {
  onSelectReport: (filename: string) => void
}

export default function ReportList({ onSelectReport }: Props) {
  const [reports, setReports] = useState<ReportListItem[]>([])

  useEffect(() => {
    listReports()
      .then(setReports)
      .catch(() => setReports([]))
  }, [])

  return (
    <div className="sidebar-content">
      <div style={{ flex: 1, overflow: 'auto', padding: '4px 0' }}>
        {reports.map((r) => (
          <div
            key={r.filename}
            onClick={() => onSelectReport(r.filename)}
            className="sidebar-conv-item"
            title={r.filename}
          >
            <div style={{ overflow: 'hidden' }}>
              <div style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {r.filename.split('/').pop()}
              </div>
              <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
                {r.report_type} &middot; {(r.size_bytes / 1024).toFixed(1)}KB
              </div>
            </div>
          </div>
        ))}

        {reports.length === 0 && (
          <div style={{ padding: '16px 12px', color: '#9ca3af', fontSize: 13 }}>
            No reports found
          </div>
        )}
      </div>
    </div>
  )
}
