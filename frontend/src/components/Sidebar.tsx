import { useEffect, useMemo, useRef, useState } from 'react'
import { listReports } from '../lib/api'
import { APP_NAME } from '../lib/constants'
import type { Conversation, ReportListItem } from '../types'

type DateGroup = 'Today' | 'Yesterday' | 'Previous 7 Days' | 'Previous 30 Days' | 'Older'

const DATE_GROUP_ORDER: DateGroup[] = [
  'Today',
  'Yesterday',
  'Previous 7 Days',
  'Previous 30 Days',
  'Older',
]

function getDateGroup(date: Date): DateGroup {
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const diff = startOfToday.getTime() - new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
  const days = diff / (1000 * 60 * 60 * 24)

  if (days < 0 || days === 0) return 'Today'
  if (days === 1) return 'Yesterday'
  if (days <= 7) return 'Previous 7 Days'
  if (days <= 30) return 'Previous 30 Days'
  return 'Older'
}

function groupConversations(convs: Conversation[]): Map<DateGroup, Conversation[]> {
  const groups = new Map<DateGroup, Conversation[]>()
  for (const conv of convs) {
    const group = getDateGroup(conv.createdAt)
    const list = groups.get(group) ?? []
    list.push(conv)
    groups.set(group, list)
  }
  return groups
}

interface Props {
  conversations: Conversation[]
  activeConversationId: string | null
  onSelectConversation: (id: string) => void
  onNewConversation: () => void
  onSelectReport: (filename: string) => void
  onDeleteConversation: (id: string) => void
  onRenameConversation: (id: string, title: string) => void
}

export default function Sidebar({
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewConversation,
  onSelectReport,
  onDeleteConversation,
  onRenameConversation,
}: Props) {
  const [reports, setReports] = useState<ReportListItem[]>([])
  const [tab, setTab] = useState<'chats' | 'reports'>('chats')
  const [searchQuery, setSearchQuery] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState('')
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)
  const editInputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (tab === 'reports') {
      listReports()
        .then(setReports)
        .catch(() => setReports([]))
    }
  }, [tab])

  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus()
      editInputRef.current.select()
    }
  }, [editingId])

  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return conversations
    const q = searchQuery.toLowerCase()
    return conversations.filter(
      (c) =>
        (c.title || 'New conversation').toLowerCase().includes(q)
    )
  }, [conversations, searchQuery])

  const grouped = useMemo(() => groupConversations(filtered), [filtered])

  const startRename = (id: string, currentTitle: string) => {
    setEditingId(id)
    setEditingTitle(currentTitle || '')
    setDeleteConfirmId(null)
  }

  const commitRename = () => {
    if (editingId && editingTitle.trim()) {
      onRenameConversation(editingId, editingTitle.trim())
    }
    setEditingId(null)
    setEditingTitle('')
  }

  const cancelRename = () => {
    setEditingId(null)
    setEditingTitle('')
  }

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
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <span style={{ fontWeight: 700, fontSize: 16, color: '#1f2937' }}>
          {APP_NAME}
        </span>
        <button
          onClick={onNewConversation}
          title="New Chat"
          style={{
            width: 28,
            height: 28,
            borderRadius: 6,
            border: '1px solid #d1d5db',
            backgroundColor: '#fff',
            cursor: 'pointer',
            fontWeight: 500,
            fontSize: 16,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#374151',
            lineHeight: 1,
          }}
        >
          +
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

      {/* Search (chats tab only) */}
      {tab === 'chats' && (
        <div style={{ padding: '8px 12px 0' }}>
          <input
            className="sidebar-search-input"
            type="text"
            placeholder="Search..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      )}

      {/* List */}
      <div style={{ flex: 1, overflow: 'auto', padding: '4px 0' }}>
        {tab === 'chats' && DATE_GROUP_ORDER.map((group) => {
          const items = grouped.get(group)
          if (!items || items.length === 0) return null
          return (
            <div key={group}>
              <div className="sidebar-section-label">{group}</div>
              {items.map((conv) => (
                <div key={conv.id}>
                  <div
                    className={`sidebar-conv-item${conv.id === activeConversationId ? ' active' : ''}`}
                    onClick={() => {
                      onSelectConversation(conv.id)
                      setDeleteConfirmId(null)
                    }}
                  >
                    {editingId === conv.id ? (
                      <input
                        ref={editInputRef}
                        className="sidebar-search-input"
                        value={editingTitle}
                        onChange={(e) => setEditingTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') commitRename()
                          if (e.key === 'Escape') cancelRename()
                        }}
                        onBlur={commitRename}
                        onClick={(e) => e.stopPropagation()}
                        style={{ padding: '2px 6px', fontSize: 13 }}
                      />
                    ) : (
                      <>
                        <span style={{
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          flex: 1,
                        }}>
                          {conv.title || 'New conversation'}
                        </span>
                        <span className="conv-actions">
                          <button
                            title="Rename"
                            onClick={(e) => {
                              e.stopPropagation()
                              startRename(conv.id, conv.title)
                            }}
                          >
                            &#9998;
                          </button>
                          <button
                            title="Delete"
                            onClick={(e) => {
                              e.stopPropagation()
                              setDeleteConfirmId(
                                deleteConfirmId === conv.id ? null : conv.id
                              )
                            }}
                          >
                            &#128465;
                          </button>
                        </span>
                      </>
                    )}
                  </div>
                  {deleteConfirmId === conv.id && (
                    <div className="sidebar-delete-confirm">
                      <div style={{ marginBottom: 4 }}>Delete this conversation?</div>
                      <button
                        className="btn-delete"
                        onClick={() => {
                          onDeleteConversation(conv.id)
                          setDeleteConfirmId(null)
                        }}
                      >
                        Delete
                      </button>
                      <button
                        className="btn-cancel"
                        onClick={() => setDeleteConfirmId(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )
        })}

        {tab === 'chats' && filtered.length === 0 && (
          <div style={{ padding: '16px 12px', color: '#9ca3af', fontSize: 13 }}>
            {searchQuery ? 'No matching conversations' : 'No conversations'}
          </div>
        )}

        {tab === 'reports' && reports.map((r) => (
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

        {tab === 'reports' && reports.length === 0 && (
          <div style={{ padding: '16px 12px', color: '#9ca3af', fontSize: 13 }}>
            No reports found
          </div>
        )}
      </div>
    </div>
  )
}
