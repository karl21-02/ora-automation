import { useEffect, useState } from 'react'
import { listRuns } from '../api'

/**
 * Hook to track the count of running orchestrations.
 * Polls the API every 10 seconds when there are active runs.
 */
export function useRunningCount() {
  const [count, setCount] = useState(0)

  useEffect(() => {
    let mounted = true

    async function fetchCount() {
      try {
        const { items } = await listRuns()
        if (!mounted) return
        const running = items.filter(
          (run) => run.status === 'pending' || run.status === 'running'
        )
        setCount(running.length)
      } catch {
        // API unavailable — ignore
      }
    }

    fetchCount()
    const interval = setInterval(fetchCount, 10000)

    return () => {
      mounted = false
      clearInterval(interval)
    }
  }, [])

  return count
}
