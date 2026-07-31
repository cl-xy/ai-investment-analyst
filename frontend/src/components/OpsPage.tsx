import { useEffect, useState, useCallback, useRef } from 'react'
import {
  Activity,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Zap,
  AlertTriangle,
  ToggleLeft,
  ToggleRight,
  Clock,
  Server,
  Database,
  Cpu,
  RefreshCw,
  Copy,
  Check,
} from 'lucide-react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import type {
  HealthStatus,
  SLOData,
  MetricsData,
  ChaosState,
  CircuitBreaker,
  RecentError,
  LatencyEntry,
} from '../api/opsService'
import { getHealth, getMetrics, getSLO, getChaosState, toggleChaosScenario } from '../api/opsService'

export default function OpsPage() {
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [slo, setSLO] = useState<SLOData | null>(null)
  const [metrics, setMetrics] = useState<MetricsData | null>(null)
  const [chaos, setChaos] = useState<ChaosState | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [confirmingChaos, setConfirmingChaos] = useState<string | null>(null)

  const fetchAll = useCallback(async () => {
    const [h, s, m, c] = await Promise.allSettled([
      getHealth(),
      getSLO(),
      getMetrics(),
      getChaosState(),
    ])
    if (h.status === 'fulfilled') setHealth(h.value)
    if (s.status === 'fulfilled') setSLO(s.value)
    if (m.status === 'fulfilled') setMetrics(m.value)
    if (c.status === 'fulfilled') setChaos(c.value)

    const failures = [h, s, m, c].filter((r) => r.status === 'rejected')
    if (failures.length > 0) {
      const reasons = failures.map((f) =>
        f.status === 'rejected' ? (f.reason instanceof Error ? f.reason.message : 'Unknown error') : ''
      )
      setError(`Partial failure: ${reasons.join(', ')}`)
    } else {
      setError(null)
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchAll()
    const interval = setInterval(fetchAll, 10000)
    return () => clearInterval(interval)
  }, [fetchAll])

  const toggleChaosScenarioHandler = async (scenarioId: string) => {
    if (!chaos) return
    const scenario = chaos.scenarios.find((s) => s.id === scenarioId)
    if (!scenario) return

    // Require confirmation to enable
    if (!scenario.enabled && confirmingChaos !== scenarioId) {
      setConfirmingChaos(scenarioId)
      return
    }
    setConfirmingChaos(null)

    const newEnabled = !scenario.enabled
    // Optimistic update
    setChaos((prev) => {
      if (!prev) return prev
      const updatedScenarios = prev.scenarios.map((s) =>
        s.id === scenarioId ? { ...s, enabled: newEnabled } : s
      )
      return {
        ...prev,
        scenarios: updatedScenarios,
        active: updatedScenarios.some((s) => s.enabled),
      }
    })
    try {
      await toggleChaosScenario(scenarioId, newEnabled)
      // Refetch to get authoritative state (separate try so toggle success isn't rolled back)
      try {
        const fresh = await getChaosState()
        setChaos(fresh)
      } catch {
        // Refetch failed but toggle succeeded; let next poll reconcile
      }
    } catch {
      // Rollback only the toggled scenario using functional update
      setChaos((prev) => {
        if (!prev) return prev
        const rolledBack = prev.scenarios.map((s) =>
          s.id === scenarioId ? { ...s, enabled: !newEnabled } : s
        )
        return {
          ...prev,
          scenarios: rolledBack,
          active: rolledBack.some((s) => s.enabled),
        }
      })
    }
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
        <div className="flex items-center gap-3 mb-8">
          <Activity className="w-5 h-5 text-[var(--accent)] animate-pulse" />
          <span className="text-sm text-[var(--text-muted)]">Loading ops data...</span>
        </div>
      </div>
    )
  }

  const chaosActive = chaos?.scenarios.some((s) => s.enabled) ?? false

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-[var(--text-primary)] flex items-center gap-2">
            <Activity className="w-5 h-5 text-[var(--accent)]" />
            Operations Dashboard
          </h1>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            Live system health, SLOs, and reliability controls
          </p>
        </div>
        <button
          onClick={fetchAll}
          className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors focus-ring rounded px-3 py-2 min-h-[36px]"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          Refresh
        </button>
      </div>

      {/* Chaos warning banner */}
      {chaosActive && (
        <div className="mb-6 rounded-xl border border-red-500/30 bg-red-500/5 px-5 py-4 flex items-center gap-3 animate-fade-in">
          <AlertTriangle className="w-5 h-5 text-red-500 shrink-0" />
          <div>
            <p className="text-sm font-medium text-red-500">Chaos mode active</p>
            <p className="text-xs text-[var(--text-muted)] mt-0.5">
              Failure injection is enabled. The system is demonstrating graceful degradation.
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="mb-6 rounded-xl border border-amber-500/20 bg-amber-500/5 px-5 py-3 text-sm text-amber-500">
          {error}
        </div>
      )}

      {/* Grid layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column: Health + SLOs */}
        <div className="space-y-6">
          {health && <HealthPanel health={health} />}
          {slo && <SLOPanel slo={slo} />}
        </div>

        {/* Middle column: Circuit breakers + Rate limits */}
        <div className="space-y-6">
          {metrics && <CircuitBreakerPanel breakers={metrics.circuit_breakers} />}
          {metrics && <RateLimitPanel limits={metrics.rate_limits} />}
        </div>

        {/* Right column: Chaos + Errors */}
        <div className="space-y-6">
          {chaos && (
            <ChaosPanel
              chaos={chaos}
              confirmingId={confirmingChaos}
              onToggle={toggleChaosScenarioHandler}
              onCancelConfirm={() => setConfirmingChaos(null)}
            />
          )}
          {metrics && <ErrorsPanel errors={metrics.recent_errors} />}
        </div>
      </div>

      {/* Request Latency Chart (full width) */}
      {metrics && (metrics.latency_history?.length ?? 0) > 0 && (
        <LatencyChart entries={metrics.latency_history} />
      )}
    </div>
  )
}

function HealthPanel({ health }: { health: HealthStatus }) {
  const statusColor = {
    healthy: 'text-emerald-500',
    degraded: 'text-amber-500',
    unhealthy: 'text-red-500',
  }
  const componentIcon = {
    api: Server,
    database: Database,
    llm_provider: Cpu,
    mcp_servers: Zap,
  }
  const componentColor = {
    up: 'bg-emerald-500',
    degraded: 'bg-amber-500',
    down: 'bg-red-500',
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
          System Health
        </h2>
        <span className={`text-xs font-medium capitalize ${statusColor[health.status]}`}>
          {health.status}
        </span>
      </div>
      <div className="space-y-3">
        {Object.entries(health.components).map(([key, comp]) => {
          const Icon = componentIcon[key as keyof typeof componentIcon] || Server
          return (
            <div key={key} className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Icon className="w-4 h-4 text-[var(--text-muted)]" />
                <span className="text-sm text-[var(--text-secondary)] capitalize">
                  {key.replace(/_/g, ' ')}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {comp.latency_ms != null && (
                  <span className="text-xs font-mono text-[var(--text-muted)]">
                    {comp.latency_ms}ms
                  </span>
                )}
                <span
                  className={`w-2 h-2 rounded-full ${componentColor[comp.status]}`}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function SLOPanel({ slo }: { slo: SLOData }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
      <h2 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-4">
        Service Level Objectives
      </h2>
      <div className="space-y-4">
        {/* Availability */}
        <SLOGauge
          label="Availability"
          current={slo.availability.current}
          target={slo.availability.target}
          format={(v) => `${(v * 100).toFixed(2)}%`}
          good={slo.availability.current >= slo.availability.target}
        />
        {/* P95 Latency */}
        <SLOGauge
          label="P95 Latency"
          current={slo.p95_latency.current_ms}
          target={slo.p95_latency.target_ms}
          format={(v) => `${(v / 1000).toFixed(1)}s`}
          good={slo.p95_latency.current_ms <= slo.p95_latency.target_ms}
          inverted
        />
        {/* Error Budget */}
        <div>
          <div className="flex items-center justify-between text-xs mb-1.5">
            <span className="text-[var(--text-muted)]">Error Budget ({slo.error_budget.window_days}d)</span>
            <span className={`font-mono ${slo.error_budget.remaining_pct > 20 ? 'text-emerald-500' : 'text-red-500'}`}>
              {slo.error_budget.remaining_pct.toFixed(1)}% remaining
            </span>
          </div>
          <div className="h-2 bg-[var(--surface)] rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-300"
              style={{
                width: `${slo.error_budget.burned_pct}%`,
                backgroundColor: slo.error_budget.remaining_pct > 20 ? 'var(--bullish)' : 'var(--bearish)',
              }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

function SLOGauge({
  label,
  current,
  target,
  format,
  good,
  inverted,
}: {
  label: string
  current: number
  target: number
  format: (v: number) => string
  good: boolean
  inverted?: boolean
}) {
  const pct = inverted
    ? (current > 0 ? Math.min(100, (target / current) * 100) : 0)
    : (target > 0 ? Math.min(100, (current / target) * 100) : 0)

  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1.5">
        <span className="text-[var(--text-muted)]">{label}</span>
        <div className="flex items-center gap-2">
          <span className={`font-mono ${good ? 'text-emerald-500' : 'text-red-500'}`}>
            {format(current)}
          </span>
          <span className="text-[var(--text-muted)]">/ {format(target)}</span>
        </div>
      </div>
      <div className="h-2 bg-[var(--surface)] rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${good ? 'bg-emerald-500' : 'bg-red-500'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function CircuitBreakerPanel({ breakers }: { breakers: CircuitBreaker[] }) {
  const stateConfig = {
    closed: { icon: ShieldCheck, color: 'text-emerald-500', bg: 'bg-emerald-500/10', label: 'Closed' },
    open: { icon: ShieldAlert, color: 'text-red-500', bg: 'bg-red-500/10', label: 'Open' },
    'half-open': { icon: Shield, color: 'text-amber-500', bg: 'bg-amber-500/10', label: 'Half-Open' },
    'half_open': { icon: Shield, color: 'text-amber-500', bg: 'bg-amber-500/10', label: 'Half-Open' },
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
      <h2 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-4">
        Circuit Breakers
      </h2>
      <div className="space-y-3">
        {breakers.map((cb) => {
          const cfg = stateConfig[cb.state]
          const Icon = cfg.icon
          return (
            <div key={cb.name} className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Icon className={`w-4 h-4 ${cfg.color}`} />
                <span className="text-sm text-[var(--text-secondary)]">{cb.name}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${cfg.bg} ${cfg.color}`}>
                  {cfg.label}
                </span>
                {cb.failure_count > 0 && (
                  <span className="text-xs font-mono text-[var(--text-muted)]">
                    {cb.failure_count} failures
                  </span>
                )}
              </div>
            </div>
          )
        })}
        {breakers.length === 0 && (
          <p className="text-xs text-[var(--text-muted)]">No circuit breakers configured</p>
        )}
      </div>
    </div>
  )
}

function RateLimitPanel({ limits }: { limits: MetricsData['rate_limits'] }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
      <h2 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-4">
        Rate Limits (OpenRouter)
      </h2>
      <div className="space-y-4">
        <RateLimitBar
          label="Per Minute"
          used={limits.openrouter.per_minute.used}
          limit={limits.openrouter.per_minute.limit}
        />
        <RateLimitBar
          label="Daily"
          used={limits.openrouter.daily.used}
          limit={limits.openrouter.daily.limit}
        />
      </div>
    </div>
  )
}

function RateLimitBar({ label, used, limit }: { label: string; used: number; limit: number }) {
  const pct = limit > 0 ? (used / limit) * 100 : 0
  const critical = pct > 80

  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1.5">
        <span className="text-[var(--text-muted)]">{label}</span>
        <span className={`font-mono ${critical ? 'text-red-500' : 'text-[var(--text-secondary)]'}`}>
          {used} / {limit}
        </span>
      </div>
      <div className="h-2 bg-[var(--surface)] rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${critical ? 'bg-red-500' : 'bg-[var(--accent)]'}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  )
}

function ChaosPanel({
  chaos,
  confirmingId,
  onToggle,
  onCancelConfirm,
}: {
  chaos: ChaosState
  confirmingId: string | null
  onToggle: (id: string) => void
  onCancelConfirm: () => void
}) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
          Chaos Mode
        </h2>
        <AlertTriangle className={`w-4 h-4 ${chaos.active ? 'text-red-500' : 'text-[var(--text-muted)]'}`} />
      </div>
      <p className="text-xs text-[var(--text-muted)] mb-4">
        Inject failures to demonstrate graceful degradation
      </p>
      <div className="space-y-3">
        {chaos.scenarios.map((scenario) => (
          <div key={scenario.id}>
            <div className="flex items-center justify-between">
              <div className="flex-1 min-w-0">
                <p className="text-sm text-[var(--text-secondary)]">{scenario.label}</p>
                <p className="text-xs text-[var(--text-muted)] truncate">{scenario.description}</p>
              </div>
              <button
                onClick={() => onToggle(scenario.id)}
                className="ml-3 shrink-0 focus-ring rounded"
                aria-label={`${scenario.enabled ? 'Disable' : 'Enable'} ${scenario.label}`}
              >
                {scenario.enabled ? (
                  <ToggleRight className="w-8 h-5 text-red-500" />
                ) : (
                  <ToggleLeft className="w-8 h-5 text-[var(--text-muted)]" />
                )}
              </button>
            </div>
            {confirmingId === scenario.id && (
              <div className="mt-2 ml-0 flex items-center gap-2 animate-fade-in">
                <span className="text-xs text-amber-500">Enable failure injection?</span>
                <button
                  onClick={() => onToggle(scenario.id)}
                  className="text-xs px-2 py-1 rounded bg-red-500/10 text-red-500 hover:bg-red-500/20 transition-colors focus-ring"
                >
                  Confirm
                </button>
                <button
                  onClick={onCancelConfirm}
                  className="text-xs px-2 py-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors focus-ring"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function LatencyChart({ entries }: { entries: LatencyEntry[] }) {
  const chartData = entries.slice(-20).map((e, index) => ({
    name: e.ticker,
    key: `${e.ticker}-${index}`,
    fetch_data: Math.round(e.stages.fetch_data_ms / 1000),
    debate: Math.round(e.stages.debate_ms / 1000),
    report: Math.round(e.stages.report_ms / 1000),
  }))

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
          Request Latency
        </h2>
        <span className="text-xs text-[var(--text-muted)]">
          Last {chartData.length} requests (seconds)
        </span>
      </div>
      <div role="img" aria-label={`Stacked bar chart showing request latency in seconds for the last ${chartData.length} requests, broken down by fetch data, debate, and report stages`}>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
            <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} unit="s" />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 8,
              }}
              labelStyle={{ color: 'var(--text-primary)' }}
              formatter={(value: unknown, name: unknown) => [
                `${value}s`,
                name === 'fetch_data' ? 'Fetch Data' : name === 'debate' ? 'Debate' : 'Report',
              ]}
            />
            <Legend
              wrapperStyle={{ fontSize: 11, color: 'var(--text-secondary)' }}
              formatter={(value: string) =>
                value === 'fetch_data' ? 'Fetch Data' : value === 'debate' ? 'Debate' : 'Report'
              }
            />
            <Bar dataKey="fetch_data" stackId="a" fill="var(--accent)" radius={[0, 0, 0, 0]} />
            <Bar dataKey="debate" stackId="a" fill="var(--live)" radius={[0, 0, 0, 0]} />
            <Bar dataKey="report" stackId="a" fill="var(--bullish)" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="sr-only">
        <table>
          <caption>Request Latency</caption>
          <thead>
            <tr>
              <th scope="col">Ticker</th>
              <th scope="col">Fetch Data (s)</th>
              <th scope="col">Debate (s)</th>
              <th scope="col">Report (s)</th>
            </tr>
          </thead>
          <tbody>
            {chartData.map((d) => (
              <tr key={d.key}>
                <td>{d.name}</td>
                <td>{d.fetch_data}</td>
                <td>{d.debate}</td>
                <td>{d.report}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ErrorsPanel({ errors }: { errors: RecentError[] }) {
  const [copiedId, setCopiedId] = useState<string | null>(null)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [])

  const copyCorrelationId = (id: string) => {
    if (!navigator.clipboard) return
    navigator.clipboard.writeText(id).then(() => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      setCopiedId(id)
      timeoutRef.current = setTimeout(() => setCopiedId(null), 2000)
    }).catch(() => {
      // Clipboard write failed (permissions, non-HTTPS, etc.)
    })
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
      <h2 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-4">
        Recent Errors
      </h2>
      {errors.length === 0 ? (
        <p className="text-xs text-[var(--text-muted)]">No recent errors</p>
      ) : (
        <div className="space-y-3 max-h-64 overflow-y-auto">
          {errors.slice(0, 10).map((err) => (
            <div key={err.id} className="text-xs border-b border-[var(--border)] pb-2 last:border-0">
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-1.5">
                  <Clock className="w-3 h-3 text-[var(--text-muted)]" />
                  <span className="text-[var(--text-muted)]">
                    {new Date(err.timestamp).toLocaleTimeString()}
                  </span>
                  <span className="px-1.5 py-0.5 rounded bg-red-500/10 text-red-500 font-medium">
                    {err.stage}
                  </span>
                </div>
                <button
                  onClick={() => copyCorrelationId(err.correlation_id)}
                  className="flex items-center gap-1 text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors focus-ring rounded p-0.5"
                  title="Copy correlation ID"
                >
                  {copiedId === err.correlation_id ? (
                    <Check className="w-3 h-3 text-emerald-500" />
                  ) : (
                    <Copy className="w-3 h-3" />
                  )}
                  <span className="font-mono">{err.correlation_id.slice(0, 8)}</span>
                </button>
              </div>
              <p className="text-[var(--text-secondary)] truncate">{err.message}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
