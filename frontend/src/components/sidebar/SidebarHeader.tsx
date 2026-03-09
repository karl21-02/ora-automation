import { ChevronLeft, Plus } from 'lucide-react'
import { APP_NAME } from '../../lib/constants'

interface SidebarHeaderProps {
  isCollapsed: boolean
  onToggle: () => void
  onNewChat: () => void
}

export function SidebarHeader({ isCollapsed, onToggle, onNewChat }: SidebarHeaderProps) {
  return (
    <div className="sidebar-header">
      <span className="sidebar-header-title">{APP_NAME}</span>
      <div className="sidebar-header-actions">
        {!isCollapsed && (
          <button onClick={onNewChat} title="New Chat (⌘N)" className="sidebar-icon-btn">
            <Plus size={18} />
          </button>
        )}
        <button
          onClick={onToggle}
          title={isCollapsed ? 'Expand (⌘B)' : 'Collapse (⌘B)'}
          className="sidebar-icon-btn"
        >
          <span className="sidebar-toggle-icon">
            <ChevronLeft size={18} />
          </span>
        </button>
      </div>
    </div>
  )
}
