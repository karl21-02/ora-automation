import type { RefObject } from 'react'
import type { Conversation, Organization } from '../types'
import { MAIN_MENU_ITEMS, BOTTOM_MENU_ITEMS, type MenuId } from '../lib/sidebarConfig'
import { SidebarHeader } from './sidebar/SidebarHeader'
import { SidebarItem } from './sidebar/SidebarItem'
import ChatList from './ChatList'
import ReportList from './ReportList'

interface Props {
  conversations: Conversation[]
  activeConversationId: string | null
  onSelectConversation: (id: string) => void
  onNewConversation: (orgId?: string | null) => void
  onSelectReport: (filename: string) => void
  onDeleteConversation: (id: string) => void
  onRenameConversation: (id: string, title: string) => void
  activeMenu: MenuId
  onMenuChange: (menu: MenuId) => void
  orgs: Organization[]
  isCollapsed: boolean
  onToggle: () => void
  searchInputRef: RefObject<HTMLInputElement | null>
  badges?: Partial<Record<MenuId, number>>
  isMobile?: boolean
  mobileOpen?: boolean
  width?: number
  onResizeStart?: (e: React.MouseEvent) => void
}

export default function Sidebar({
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewConversation,
  onSelectReport,
  onDeleteConversation,
  onRenameConversation,
  activeMenu,
  onMenuChange,
  orgs,
  isCollapsed,
  onToggle,
  searchInputRef,
  badges = {},
  isMobile = false,
  mobileOpen = false,
  width = 260,
  onResizeStart,
}: Props) {
  const handleMenuClick = (menuId: MenuId) => {
    onMenuChange(menuId)
  }

  // Build class names
  const classNames = ['sidebar']
  if (isCollapsed && !isMobile) classNames.push('collapsed')
  if (isMobile && mobileOpen) classNames.push('mobile-open')

  // Dynamic width style (only when not collapsed and not on mobile)
  const sidebarStyle: React.CSSProperties = {}
  if (!isCollapsed && !isMobile) {
    sidebarStyle.width = width
    sidebarStyle.minWidth = width
  }

  return (
    <div className={classNames.join(' ')} style={sidebarStyle}>
      {/* Header */}
      <SidebarHeader
        isCollapsed={isCollapsed}
        onToggle={onToggle}
        onNewChat={() => onNewConversation()}
      />

      {/* Main Navigation */}
      <nav className="sidebar-nav">
        {MAIN_MENU_ITEMS.map((item) => (
          <SidebarItem
            key={item.id}
            icon={item.icon}
            label={item.label}
            isActive={activeMenu === item.id}
            isCollapsed={isCollapsed && !isMobile}
            onClick={() => handleMenuClick(item.id as MenuId)}
            badge={badges[item.id as MenuId]}
          />
        ))}
      </nav>

      {/* Content Area (hidden when collapsed, but always visible on mobile) */}
      {(isMobile || !isCollapsed) && activeMenu === 'chats' && (
        <ChatList
          conversations={conversations}
          activeConversationId={activeConversationId}
          onSelectConversation={onSelectConversation}
          onDeleteConversation={onDeleteConversation}
          onRenameConversation={onRenameConversation}
          orgs={orgs}
          searchInputRef={searchInputRef}
        />
      )}

      {(isMobile || !isCollapsed) && activeMenu === 'reports' && (
        <ReportList onSelectReport={onSelectReport} />
      )}

      {/* Bottom Navigation */}
      <div className="sidebar-bottom">
        {BOTTOM_MENU_ITEMS.map((item) => (
          <SidebarItem
            key={item.id}
            icon={item.icon}
            label={item.label}
            isActive={activeMenu === item.id}
            isCollapsed={isCollapsed && !isMobile}
            onClick={() => handleMenuClick(item.id as MenuId)}
            badge={badges[item.id as MenuId]}
          />
        ))}
      </div>

      {/* Resize Handle (desktop only, when not collapsed) */}
      {!isMobile && !isCollapsed && onResizeStart && (
        <div
          className="sidebar-resize-handle"
          onMouseDown={onResizeStart}
        />
      )}
    </div>
  )
}
