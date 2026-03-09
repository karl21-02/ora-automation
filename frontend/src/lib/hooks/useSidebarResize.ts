import { useCallback, useEffect, useRef, useState } from 'react'

const STORAGE_KEY = 'ora-sidebar-width'
const MIN_WIDTH = 200
const MAX_WIDTH = 400
const DEFAULT_WIDTH = 260

/**
 * Hook to handle sidebar resize via drag.
 */
export function useSidebarResize() {
  const [width, setWidth] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    const parsed = stored ? parseInt(stored, 10) : DEFAULT_WIDTH
    return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, parsed))
  })

  const isDragging = useRef(false)
  const startX = useRef(0)
  const startWidth = useRef(width)

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    isDragging.current = true
    startX.current = e.clientX
    startWidth.current = width
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'
  }, [width])

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return
      const delta = e.clientX - startX.current
      const newWidth = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, startWidth.current + delta))
      setWidth(newWidth)
    }

    const handleMouseUp = () => {
      if (!isDragging.current) return
      isDragging.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      localStorage.setItem(STORAGE_KEY, String(width))
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', handleMouseUp)
    }
  }, [width])

  // Save on width change
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, String(width))
  }, [width])

  const resetWidth = useCallback(() => {
    setWidth(DEFAULT_WIDTH)
  }, [])

  return {
    width,
    handleMouseDown,
    resetWidth,
    minWidth: MIN_WIDTH,
    maxWidth: MAX_WIDTH,
  }
}
