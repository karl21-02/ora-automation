import type { RefObject } from 'react'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Conversation, Organization } from '../types'

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
  onDeleteConversation: (id: string) => void
  onRenameConversation: (id: string, title: string) => void
  orgs: Organization[]
  searchInputRef?: RefObject<HTMLInputElement | null>
}

export default function ChatList({
  conversations,
  activeConversationId,
  onSelectConversation,
  onDeleteConversation,
  onRenameConversation,
  orgs,
  searchInputRef,
}: Props) {
  const [searchQuery, setSearchQuery] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingTitle, setEditingTitle] = useState('')
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)
  const editInputRef = useRef<HTMLInputElement>(null)

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
      (c) => (c.title || 'New conversation').toLowerCase().includes(q)
    )
  }, [conversations, searchQuery])

  const grouped = useMemo(() => groupConversations(filtered), [filtered])

  const orgGrouped = useMemo(() => {
    if (orgs.length === 0) return null
    type OrgBucket = { orgId: string | null; orgName: string; convs: Conversation[] }
    const buckets = new Map<string, OrgBucket>()

    for (const conv of filtered) {
      const key = conv.orgId ?? '__none__'
      if (!buckets.has(key)) {
        const orgName = conv.orgId
          ? (conv.orgName ?? orgs.find((o) => o.id === conv.orgId)?.name ?? conv.orgId)
          : '미분류'
        buckets.set(key, { orgId: conv.orgId ?? null, orgName, convs: [] })
      }
      buckets.get(key)!.convs.push(conv)
    }

    const sorted = [...buckets.values()].sort((a, b) => {
      if (a.orgId === null) return 1
      if (b.orgId === null) return -1
      return a.orgName.localeCompare(b.orgName)
    })
    return sorted
  }, [filtered, orgs])

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

  const renderConvItem = (conv: Conversation) => (
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
                  setDeleteConfirmId(deleteConfirmId === conv.id ? null : conv.id)
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
  )

  const renderDateGroup = (convs: Conversation[], indent = false) => {
    const dateGrouped = groupConversations(convs)
    return DATE_GROUP_ORDER.map((group) => {
      const items = dateGrouped.get(group)
      if (!items || items.length === 0) return null
      return (
        <div key={group} style={indent ? { paddingLeft: 8 } : undefined}>
          <div className="sidebar-section-label">{group}</div>
          {items.map(renderConvItem)}
        </div>
      )
    })
  }

  return (
    <div className="sidebar-content">
      {/* Search */}
      <div style={{ padding: '8px 12px 0' }}>
        <input
          ref={searchInputRef}
          className="sidebar-search-input"
          type="text"
          placeholder="Search... (⌘K)"
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
      </div>

      {/* List */}
      <div style={{ flex: 1, overflow: 'auto', padding: '4px 0' }}>
        {orgGrouped ? (
          orgGrouped.map((bucket) => (
            <div key={bucket.orgId ?? '__none__'}>
              <div style={{
                padding: '8px 12px 2px',
                fontSize: 11,
                fontWeight: 700,
                color: '#6b7280',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
              }}>
                <span>{bucket.orgId ? '\u{1F3E2}' : '\u{1F4CE}'}</span>
                <span>{bucket.orgName}</span>
              </div>
              {renderDateGroup(bucket.convs, true)}
            </div>
          ))
        ) : (
          DATE_GROUP_ORDER.map((group) => {
            const items = grouped.get(group)
            if (!items || items.length === 0) return null
            return (
              <div key={group}>
                <div className="sidebar-section-label">{group}</div>
                {items.map(renderConvItem)}
              </div>
            )
          })
        )}

        {filtered.length === 0 && (
          <div style={{ padding: '16px 12px', color: '#9ca3af', fontSize: 13 }}>
            {searchQuery ? 'No matching conversations' : 'No conversations'}
          </div>
        )}
      </div>
    </div>
  )
}
