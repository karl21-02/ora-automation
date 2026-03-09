import { useEffect, useCallback } from 'react'

interface ShortcutHandlers {
  onToggleSidebar?: () => void
  onNewChat?: () => void
  onFocusSearch?: () => void
  onNavigateMenu?: (index: number) => void
}

export function useKeyboardShortcuts(handlers: ShortcutHandlers) {
  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    const isMeta = event.metaKey || event.ctrlKey
    const target = event.target as HTMLElement
    const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable

    // Cmd/Ctrl + B: Toggle sidebar
    if (isMeta && event.key === 'b') {
      event.preventDefault()
      handlers.onToggleSidebar?.()
      return
    }

    // Cmd/Ctrl + K: Focus search
    if (isMeta && event.key === 'k') {
      event.preventDefault()
      handlers.onFocusSearch?.()
      return
    }

    // Cmd/Ctrl + N: New chat (only if not in input)
    if (isMeta && event.key === 'n' && !isInput) {
      event.preventDefault()
      handlers.onNewChat?.()
      return
    }

    // Number keys 1-5: Navigate menu (only if not in input)
    if (!isInput && event.key >= '1' && event.key <= '5') {
      const index = parseInt(event.key, 10) - 1
      handlers.onNavigateMenu?.(index)
      return
    }
  }, [handlers])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])
}
