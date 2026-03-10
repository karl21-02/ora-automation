import type { ReactNode } from 'react'
import { FileText, FolderOpen, Inbox, MessageSquare, Search, Settings, Users } from 'lucide-react'

type IconType = 'inbox' | 'folder' | 'file' | 'search' | 'users' | 'chat' | 'settings'

interface EmptyStateProps {
  icon?: IconType
  title: string
  description?: string
  action?: {
    label: string
    onClick: () => void
  }
  className?: string
  children?: ReactNode
}

const ICONS: Record<IconType, typeof Inbox> = {
  inbox: Inbox,
  folder: FolderOpen,
  file: FileText,
  search: Search,
  users: Users,
  chat: MessageSquare,
  settings: Settings,
}

export default function EmptyState({
  icon = 'inbox',
  title,
  description,
  action,
  className = '',
  children,
}: EmptyStateProps) {
  const IconComponent = ICONS[icon]

  return (
    <div className={`empty-state ${className}`}>
      <div className="empty-state-icon">
        <IconComponent size={32} strokeWidth={1.5} />
      </div>
      <h3 className="empty-state-title">{title}</h3>
      {description && <p className="empty-state-description">{description}</p>}
      {action && (
        <button className="empty-state-action" onClick={action.onClick}>
          {action.label}
        </button>
      )}
      {children && <div className="empty-state-content">{children}</div>}
    </div>
  )
}
