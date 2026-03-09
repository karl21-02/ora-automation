import { useState, useEffect, useCallback } from 'react'

const STORAGE_KEY = 'ora-sidebar-collapsed'

export function useSidebarState(defaultCollapsed = false) {
  const [isCollapsed, setIsCollapsed] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      return stored ? JSON.parse(stored) : defaultCollapsed
    } catch {
      return defaultCollapsed
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(isCollapsed))
    } catch {
      // localStorage not available
    }
  }, [isCollapsed])

  const toggle = useCallback(() => setIsCollapsed((c: boolean) => !c), [])

  return { isCollapsed, setIsCollapsed, toggle }
}
