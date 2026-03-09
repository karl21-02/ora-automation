import { Menu } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import ChatWindow from './components/ChatWindow'
import OrgPanel from './components/OrgPanel'
import ReportViewer from './components/ReportViewer'
import SchedulerPanel from './components/SchedulerPanel'
import SettingsPanel from './components/SettingsPanel'
import Sidebar from './components/Sidebar'
import { createConversation, deleteConversation, getConversation, listConversations, listOrgs, renameConversation, updateConversationOrg } from './lib/api'
import { useKeyboardShortcuts } from './lib/hooks/useKeyboardShortcuts'
import { useIsMobile } from './lib/hooks/useMediaQuery'
import { useRunningCount } from './lib/hooks/useRunningCount'
import { useSidebarResize } from './lib/hooks/useSidebarResize'
import { useSidebarState } from './lib/hooks/useSidebarState'
import { MENU_ITEMS, type MenuId } from './lib/sidebarConfig'
import type { Conversation, Message, Organization } from './types'

const ACTIVE_KEY = 'ora-chatbot-active-id'

function newConversation(orgId?: string | null): Conversation {
  return {
    id: crypto.randomUUID(),
    title: '',
    messages: [],
    createdAt: new Date(),
    orgId: orgId ?? null,
    orgName: null,
  }
}

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<string>('')
  const [reportFile, setReportFile] = useState<string | null>(null)
  const [activeMenu, setActiveMenu] = useState<MenuId>('chats')
  const [dbReady, setDbReady] = useState(false)
  const [orgs, setOrgs] = useState<Organization[]>([])
  const { isCollapsed, toggle: toggleSidebar } = useSidebarState()
  const searchInputRef = useRef<HTMLInputElement>(null)
  const runningCount = useRunningCount()
  const isMobile = useIsMobile()
  const [mobileOpen, setMobileOpen] = useState(false)
  const { width: sidebarWidth, handleMouseDown: handleResizeStart } = useSidebarResize()

  // Close mobile sidebar when switching away from mobile view
  useEffect(() => {
    if (!isMobile) setMobileOpen(false)
  }, [isMobile])

  const refreshOrgs = useCallback(() => {
    listOrgs().then(({ items }) => setOrgs(items)).catch(() => setOrgs([]))
  }, [])

  // Keyboard shortcuts
  useKeyboardShortcuts({
    onToggleSidebar: toggleSidebar,
    onNewChat: () => handleNewConversation(),
    onFocusSearch: () => {
      if (isCollapsed) toggleSidebar()
      setActiveMenu('chats')
      setTimeout(() => searchInputRef.current?.focus(), 100)
    },
    onNavigateMenu: (index) => {
      const menu = MENU_ITEMS[index]
      if (menu) setActiveMenu(menu.id as MenuId)
    },
  })

  // Load conversations from DB on mount
  useEffect(() => {
    refreshOrgs()
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
                  orgId: detail.org_id ?? null,
                  orgName: detail.org_name ?? null,
                  createdAt: new Date(detail.created_at),
                  messages: detail.messages.map((m) => {
                    const planData = m.plan as Record<string, unknown> | null
                    const msg: Message = {
                      id: String(m.id),
                      role: m.role as 'user' | 'assistant',
                      content: m.content,
                      runId: m.run_id,
                      timestamp: new Date(m.created_at),
                    }
                    if (planData) {
                      if ('plans' in planData && Array.isArray(planData.plans)) {
                        msg.plans = planData.plans as Message['plans']
                      } else if ('choices' in planData && Array.isArray(planData.choices)) {
                        msg.choices = planData.choices as Message['choices']
                      } else if ('project_select' in planData && Array.isArray(planData.project_select)) {
                        msg.projectSelect = planData.project_select as Message['projectSelect']
                      } else if ('target' in planData) {
                        msg.plan = {
                          target: planData.target as string,
                          env: (planData.env as Record<string, string>) || {},
                          label: (planData.label as string) || undefined,
                        }
                      }
                    }
                    return msg
                  }),
                }
              } catch {
                return {
                  id: item.id,
                  title: item.title,
                  orgId: item.org_id ?? null,
                  orgName: item.org_name ?? null,
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

  const handleNewConversation = useCallback(async (orgId?: string | null) => {
    const conv = newConversation(orgId)
    try {
      await createConversation(conv.id, conv.title, orgId)
    } catch {
      // proceed locally even if DB fails
    }
    setConversations((prev) => [conv, ...prev])
    setActiveId(conv.id)
  }, [])

  const handleDeleteConversation = useCallback(async (id: string) => {
    try {
      await deleteConversation(id)
    } catch {
      // proceed locally even if DB fails
    }
    setConversations((prev) => {
      const remaining = prev.filter((c) => c.id !== id)
      if (remaining.length === 0) {
        const conv = newConversation()
        createConversation(conv.id, conv.title).catch(() => {})
        setActiveId(conv.id)
        return [conv]
      }
      if (id === activeId) {
        setActiveId(remaining[0].id)
      }
      return remaining
    })
  }, [activeId])

  const handleChangeConversationOrg = useCallback(async (convId: string, orgId: string | null) => {
    const orgName = orgId ? orgs.find((o) => o.id === orgId)?.name ?? null : null
    setConversations((prev) =>
      prev.map((c) => (c.id === convId ? { ...c, orgId, orgName } : c))
    )
    try {
      await updateConversationOrg(convId, orgId)
    } catch {
      // local state already updated
    }
  }, [orgs])

  const handleRenameConversation = useCallback(async (id: string, title: string) => {
    setConversations((prev) =>
      prev.map((c) => (c.id === id ? { ...c, title } : c))
    )
    try {
      await renameConversation(id, title)
    } catch {
      // local state already updated
    }
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

  const handleMobileClose = useCallback(() => {
    if (isMobile) setMobileOpen(false)
  }, [isMobile])

  return (
    <div style={{
      display: 'flex',
      height: '100vh',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      color: '#1f2937',
    }}>
      {/* Mobile menu button */}
      <button
        className="mobile-menu-btn"
        onClick={() => setMobileOpen(true)}
        aria-label="Open menu"
      >
        <Menu size={24} />
      </button>

      {/* Mobile backdrop */}
      <div
        className={`sidebar-backdrop ${mobileOpen ? 'visible' : ''}`}
        onClick={() => setMobileOpen(false)}
      />

      <Sidebar
        conversations={conversations}
        activeConversationId={activeId}
        onSelectConversation={(id) => { setActiveMenu('chats'); setActiveId(id); handleMobileClose() }}
        onNewConversation={(orgId) => { setActiveMenu('chats'); handleNewConversation(orgId); handleMobileClose() }}
        onSelectReport={(f) => { setReportFile(f); handleMobileClose() }}
        onDeleteConversation={handleDeleteConversation}
        onRenameConversation={handleRenameConversation}
        activeMenu={activeMenu}
        onMenuChange={(menu) => { setActiveMenu(menu); handleMobileClose() }}
        orgs={orgs}
        isCollapsed={isCollapsed}
        onToggle={toggleSidebar}
        searchInputRef={searchInputRef}
        badges={{ scheduler: runningCount }}
        isMobile={isMobile}
        mobileOpen={mobileOpen}
        width={sidebarWidth}
        onResizeStart={handleResizeStart}
      />
      {activeMenu === 'chats' && (
        <ChatWindow
          key={activeConv.id}
          messages={activeConv.messages}
          onNewMessage={handleNewMessage}
          onUpdateMessage={handleUpdateMessage}
          conversationId={activeConv.id}
          orgId={activeConv.orgId ?? null}
          orgName={activeConv.orgName ?? null}
          orgs={orgs}
          onChangeOrg={(orgId) => handleChangeConversationOrg(activeConv.id, orgId)}
        />
      )}
      {activeMenu === 'reports' && (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#9ca3af' }}>
          Select a report from the sidebar
        </div>
      )}
      {activeMenu === 'orgs' && (
        <OrgPanel onOrgsChanged={refreshOrgs} />
      )}
      {activeMenu === 'scheduler' && (
        <SchedulerPanel />
      )}
      {activeMenu === 'settings' && (
        <SettingsPanel />
      )}
      {reportFile && (
        <ReportViewer
          filename={reportFile}
          onClose={() => setReportFile(null)}
        />
      )}
    </div>
  )
}
