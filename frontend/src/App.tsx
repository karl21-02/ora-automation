import { useCallback, useEffect, useState } from 'react'
import ChatWindow from './components/ChatWindow'
import ReportViewer from './components/ReportViewer'
import Sidebar from './components/Sidebar'
import { createConversation, getConversation, listConversations } from './lib/api'
import type { Conversation, Message } from './types'

const ACTIVE_KEY = 'ora-chatbot-active-id'

function newConversation(): Conversation {
  return {
    id: crypto.randomUUID(),
    title: '',
    messages: [],
    createdAt: new Date(),
  }
}

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<string>('')
  const [reportFile, setReportFile] = useState<string | null>(null)
  const [dbReady, setDbReady] = useState(false)

  // Load conversations from DB on mount
  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const { items } = await listConversations()
        if (cancelled) return

        if (items.length > 0) {
          // Load full details for each conversation (messages)
          const convs: Conversation[] = await Promise.all(
            items.map(async (item) => {
              try {
                const detail = await getConversation(item.id)
                return {
                  id: detail.id,
                  title: detail.title,
                  createdAt: new Date(detail.created_at),
                  messages: detail.messages.map((m) => ({
                    id: String(m.id),
                    role: m.role as 'user' | 'assistant',
                    content: m.content,
                    plan: m.plan ? { target: m.plan.target, env: m.plan.env } : undefined,
                    runId: m.run_id,
                    timestamp: new Date(m.created_at),
                  })),
                }
              } catch {
                return {
                  id: item.id,
                  title: item.title,
                  createdAt: new Date(item.created_at),
                  messages: [],
                }
              }
            })
          )
          setConversations(convs)
          const savedActive = localStorage.getItem(ACTIVE_KEY)
          if (savedActive && convs.some((c) => c.id === savedActive)) {
            setActiveId(savedActive)
          } else {
            setActiveId(convs[0].id)
          }
        } else {
          // No DB conversations — create a fresh one
          const conv = newConversation()
          try {
            await createConversation(conv.id, conv.title)
          } catch {
            // DB may be unavailable — still work locally
          }
          setConversations([conv])
          setActiveId(conv.id)
        }
      } catch {
        // DB unavailable — start with local empty conversation
        const conv = newConversation()
        setConversations([conv])
        setActiveId(conv.id)
      }
      setDbReady(true)
    }
    load()
    return () => { cancelled = true }
  }, [])

  // Save active ID to localStorage
  useEffect(() => {
    if (activeId) localStorage.setItem(ACTIVE_KEY, activeId)
  }, [activeId])

  const activeConv = conversations.find((c) => c.id === activeId) ?? conversations[0]

  const handleNewMessage = useCallback((msg: Message) => {
    setConversations((prev) =>
      prev.map((c) => {
        if (c.id !== activeId) return c
        const msgs = [...c.messages, msg]
        const title = c.title || (msg.role === 'user' ? msg.content.slice(0, 40) : c.title)
        return { ...c, messages: msgs, title }
      })
    )
  }, [activeId])

  const handleUpdateMessage = useCallback((msgId: string, updates: Partial<Message>) => {
    setConversations((prev) =>
      prev.map((c) => {
        if (c.id !== activeId) return c
        return {
          ...c,
          messages: c.messages.map((m) =>
            m.id === msgId ? { ...m, ...updates } : m
          ),
        }
      })
    )
  }, [activeId])

  const handleNewConversation = useCallback(async () => {
    const conv = newConversation()
    try {
      await createConversation(conv.id, conv.title)
    } catch {
      // proceed locally even if DB fails
    }
    setConversations((prev) => [conv, ...prev])
    setActiveId(conv.id)
  }, [])

  if (!dbReady || !activeConv) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100vh',
        color: '#9ca3af',
        fontSize: 15,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      }}>
        Loading...
      </div>
    )
  }

  return (
    <div style={{
      display: 'flex',
      height: '100vh',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      color: '#1f2937',
    }}>
      <Sidebar
        conversations={conversations}
        activeConversationId={activeId}
        onSelectConversation={setActiveId}
        onNewConversation={handleNewConversation}
        onSelectReport={setReportFile}
      />
      <ChatWindow
        key={activeConv.id}
        messages={activeConv.messages}
        onNewMessage={handleNewMessage}
        onUpdateMessage={handleUpdateMessage}
        conversationId={activeConv.id}
      />
      {reportFile && (
        <ReportViewer
          filename={reportFile}
          onClose={() => setReportFile(null)}
        />
      )}
    </div>
  )
}
