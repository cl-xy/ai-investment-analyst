import { useEffect, useState, useCallback } from 'react'
import { Cloud, CloudOff, Check, AlertCircle, Loader2 } from 'lucide-react'
import { useSaveStatusStore } from '../stores/saveStatusStore'

function formatRelativeTime(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp) / 1000)
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ago`
}

export function SaveStatusChip() {
  const { status, lastSavedAt, error, setSaving } = useSaveStatusStore()
  const [relativeTime, setRelativeTime] = useState('')

  useEffect(() => {
    if (status !== 'saved' || !lastSavedAt) return

    const update = () => setRelativeTime(formatRelativeTime(lastSavedAt))
    update()

    const interval = setInterval(update, 10_000)
    return () => clearInterval(interval)
  }, [status, lastSavedAt])

  const handleRetry = useCallback(() => {
    setSaving()
  }, [setSaving])

  if (status === 'idle') return null

  return (
    <div
      role="status"
      aria-live="polite"
      aria-atomic="true"
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium transition-colors"
      style={{
        transitionDuration: 'var(--motion-standard)',
        background: 'var(--surface-elevated)',
        border: '1px solid var(--border)',
      }}
    >
      {status === 'saving' && (
        <>
          <Loader2
            size={14}
            className="animate-spin"
            style={{ color: 'var(--accent)' }}
            aria-hidden="true"
          />
          <span style={{ color: 'var(--text-secondary)' }}>Saving...</span>
        </>
      )}

      {status === 'saved' && (
        <>
          <Check
            size={14}
            style={{ color: 'var(--success)' }}
            aria-hidden="true"
          />
          <span style={{ color: 'var(--text-muted)' }}>
            Saved {relativeTime}
          </span>
        </>
      )}

      {status === 'offline' && (
        <>
          <CloudOff
            size={14}
            style={{ color: 'var(--warning)' }}
            aria-hidden="true"
          />
          <span style={{ color: 'var(--warning)' }}>Offline</span>
        </>
      )}

      {status === 'failed' && (
        <>
          <AlertCircle
            size={14}
            style={{ color: 'var(--error)' }}
            aria-hidden="true"
          />
          <span style={{ color: 'var(--error)' }}>Save failed</span>
          <button
            onClick={handleRetry}
            aria-label={`Retry save${error ? `: ${error}` : ''}`}
            className="ml-1 inline-flex items-center justify-center rounded-full transition-colors hover:opacity-80"
            style={{
              minWidth: '44px',
              minHeight: '44px',
              margin: '-12px -10px -12px 0',
              color: 'var(--error)',
              transitionDuration: 'var(--motion-micro)',
            }}
          >
            <Cloud size={14} aria-hidden="true" />
          </button>
        </>
      )}
    </div>
  )
}
