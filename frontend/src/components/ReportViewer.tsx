import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { getReport } from '../lib/api'

interface Props {
  filename: string
  onClose: () => void
}

export default function ReportViewer({ filename, onClose }: Props) {
  const [content, setContent] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getReport(filename)
      .then(setContent)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [filename])

  const isJson = filename.endsWith('.json')

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
        backgroundColor: '#fff',
        borderRadius: 12,
        width: '80vw',
        maxWidth: 900,
        height: '80vh',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderBottom: '1px solid #e5e7eb',
        }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {filename}
          </h3>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              fontSize: 20,
              cursor: 'pointer',
              color: '#6b7280',
              lineHeight: 1,
            }}
          >
            &times;
          </button>
        </div>

        {/* Content */}
        <div style={{
          flex: 1,
          overflow: 'auto',
          padding: 20,
          fontSize: 14,
          lineHeight: 1.7,
        }}>
          {loading && <p style={{ color: '#9ca3af' }}>Loading...</p>}
          {error && <p style={{ color: '#ef4444' }}>{error}</p>}
          {!loading && !error && (
            isJson ? (
              <pre style={{
                backgroundColor: '#f9fafb',
                padding: 16,
                borderRadius: 8,
                overflow: 'auto',
                fontSize: 13,
                lineHeight: 1.5,
              }}>
                {content}
              </pre>
            ) : (
              <div className="markdown-body">
                <ReactMarkdown>{content}</ReactMarkdown>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  )
}
