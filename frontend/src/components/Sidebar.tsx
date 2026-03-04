import { useEffect, useState } from 'react'
import { listReports } from '../lib/api'
import type { Conversation, ReportListItem } from '../types'

interface Props {
  conversations: Conversation[]
  activeConversationId: string | null
  onSelectConversation: (id: string) => void
  onNewConversation: () => void
  onSelectReport: (filename: string) => void
}

export default function Sidebar({
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewConversation,
  onSelectReport,
}: Props) {
  const [reports, setReports] = useState<ReportListItem[]>([])
  const [tab, setTab] = useState<'chats' | 'reports'>('chats')

  useEffect(() => {
    if (tab === 'reports') {
      listReports()
        .then(setReports)
        .catch(() => setReports([]))
    }
  }, [tab])

  return (
    <div style={{
      width: 260,
      minWidth: 260,
      height: '100%',
      borderRight: '1px solid #e5e7eb',
      display: 'flex',
      flexDirection: 'column',
      backgroundColor: '#f9fafb',
    }}>
      {/* Header */}
      <div style={{
        padding: '16px 12px 8px',
        fontWeight: 700,
        fontSize: 16,
        color: '#1f2937',
      }}>
        Ora Chatbot
      </div>

      {/* New chat button */}
      <div style={{ padding: '0 12px 8px' }}>
        <button
          onClick={onNewConversation}
          style={{
            width: '100%',
            padding: '8px 0',
            borderRadius: 8,
            border: '1px solid #d1d5db',
            backgroundColor: '#fff',
            cursor: 'pointer',
            fontWeight: 500,
            fontSize: 13,
          }}
        >
          + New Chat
        </button>
      </div>

      {/* Tabs */}
      <div style={{
        display: 'flex',
        borderBottom: '1px solid #e5e7eb',
      }}>
        {(['chats', 'reports'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              flex: 1,
              padding: '8px 0',
              border: 'none',
              backgroundColor: 'transparent',
              borderBottom: tab === t ? '2px solid #2563eb' : '2px solid transparent',
              color: tab === t ? '#2563eb' : '#6b7280',
              fontWeight: 500,
              fontSize: 13,
              cursor: 'pointer',
            }}
          >
            {t === 'chats' ? 'Chats' : 'Reports'}
          </button>
        ))}
      </div>

      {/* List */}
      <div style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
        {tab === 'chats' && conversations.map((conv) => (
          <div
            key={conv.id}
            onClick={() => onSelectConversation(conv.id)}
            style={{
              padding: '8px 12px',
              margin: '0 8px 2px',
              borderRadius: 6,
              cursor: 'pointer',
              backgroundColor: conv.id === activeConversationId ? '#e5e7eb' : 'transparent',
              fontSize: 13,
              color: '#374151',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {conv.title || 'New conversation'}
          </div>
        ))}

        {tab === 'reports' && reports.map((r) => (
          <div
            key={r.filename}
            onClick={() => onSelectReport(r.filename)}
            style={{
              padding: '8px 12px',
              margin: '0 8px 2px',
              borderRadius: 6,
              cursor: 'pointer',
              fontSize: 12,
              color: '#374151',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={r.filename}
          >
            <div style={{ fontWeight: 500 }}>{r.filename.split('/').pop()}</div>
            <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
              {r.report_type} &middot; {(r.size_bytes / 1024).toFixed(1)}KB
            </div>
          </div>
        ))}

        {tab === 'reports' && reports.length === 0 && (
          <div style={{ padding: '16px 12px', color: '#9ca3af', fontSize: 13 }}>
            No reports found
          </div>
        )}
      </div>
    </div>
  )
}
