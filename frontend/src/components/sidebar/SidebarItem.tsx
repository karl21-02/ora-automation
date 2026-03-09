import type { LucideIcon } from 'lucide-react'

interface SidebarItemProps {
  icon: LucideIcon
  label: string
  isActive: boolean
  isCollapsed: boolean
  onClick: () => void
}

export function SidebarItem({
  icon: Icon,
  label,
  isActive,
  isCollapsed,
  onClick,
}: SidebarItemProps) {
  return (
    <button
      onClick={onClick}
      className={`sidebar-nav-item ${isActive ? 'active' : ''}`}
      title={isCollapsed ? label : undefined}
    >
      <span className="nav-icon">
        <Icon size={20} />
      </span>
      <span className="nav-label">{label}</span>
    </button>
  )
}
