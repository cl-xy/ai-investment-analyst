import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bell } from 'lucide-react'
import { getUnreadCount } from '../api/alertsService'

const POLL_INTERVAL_MS = 60_000

export function AlertsBadge() {
  const [unreadCount, setUnreadCount] = useState(0)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    let cancelled = false

    const poll = async () => {
      if (document.visibilityState !== 'visible') return
      try {
        const count = await getUnreadCount()
        if (!cancelled) setUnreadCount(count)
      } catch {
        // Best-effort; silently ignore transient failures so the badge
        // doesn't flicker error states into the header.
      }
    }

    poll()
    intervalRef.current = setInterval(poll, POLL_INTERVAL_MS)

    const handleVisibility = () => {
      if (document.visibilityState === 'visible') poll()
    }
    document.addEventListener('visibilitychange', handleVisibility)

    return () => {
      cancelled = true
      if (intervalRef.current) clearInterval(intervalRef.current)
      document.removeEventListener('visibilitychange', handleVisibility)
    }
  }, [])

  return (
    <Link
      to="/alerts"
      className="relative min-w-[44px] min-h-[44px] flex items-center justify-center rounded-lg hover:bg-[var(--surface-elevated)] transition-colors focus-ring"
      aria-label={unreadCount > 0 ? `Signal alerts, ${unreadCount} unread` : 'Signal alerts'}
    >
      <Bell className="w-[18px] h-[18px] text-[var(--text-secondary)]" aria-hidden="true" />
      {unreadCount > 0 && (
        <span
          className="absolute top-1.5 right-1.5 min-w-[16px] h-[16px] px-1 rounded-full text-[10px] font-semibold flex items-center justify-center leading-none"
          style={{ backgroundColor: 'var(--bearish)', color: 'white' }}
          aria-hidden="true"
        >
          {unreadCount > 9 ? '9+' : unreadCount}
        </span>
      )}
    </Link>
  )
}
