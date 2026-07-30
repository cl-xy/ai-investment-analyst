import { useCallback, useEffect, useRef, useState } from 'react'
import { BarChart3, Clock, CheckCircle2, Database, Zap, TrendingUp, AlertCircle, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'

import { API_BASE, authHeaders } from '../api/config'

interface EvalSummary {
  total_runs: number
  schema_validation_rate: number
  avg_latency_ms: number
  p95_latency_ms: number
  citation_coverage: number
  tool_success_rate: number
  cache_hit_rate: number
  last_run_at: string | null
}

export default function EvalPage() {
  const [summary, setSummary] = useState<EvalSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const fetchData = useCallback(() => {
    // Abort any in-flight request to prevent stale responses overwriting newer data
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError(null)
    fetch(`${API_BASE}/api/eval/summary`, {
      headers: authHeaders(),
      signal: controller.signal,
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to fetch eval summary (${res.status})`)
        if (res.status === 204) return null
        return res.json()
      })
      .then((data) => {
        if (!controller.signal.aborted) setSummary(data)
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        if (!controller.signal.aborted) setError(err.message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })
  }, [])

  useEffect(() => {
    fetchData()
    return () => { abortRef.current?.abort() }
  }, [fetchData])

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-12">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
              <div className="h-4 w-20 rounded animate-shimmer mb-3" />
              <div className="h-7 w-16 rounded animate-shimmer" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-12">
        <div className="max-w-md mx-auto rounded-xl border border-red-500/20 bg-red-500/5 p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-500 mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-red-500">Failed to load evaluation data</p>
              <p className="text-sm text-[var(--text-secondary)] mt-1">{error}</p>
              <div className="flex items-center gap-4 mt-4">
                <button
                  onClick={fetchData}
                  className="flex items-center gap-2 text-sm text-[var(--accent)] hover:underline focus-ring rounded"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  Retry
                </button>
                <Link to="/" className="text-sm text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors">
                  Go to Watchlist
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    )
  }

  if (!summary) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-12">
        <div className="max-w-md mx-auto rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-8 text-center">
          <BarChart3 className="w-8 h-8 text-[var(--text-muted)] mx-auto mb-3" />
          <p className="text-sm font-medium text-[var(--text-primary)]">No evaluation data yet</p>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            Run an analysis to generate quality metrics.
          </p>
          <Link
            to="/"
            className="inline-block mt-4 text-sm text-[var(--accent)] hover:underline focus-ring rounded"
          >
            Start an analysis
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">Evaluation Metrics</h1>
        <p className="text-sm text-[var(--text-muted)] mt-1">
          Automated quality metrics from the last 100 analysis runs.
          {summary.last_run_at && (() => {
            const d = new Date(summary.last_run_at)
            return !isNaN(d.getTime()) ? (
              <span className="ml-2">Last run: {d.toLocaleString()}</span>
            ) : null
          })()}
        </p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricTile
          icon={<CheckCircle2 className="w-4 h-4" />}
          label="Schema Validation"
          value={`${(summary.schema_validation_rate ?? 0).toFixed(1)}%`}
          status={(summary.schema_validation_rate ?? 0) >= 95 ? 'good' : (summary.schema_validation_rate ?? 0) >= 80 ? 'warn' : 'bad'}
        />
        <MetricTile
          icon={<Clock className="w-4 h-4" />}
          label="Avg Latency"
          value={`${((summary.avg_latency_ms ?? 0) / 1000).toFixed(1)}s`}
          subtitle={`p95: ${((summary.p95_latency_ms ?? 0) / 1000).toFixed(1)}s`}
          status={(summary.avg_latency_ms ?? 0) < 8000 ? 'good' : (summary.avg_latency_ms ?? 0) < 15000 ? 'warn' : 'bad'}
        />
        <MetricTile
          icon={<Zap className="w-4 h-4" />}
          label="Tool Success"
          value={`${(summary.tool_success_rate ?? 0).toFixed(1)}%`}
          status={(summary.tool_success_rate ?? 0) >= 90 ? 'good' : (summary.tool_success_rate ?? 0) >= 70 ? 'warn' : 'bad'}
        />
        <MetricTile
          icon={<Database className="w-4 h-4" />}
          label="Cache Hit Rate"
          value={`${(summary.cache_hit_rate ?? 0).toFixed(1)}%`}
          status={(summary.cache_hit_rate ?? 0) >= 60 ? 'good' : (summary.cache_hit_rate ?? 0) >= 30 ? 'warn' : 'bad'}
        />
        <MetricTile
          icon={<BarChart3 className="w-4 h-4" />}
          label="Total Runs"
          value={(summary.total_runs ?? 0).toString()}
          status="neutral"
        />
        <MetricTile
          icon={<TrendingUp className="w-4 h-4" />}
          label="Citation Coverage"
          value={`${(summary.citation_coverage ?? 0).toFixed(1)}`}
          subtitle="avg per analysis"
          status={(summary.citation_coverage ?? 0) >= 3 ? 'good' : 'warn'}
        />
      </div>

      {/* Disclaimer */}
      <div className="mt-8 pt-6 border-t border-[var(--border)]">
        <p className="text-xs text-[var(--text-muted)]">
          These metrics reflect system reliability and output quality, not prediction accuracy.
          Schema validation ensures structured outputs conform to the expected format.
          Citation coverage measures how well claims are grounded in retrieved data.
        </p>
      </div>
    </div>
  )
}

function MetricTile({
  icon,
  label,
  value,
  subtitle,
  status,
}: {
  icon: React.ReactNode
  label: string
  value: string
  subtitle?: string
  status: 'good' | 'warn' | 'bad' | 'neutral'
}) {
  const statusColors = {
    good: 'text-[var(--bullish)]',
    warn: 'text-[var(--neutral)]',
    bad: 'text-[var(--bearish)]',
    neutral: 'text-[var(--text-primary)]',
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
      <div className="flex items-center gap-2 text-[var(--text-muted)] mb-2">
        {icon}
        <span className="text-xs font-medium uppercase tracking-wider">{label}</span>
      </div>
      <p className={`text-2xl font-semibold font-mono ${statusColors[status]}`}>
        {value}
      </p>
      {subtitle && (
        <p className="text-xs text-[var(--text-muted)] mt-1">{subtitle}</p>
      )}
    </div>
  )
}
