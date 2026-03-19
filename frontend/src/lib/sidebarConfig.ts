import { MessageSquare, FileText, Building2, Calendar, Settings, FolderKanban, type LucideIcon } from 'lucide-react'

export interface MenuItem {
  id: string
  label: string
  icon: LucideIcon
  bottom?: boolean
}

export const MENU_ITEMS: MenuItem[] = [
  { id: 'chats', label: 'Chats', icon: MessageSquare },
  { id: 'reports', label: 'Reports', icon: FileText },
  { id: 'orgs', label: 'Orgs', icon: Building2 },
  { id: 'control', label: 'Control', icon: FolderKanban },
  { id: 'scheduler', label: 'Scheduler', icon: Calendar },
  { id: 'settings', label: 'Settings', icon: Settings, bottom: true },
]

export type MenuId = 'chats' | 'reports' | 'orgs' | 'control' | 'scheduler' | 'settings'

export const MAIN_MENU_ITEMS = MENU_ITEMS.filter(item => !item.bottom)
export const BOTTOM_MENU_ITEMS = MENU_ITEMS.filter(item => item.bottom)
