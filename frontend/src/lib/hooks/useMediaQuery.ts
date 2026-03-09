import { useEffect, useState } from 'react'

/**
 * Hook to detect if a media query matches.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === 'undefined') return false
    return window.matchMedia(query).matches
  })

  useEffect(() => {
    const mediaQuery = window.matchMedia(query)
    const handler = (event: MediaQueryListEvent) => setMatches(event.matches)

    setMatches(mediaQuery.matches)
    mediaQuery.addEventListener('change', handler)

    return () => mediaQuery.removeEventListener('change', handler)
  }, [query])

  return matches
}

/**
 * Convenience hook for mobile detection (< 768px).
 */
export function useIsMobile(): boolean {
  return useMediaQuery('(max-width: 767px)')
}
