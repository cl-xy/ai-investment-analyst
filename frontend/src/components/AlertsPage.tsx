import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  Bell,
  BellOff,
  ChevronDown,
  ChevronUp,
  Info,
  Send,
} from 'lucide-react'
import {
  acknowledgeAlert,
  getAlerts,
  getTelegramStatus,
  type AlertItem,
  type AlertSeverity,
} from '../api/alertsService'
import { toastError } from '../stores/toastStore'
import EmptyState from './EmptyState'

const PAGE_SIZE = 20

const SEVERITY_CONFIG: Record<AlertSeverity, { icon: typeof Info; color: string; label: string }> = {
  critical: { icon: AlertTriangle, color: 'var(--bearish)', label: 'Critical' },
  warning: { icon: AlertTriangle, color: 'var(--neutral)', label: 'Warning' },
  info: { icon: Info, color: 'var(--text-muted)', label: 'Info' },
}

function SeverityBadge({ severity }: { severity: AlertSeverity }) {
  const config = SEVERITY_CONFIG[severity]
  const Icon = config.icon
  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded"
      style={{ color: config.color, backgroundColor: 'var(--surface)' }}
    >
      <Icon size={11} aria-hidden="true" />
      {config.label}
    </span>
  )
}

function SignalTransition({ oldSignal, newSignal }: { oldSignal: string | null; newSignal: string | null }) {
  if (!oldSignal) return null
  const changed = newSignal && newSignal !== oldSignal

  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-mono">
      <span className="text-[var(--text-muted)] uppercase">{oldSignal}</span>
      {changed && (
        <>
          <span className="text-[var(--text-muted)]">&rarr;</span>
          <span
            className="uppercase font-semibold"
            style={{
              color:
                newSignal === 'buy'
                  ? 'var(--bullish)'
                  : newSignal === 'sell'
                    ? 'var(--bearish)'
                    : 'var(--neutral)',
            }}
          >
            {newSignal}
          </span>
        </>
      )}
    </span>
  )
}

function AlertCard({
  alert,
  onAcknowledge,
}: {
  alert: AlertItem
  onAcknowledge: (id: string) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const navigate = useNavigate()
  const isUnread = alert.acknowledged_at === null
  const judgment = alert.reasoning_diff.llm_judgment
  const events = alert.reasoning_diff.triggered_events ?? []

  return (
    <div
      className="rounded-lg border p-4 transition-colors"
      style={{
        borderColor: isUnread ? 'var(--accent)' : 'var(--border)',
        backgroundColor: isUnread ? 'var(--accent-bg)' : 'var(--surface-elevated)',
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <button
              onClick={() => navigate(`/analyze?tickers=${alert.ticker}`)}
              className="font-mono text-sm font-semibold text-[var(--text-primary)] hover:underline focus-ring rounded"
            >
              {alert.ticker}
            </button>
            <SeverityBadge severity={alert.severity} />
            <SignalTransition oldSignal={alert.old_signal} newSignal={alert.new_signal} />
          </div>
          <p className="text-xs text-[var(--text-muted)]">
            Drift score {alert.drift_score.toFixed(2)} &middot;{' '}
            {new Date(alert.created_at).toLocaleString()}
            {alert.dispatched_telegram && (
              <span className="inline-flex items-center gap-1 ml-2">
                <Send size={10} aria-hidden="true" /> sent to Telegram
              </span>
            )}
          </p>
        </div>
        {isUnread && (
          <button
            onClick={() => onAcknowledge(alert.id)}
            className="text-xs font-medium text-[var(--accent)] hover:underline focus-ring rounded px-2 py-1 whitespace-nowrap"
          >
            Mark read
          </button>
        )}
      </div>

      {judgment?.reasoning && (
        <p className="text-sm text-[var(--text-secondary)] mt-3">{judgment.reasoning}</p>
      )}

      <button
        onClick={() => setExpanded((e) => !e)}
        className="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] mt-3 focus-ring rounded"
        aria-expanded={expanded}
      >
        {expanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        {expanded ? 'Hide details' : 'What changed'}
      </button>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-[var(--border-subtle)] space-y-2">
          {(judgment?.key_shifts ?? []).map((shift, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
              <span className="text-[var(--accent)] mt-0.5">&bull;</span>
              {shift}
            </div>
          ))}
          {events.map((event, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-[var(--text-secondary)]">
              <span className="text-[var(--text-muted)] mt-0.5">&bull;</span>
              {event.summary}
            </div>
          ))}
          {!judgment?.key_shifts?.length && !events.length && (
            <p className="text-xs text-[var(--text-muted)]">No specific events recorded.</p>
          )}
        </div>
      )}
    </div>
  )
}

export default function AlertsPage() {
  const [alerts, setAlerts] = useState<AlertItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAlerts = useCallback(async (newOffset: number, signal?: AbortSignal) => {
    setLoading(true)
    setError(null)
    try {
      const result = await getAlerts({ limit: PAGE_SIZE, offset: newOffset })
      if (signal?.aborted) return
      setAlerts((prev) => (newOffset === 0 ? result.alerts : [...prev, ...result.alerts]))
      setTotal(result.total)
      setOffset(newOffset)
    } catch {
      if (signal?.aborted) return
      setError('Unable to load alerts')
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    fetchAlerts(0, controller.signal)
    return () => controller.abort()
  }, [fetchAlerts])

  const handleAcknowledge = async (id: string) => {
    try {
      const updated = await acknowledgeAlert(id)
      setAlerts((prev) => prev.map((a) => (a.id === id ? updated : a)))
    } catch {
      toastError('Failed to acknowledge alert')
    }
  }

  const hasMore = alerts.length < total

  if (loading && alerts.length === 0) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-8">
        <div className="animate-pulse space-y-3">
          <div className="h-8 w-48 rounded bg-[var(--surface-elevated)]" />
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-24 rounded-lg bg-[var(--surface-elevated)]" />
          ))}
        </div>
      </div>
    )
  }

  if (error && alerts.length === 0) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-12">
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-6 text-center">
          <AlertTriangle className="mx-auto h-8 w-8 text-red-400 mb-3" />
          <p className="text-sm text-[var(--text-secondary)]">{error}</p>
          <button
            onClick={() => fetchAlerts(0)}
            className="mt-4 px-4 py-2 text-sm rounded-md bg-[var(--surface-elevated)] text-[var(--text-primary)] hover:bg-[var(--border)] focus-ring transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-[var(--text-primary)] mb-1">Signal Alerts</h1>
        <p className="text-sm text-[var(--text-secondary)]">
          Notified when a ticker's underlying investment thesis materially changes &mdash; not
          just when the price moves.
        </p>
      </div>

      <TelegramSubscriptionPanel />

      {alerts.length === 0 ? (
        <EmptyState
          icon={<Bell size={40} strokeWidth={1.5} />}
          title="No alerts yet"
          description="Monitored tickers are checked periodically for reasoning drift. Add tickers to your watchlist and enable monitoring to get started."
        />
      ) : (
        <div className="space-y-3 mt-6">
          {alerts.map((alert) => (
            <AlertCard key={alert.id} alert={alert} onAcknowledge={handleAcknowledge} />
          ))}
          {hasMore && (
            <div className="text-center pt-2">
              <button
                onClick={() => fetchAlerts(offset + PAGE_SIZE)}
                disabled={loading}
                className="text-sm font-medium text-[var(--accent)] hover:underline focus-ring rounded px-3 py-2 disabled:opacity-50"
              >
                {loading ? 'Loading...' : 'Load more'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function TelegramSubscriptionPanel() {
  const botUsername = import.meta.env.VITE_TELEGRAM_BOT_USERNAME || ''
  const botLink = botUsername ? `https://t.me/${botUsername}` : ''
  const [connected, setConnected] = useState<boolean | null>(null)

  const checkStatus = useCallback(async (signal?: AbortSignal) => {
    try {
      const status = await getTelegramStatus()
      if (signal?.aborted) return
      setConnected(status.connected)
    } catch {
      if (signal?.aborted) return
      setConnected(null)
    }
  }, [])

  useEffect(() => {
    if (!botLink) return
    const controller = new AbortController()
    checkStatus(controller.signal)

    // Poll while this panel is mounted so status flips to "connected" after
    // the user completes /start in Telegram and comes back to the tab —
    // there's no webhook->frontend push channel for this (no per-session
    // linkage to the chat_id), so short polling is the simplest fix.
    const interval = setInterval(() => checkStatus(), 5000)
    return () => {
      controller.abort()
      clearInterval(interval)
    }
  }, [botLink, checkStatus])

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] p-4 flex items-center gap-4 flex-wrap">
      <div className="flex items-center gap-2 flex-1 min-w-[200px]">
        <Send size={18} className="text-[var(--accent)]" aria-hidden="true" />
        <div>
          <p className="text-sm font-medium text-[var(--text-primary)]">Telegram alerts</p>
          <p className="text-xs text-[var(--text-muted)]">
            {connected
              ? 'Connected — alerts will be delivered to Telegram.'
              : 'Get notified in real time when a signal changes.'}
          </p>
        </div>
      </div>
      {botLink ? (
        connected ? (
          <span className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-md bg-[var(--bullish-bg)] text-[var(--bullish)]">
            <Bell size={14} aria-hidden="true" /> Connected
          </span>
        ) : (
          <a
            href={botLink}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-2 min-h-[44px] text-sm font-medium rounded-md bg-[var(--accent)] text-white hover:opacity-90 focus-ring transition-opacity"
          >
            Connect on Telegram
          </a>
        )
      ) : (
        <span className="text-xs text-[var(--text-muted)] inline-flex items-center gap-1">
          <BellOff size={13} aria-hidden="true" /> Telegram bot not configured
        </span>
      )}
    </div>
  )
}
