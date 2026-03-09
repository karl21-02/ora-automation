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
}: Props) {
  const handleMenuClick = (menuId: MenuId) => {
    onMenuChange(menuId)
  }

  return (
    <div className={`sidebar ${isCollapsed ? 'collapsed' : ''}`}>
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
            isCollapsed={isCollapsed}
            onClick={() => handleMenuClick(item.id as MenuId)}
          />
        ))}
      </nav>

      {/* Content Area (hidden when collapsed) */}
      {!isCollapsed && activeMenu === 'chats' && (
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

      {!isCollapsed && activeMenu === 'reports' && (
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
            isCollapsed={isCollapsed}
            onClick={() => handleMenuClick(item.id as MenuId)}
          />
        ))}
      </div>
    </div>
  )
}
