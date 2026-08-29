import { useCallback, useEffect, useRef, useState } from 'react'
import { BarChart3, Clock, CheckCircle2, Database, Zap, TrendingUp, AlertCircle, RefreshCw, GitBranch, ShieldCheck, ShieldAlert, ShieldQuestion } from 'lucide-react'
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

interface FunnelData {
  resolved_predictions: number
  classified_cases: number
  promoted_cases: number
  replay_ready_cases: number
  promotion_reasons: { reason: string; count: number }[]
}

interface EvaluationRunSummary {
  id: string
  candidate_config: string
  case_count: number
  status: string
  decision: string | null
  started_at: string | null
  completed_at: string | null
}

export default function EvalPage() {
  const [summary, setSummary] = useState<EvalSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  // Production Learning Loop section has its own independent fetch/loading/
  // error state, so a flywheel-specific failure never blocks the existing
  // eval metrics above it from rendering.
  const [funnel, setFunnel] = useState<FunnelData | null>(null)
  const [latestRun, setLatestRun] = useState<EvaluationRunSummary | null>(null)
  const [flywheelLoading, setFlywheelLoading] = useState(true)
  const [flywheelError, setFlywheelError] = useState<string | null>(null)
  const flywheelAbortRef = useRef<AbortController | null>(null)

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

  const fetchFlywheelData = useCallback(() => {
    flywheelAbortRef.current?.abort()
    const controller = new AbortController()
    flywheelAbortRef.current = controller

    setFlywheelLoading(true)
    setFlywheelError(null)

    Promise.all([
      fetch(`${API_BASE}/api/eval-flywheel/funnel`, {
        headers: authHeaders(),
        signal: controller.signal,
      }),
      fetch(`${API_BASE}/api/eval-flywheel/runs?limit=1`, {
        headers: authHeaders(),
        signal: controller.signal,
      }),
    ])
      .then(async ([funnelRes, runsRes]) => {
        if (!funnelRes.ok) throw new Error(`Failed to fetch funnel (${funnelRes.status})`)
        if (!runsRes.ok) throw new Error(`Failed to fetch runs (${runsRes.status})`)
        const funnelData = await funnelRes.json()
        const runsData = await runsRes.json()
        if (!controller.signal.aborted) {
          setFunnel(funnelData)
          setLatestRun(runsData.runs?.[0] ?? null)
        }
      })
      .catch((err) => {
        if (err.name === 'AbortError') return
        if (!controller.signal.aborted) setFlywheelError(err.message)
      })
      .finally(() => {
        if (!controller.signal.aborted) setFlywheelLoading(false)
      })
  }, [])

  useEffect(() => {
    fetchData()
    return () => { abortRef.current?.abort() }
  }, [fetchData])

  useEffect(() => {
    fetchFlywheelData()
    return () => { flywheelAbortRef.current?.abort() }
  }, [fetchFlywheelData])

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

      {/* Production Learning Loop: Outcome-Grounded Evaluation Flywheel */}
      <FlywheelSection
        funnel={funnel}
        latestRun={latestRun}
        loading={flywheelLoading}
        error={flywheelError}
        onRetry={fetchFlywheelData}
      />

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

function FlywheelSection({
  funnel,
  latestRun,
  loading,
  error,
  onRetry,
}: {
  funnel: FunnelData | null
  latestRun: EvaluationRunSummary | null
  loading: boolean
  error: string | null
  onRetry: () => void
}) {
  return (
    <div className="mt-10 pt-8 border-t border-[var(--border)]">
      <div className="mb-5">
        <h2 className="text-lg font-semibold text-[var(--text-primary)] flex items-center gap-2">
          <GitBranch className="w-4 h-4 text-[var(--accent)]" />
          Production Learning Loop
        </h2>
        <p className="text-sm text-[var(--text-muted)] mt-1">
          Resolved prediction failures are deterministically classified into a governed
          evaluation corpus, then replayed against the debate reasoning core (bull/bear/
          moderator only — not the full pipeline) with zero live tool calls and no access
          to the resolved outcome.
        </p>
      </div>

      {loading && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
              <div className="h-4 w-20 rounded animate-shimmer mb-3" />
              <div className="h-7 w-16 rounded animate-shimmer" />
            </div>
          ))}
        </div>
      )}

      {!loading && error && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-6">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-500 mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-red-500">Failed to load learning loop data</p>
              <p className="text-sm text-[var(--text-secondary)] mt-1">{error}</p>
              <button
                onClick={onRetry}
                className="mt-3 flex items-center gap-2 text-sm text-[var(--accent)] hover:underline focus-ring rounded"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Retry
              </button>
            </div>
          </div>
        </div>
      )}

      {!loading && !error && (!funnel || funnel.resolved_predictions === 0) && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-8 text-center">
          <GitBranch className="w-8 h-8 text-[var(--text-muted)] mx-auto mb-3" />
          <p className="text-sm font-medium text-[var(--text-primary)]">No resolved predictions yet</p>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            The learning loop activates once predictions reach their resolution horizon.
          </p>
          <Link
            to="/calibration"
            className="inline-block mt-4 text-sm text-[var(--accent)] hover:underline focus-ring rounded"
          >
            View track record
          </Link>
        </div>
      )}

      {!loading && !error && funnel && funnel.resolved_predictions > 0 && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricTile
              icon={<CheckCircle2 className="w-4 h-4" />}
              label="Resolved Predictions"
              value={funnel.resolved_predictions.toString()}
              status="neutral"
            />
            <MetricTile
              icon={<GitBranch className="w-4 h-4" />}
              label="Classified Cases"
              value={funnel.classified_cases.toString()}
              status="neutral"
            />
            <MetricTile
              icon={<TrendingUp className="w-4 h-4" />}
              label="Promoted Cases"
              value={funnel.promoted_cases.toString()}
              subtitle="material failures"
              status={funnel.promoted_cases > 0 ? 'warn' : 'good'}
            />
            <MetricTile
              icon={<Database className="w-4 h-4" />}
              label="Replay-Ready"
              value={funnel.replay_ready_cases.toString()}
              subtitle="capture complete"
              status={funnel.replay_ready_cases > 0 ? 'good' : 'neutral'}
            />
          </div>

          {funnel.promotion_reasons.length > 0 && (
            <div className="mt-5 rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
              <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-3">
                Promotion Reasons
              </h3>
              <ul className="space-y-2">
                {funnel.promotion_reasons.map((r) => (
                  <li key={r.reason} className="flex items-center justify-between text-sm">
                    <span className="text-[var(--text-secondary)] font-mono text-xs">{r.reason}</span>
                    <span className="text-[var(--text-primary)] font-medium">{r.count}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-5 rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
            <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-3">
              Latest Evaluation Run
            </h3>
            {!latestRun ? (
              <p className="text-sm text-[var(--text-muted)]">
                No evaluation run has been triggered yet.
              </p>
            ) : (
              <div className="flex items-center gap-4">
                <DecisionBadge decision={latestRun.decision} />
                <div className="text-sm text-[var(--text-secondary)]">
                  <span className="font-mono">{latestRun.candidate_config}</span>
                  {' · '}
                  {latestRun.case_count} case{latestRun.case_count === 1 ? '' : 's'}
                  {latestRun.completed_at && (
                    <span className="ml-2 text-[var(--text-muted)]">
                      {new Date(latestRun.completed_at).toLocaleString()}
                    </span>
                  )}
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

function DecisionBadge({ decision }: { decision: string | null }) {
  if (decision === 'pass') {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-500">
        <ShieldCheck className="w-3.5 h-3.5" />
        Pass
      </span>
    )
  }
  if (decision === 'reject') {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-red-500/10 text-red-500">
        <ShieldAlert className="w-3.5 h-3.5" />
        Reject
      </span>
    )
  }
  if (decision === 'investigate') {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-amber-500/10 text-amber-500">
        <ShieldQuestion className="w-3.5 h-3.5" />
        Investigate
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-[var(--text-muted)]/10 text-[var(--text-muted)]">
      <ShieldQuestion className="w-3.5 h-3.5" />
      Insufficient Data
    </span>
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
