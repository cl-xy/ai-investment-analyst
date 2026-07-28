import { useState, useEffect, useRef } from 'react'
import { API_BASE } from '../api/config'

const HEALTH_INTERVAL = 30_000
const HEALTH_TIMEOUT = 5_000

/**
 * Online status with double-failure health check debouncing.
 * Pauses polling when tab is hidden to avoid wasted network I/O.
 */
export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(navigator.onLine)
  const failCountRef = useRef(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    const handleOnline = () => {
      failCountRef.current = 0
      setOnline(true)
    }
    const handleOffline = () => setOnline(false)

    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)

    const checkHealth = async () => {
      if (!navigator.onLine) return
      try {
        const controller = new AbortController()
        const timeout = setTimeout(() => controller.abort(), HEALTH_TIMEOUT)
        await fetch(`${API_BASE}/api/health`, {
          signal: controller.signal,
          cache: 'no-store',
        })
        clearTimeout(timeout)
        failCountRef.current = 0
        setOnline(true)
      } catch {
        failCountRef.current += 1
        if (failCountRef.current >= 2) setOnline(false)
      }
    }

    const startPolling = () => {
      if (!intervalRef.current) {
        intervalRef.current = setInterval(checkHealth, HEALTH_INTERVAL)
      }
    }

    const stopPolling = () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }

    const handleVisibility = () => {
      if (document.hidden) {
        stopPolling()
      } else {
        checkHealth() // immediate check on resume
        startPolling()
      }
    }

    document.addEventListener('visibilitychange', handleVisibility)
    if (!document.hidden) startPolling()

    return () => {
      stopPolling()
      document.removeEventListener('visibilitychange', handleVisibility)
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  return online
}
