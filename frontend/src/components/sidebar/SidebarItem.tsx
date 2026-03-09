import type { LucideIcon } from 'lucide-react'
import { Tooltip } from './Tooltip'

interface SidebarItemProps {
  icon: LucideIcon
  label: string
  isActive: boolean
  isCollapsed: boolean
  onClick: () => void
  badge?: number | null
}

export function SidebarItem({
  icon: Icon,
  label,
  isActive,
  isCollapsed,
  onClick,
  badge,
}: SidebarItemProps) {
  const button = (
    <button
      onClick={onClick}
      className={`sidebar-nav-item ${isActive ? 'active' : ''}`}
    >
      <span className="nav-icon">
        <Icon size={20} />
        {badge != null && badge > 0 && (
          <span className="nav-badge">{badge > 99 ? '99+' : badge}</span>
        )}
      </span>
      <span className="nav-label">{label}</span>
    </button>
  )

  return (
    <Tooltip content={label} disabled={!isCollapsed}>
      {button}
    </Tooltip>
  )
}
