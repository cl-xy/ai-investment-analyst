import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Cell, LabelList } from 'recharts'
import { Target, TrendingUp, TrendingDown, Activity, AlertCircle, AlertTriangle, CheckCircle, XCircle, MinusCircle } from 'lucide-react'
import { API_BASE, authParam } from '../api/config'

interface CalibrationData {
  status: string
  horizon_days: number
  total_predictions: number
  resolved: number
  unresolved: number
  overall_accuracy: number
  brier_score: number | null
  calibration_by_confidence: Record<string, { count: number; hit_rate: number }>
  accuracy_by_signal: Record<string, { total: number; correct: number; accuracy: number }>
}

interface Prediction {
  id: string
  ticker: string
  signal: string
  confidence: string
  sentiment_score: number
  thesis: string
  price_at_prediction: number | null
  horizon_days: number
  created_at: string
  resolved_at: string | null
  outcome_price: number | null
  realized_return: number | null
  outcome: string | null
}

export default function CalibrationPage() {
  const [data, setData] = useState<CalibrationData | null>(null)
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'correct' | 'incorrect'>('all')

  async function fetchData() {
    setError(null)
    setLoading(true)
    try {
      const auth = authParam()
      const [calRes, predRes] = await Promise.all([
        fetch(`${API_BASE}/api/calibration?${auth}`),
        fetch(`${API_BASE}/api/calibration/predictions?limit=100&${auth}`),
      ])
      if (calRes.ok) setData(await calRes.json())
      if (predRes.ok) setPredictions(await predRes.json())
    } catch {
      setError('Unable to load calibration data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
  }, [])

  if (loading) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-12">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-64 rounded bg-[var(--surface-elevated)]" />
          <div className="grid grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-24 rounded-xl bg-[var(--surface-elevated)]" />
            ))}
          </div>
          <div className="h-64 rounded-xl bg-[var(--surface-elevated)]" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-12">
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-6 text-center">
          <AlertTriangle className="mx-auto h-8 w-8 text-red-400 mb-3" />
          <p className="text-sm text-[var(--text-secondary)]">{error}</p>
          <button
            onClick={() => fetchData()}
            className="mt-4 px-4 py-2 text-sm rounded-md bg-[var(--surface-elevated)] text-[var(--text-primary)] hover:bg-[var(--border)] focus-ring transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  const isEmpty = !data || data.status === 'insufficient_data' || data.total_predictions === 0

  if (isEmpty) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-16 text-center">
        <Target className="w-10 h-10 text-[var(--text-muted)] mx-auto mb-4" />
        <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-2">
          Track Record
        </h2>
        <p className="text-sm text-[var(--text-secondary)] max-w-md mx-auto">
          No predictions recorded yet. Run analyses to start building a track record.
          Each analysis creates a prediction that is scored against actual market outcomes
          after {data?.horizon_days || 30} days.
        </p>
      </div>
    )
  }

  // Prepare chart data
  const calibrationChartData = ['low', 'medium', 'high'].map((level) => {
    const bucket = data.calibration_by_confidence[level]
    return {
      name: level.charAt(0).toUpperCase() + level.slice(1),
      hit_rate: bucket ? Math.round(bucket.hit_rate * 100) : 0,
      count: bucket?.count || 0,
      // Expected hit rate for calibration reference
      expected: level === 'high' ? 80 : level === 'medium' ? 55 : 30,
    }
  })

  const signalChartData = Object.entries(data.accuracy_by_signal).map(([signal, stats]) => ({
    name: signal.charAt(0).toUpperCase() + signal.slice(1),
    accuracy: Math.round(stats.accuracy * 100),
    total: stats.total,
    correct: stats.correct,
    signal,
  }))

  const filteredPredictions = predictions.filter((p) => {
    if (filter === 'correct') return p.outcome === 'correct'
    if (filter === 'incorrect') return p.outcome === 'incorrect'
    return true
  })

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      {/* Hero */}
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[var(--text-primary)] mb-1">
          Track Record
        </h1>
        <p className="text-sm text-[var(--text-secondary)]">
          This system keeps score against reality. Every signal is a prediction, scored after {data.horizon_days} days.
        </p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <StatCard
          label="Overall Accuracy"
          value={`${Math.round(data.overall_accuracy * 100)}%`}
          icon={<Target className="w-4 h-4" />}
          color="var(--accent)"
        />
        <StatCard
          label="Brier Score"
          value={data.brier_score !== null ? data.brier_score.toFixed(3) : 'N/A'}
          subtitle="Lower is better"
          icon={<Activity className="w-4 h-4" />}
          color="var(--accent)"
        />
        <StatCard
          label="Resolved"
          value={`${data.resolved}`}
          subtitle={`of ${data.total_predictions} total`}
          icon={<CheckCircle className="w-4 h-4" />}
          color="var(--bullish)"
        />
        <StatCard
          label="Pending"
          value={`${data.unresolved}`}
          subtitle={`awaiting ${data.horizon_days}d horizon`}
          icon={<MinusCircle className="w-4 h-4" />}
          color="var(--text-muted)"
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        {/* Calibration Chart */}
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1">
            Calibration by Confidence
          </h3>
          <p className="text-xs text-[var(--text-muted)] mb-4">
            Does high confidence mean high accuracy?
          </p>
          <div role="img" aria-label="Bar chart showing hit rate by confidence level: low, medium, and high">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={calibrationChartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="name" tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} />
                <YAxis domain={[0, 100]} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} unit="%" />
                <Tooltip
                  contentStyle={{ backgroundColor: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                  labelStyle={{ color: 'var(--text-primary)' }}
                  formatter={(value, name) => [
                    `${value}%`,
                    name === 'hit_rate' ? 'Actual Hit Rate' : 'Expected',
                  ]}
                />
                <ReferenceLine y={50} stroke="var(--text-muted)" strokeDasharray="3 3" label={{ value: '50%', position: 'right', fill: 'var(--text-muted)', fontSize: 10 }} />
                <Bar dataKey="hit_rate" radius={[4, 4, 0, 0]} name="hit_rate">
                  {calibrationChartData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={entry.hit_rate >= entry.expected ? 'var(--bullish)' : 'var(--bearish)'}
                      fillOpacity={0.8}
                    />
                  ))}
                  <LabelList dataKey="hit_rate" position="top" formatter={(v) => `${v}%`} style={{ fill: 'var(--text-secondary)', fontSize: 10 }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="flex justify-center gap-4 mt-2 text-[10px] text-[var(--text-muted)]">
            {calibrationChartData.map((d) => (
              <span key={d.name}>{d.name}: {d.count} predictions</span>
            ))}
          </div>
          <div className="sr-only">
            <table>
              <caption>Calibration by Confidence</caption>
              <thead>
                <tr>
                  <th scope="col">Confidence Level</th>
                  <th scope="col">Hit Rate</th>
                  <th scope="col">Predictions</th>
                </tr>
              </thead>
              <tbody>
                {calibrationChartData.map((d) => (
                  <tr key={d.name}>
                    <td>{d.name}</td>
                    <td>{d.hit_rate}%</td>
                    <td>{d.count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Signal Accuracy Chart */}
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1">
            Accuracy by Signal
          </h3>
          <p className="text-xs text-[var(--text-muted)] mb-4">
            Which signals are most reliable?
          </p>
          <div role="img" aria-label="Horizontal bar chart showing prediction accuracy percentage for each signal type">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={signalChartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis type="number" domain={[0, 100]} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} unit="%" />
                <YAxis type="category" dataKey="name" tick={{ fill: 'var(--text-secondary)', fontSize: 12 }} width={50} />
                <Tooltip
                  contentStyle={{ backgroundColor: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}
                  formatter={(value) => [`${value}%`, 'Accuracy']}
                />
                <Bar dataKey="accuracy" radius={[0, 4, 4, 0]}>
                  {signalChartData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={entry.signal === 'buy' ? 'var(--bullish)' : entry.signal === 'sell' ? 'var(--bearish)' : 'var(--accent)'}
                      fillOpacity={0.8}
                    />
                  ))}
                  <LabelList dataKey="accuracy" position="right" formatter={(v) => `${v}%`} style={{ fill: 'var(--text-secondary)', fontSize: 10 }} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="sr-only">
            <table>
              <caption>Accuracy by Signal</caption>
              <thead>
                <tr>
                  <th scope="col">Signal</th>
                  <th scope="col">Accuracy</th>
                  <th scope="col">Correct</th>
                  <th scope="col">Total</th>
                </tr>
              </thead>
              <tbody>
                {signalChartData.map((d) => (
                  <tr key={d.name}>
                    <td>{d.name}</td>
                    <td>{d.accuracy}%</td>
                    <td>{d.correct}</td>
                    <td>{d.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Prediction Ledger */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">
            Prediction Ledger
          </h3>
          <div className="flex gap-1">
            {(['all', 'correct', 'incorrect'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`text-xs px-2.5 py-1 rounded-md transition-colors ${
                  filter === f
                    ? 'bg-[var(--accent)]/15 text-[var(--accent)] font-medium'
                    : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'
                }`}
              >
                {f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm" role="table">
            <thead>
              <tr className="border-b border-[var(--border)] text-[var(--text-muted)]">
                <th scope="col" className="px-4 py-2.5 text-left text-xs font-medium">Ticker</th>
                <th scope="col" className="px-4 py-2.5 text-left text-xs font-medium">Signal</th>
                <th scope="col" className="px-4 py-2.5 text-left text-xs font-medium">Confidence</th>
                <th scope="col" className="px-4 py-2.5 text-left text-xs font-medium">Entry Price</th>
                <th scope="col" className="px-4 py-2.5 text-left text-xs font-medium">Return</th>
                <th scope="col" className="px-4 py-2.5 text-left text-xs font-medium">Outcome</th>
                <th scope="col" className="px-4 py-2.5 text-left text-xs font-medium">Date</th>
              </tr>
            </thead>
            <tbody>
              {filteredPredictions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-sm text-[var(--text-muted)]">
                    No predictions match this filter.
                  </td>
                </tr>
              ) : (
                filteredPredictions.map((pred) => (
                  <PredictionRow key={pred.id} prediction={pred} />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function StatCard({
  label,
  value,
  subtitle,
  icon,
  color,
}: {
  label: string
  value: string
  subtitle?: string
  icon: React.ReactNode
  color: string
}) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-4">
      <div className="flex items-center gap-2 mb-2">
        <span style={{ color }}>{icon}</span>
        <span className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
          {label}
        </span>
      </div>
      <p className="text-2xl font-bold text-[var(--text-primary)]">{value}</p>
      {subtitle && (
        <p className="text-[10px] text-[var(--text-muted)] mt-0.5">{subtitle}</p>
      )}
    </div>
  )
}

function PredictionRow({ prediction }: { prediction: Prediction }) {
  const signalConfig = {
    buy: { icon: TrendingUp, color: 'var(--bullish)', label: 'Buy' },
    sell: { icon: TrendingDown, color: 'var(--bearish)', label: 'Sell' },
    hold: { icon: MinusCircle, color: 'var(--text-muted)', label: 'Hold' },
  }

  const outcomeConfig = {
    correct: { icon: CheckCircle, color: 'text-emerald-500', bg: 'bg-emerald-500/10', label: 'Correct' },
    incorrect: { icon: XCircle, color: 'text-red-500', bg: 'bg-red-500/10', label: 'Incorrect' },
    neutral: { icon: MinusCircle, color: 'text-amber-500', bg: 'bg-amber-500/10', label: 'Neutral' },
  }

  const signal = signalConfig[prediction.signal as keyof typeof signalConfig] || signalConfig.hold
  const outcome = prediction.outcome ? outcomeConfig[prediction.outcome as keyof typeof outcomeConfig] : null
  const SignalIcon = signal.icon
  const OutcomeIcon = outcome?.icon || AlertCircle

  const returnPct = prediction.realized_return !== null
    ? `${prediction.realized_return >= 0 ? '+' : ''}${(prediction.realized_return * 100).toFixed(1)}%`
    : null

  const date = prediction.created_at
    ? new Date(prediction.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    : ''

  return (
    <tr className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface)] transition-colors">
      <td className="px-4 py-3">
        <span className="font-mono font-medium text-[var(--text-primary)]">
          {prediction.ticker}
        </span>
      </td>
      <td className="px-4 py-3">
        <span className="flex items-center gap-1.5">
          <SignalIcon className="w-3.5 h-3.5" style={{ color: signal.color }} />
          <span className="text-xs font-medium" style={{ color: signal.color }}>
            {signal.label}
          </span>
        </span>
      </td>
      <td className="px-4 py-3">
        <span className="text-xs text-[var(--text-secondary)]">{prediction.confidence}</span>
      </td>
      <td className="px-4 py-3">
        <span className="text-xs font-mono text-[var(--text-secondary)]">
          {prediction.price_at_prediction !== null ? `$${prediction.price_at_prediction.toFixed(2)}` : '-'}
        </span>
      </td>
      <td className="px-4 py-3">
        {returnPct ? (
          <span className={`text-xs font-mono font-medium ${
            prediction.realized_return! >= 0 ? 'text-emerald-500' : 'text-red-500'
          }`}>
            {returnPct}
          </span>
        ) : (
          <span className="text-xs text-[var(--text-muted)]">Pending</span>
        )}
      </td>
      <td className="px-4 py-3">
        {outcome ? (
          <span className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full ${outcome.bg} ${outcome.color}`}>
            <OutcomeIcon className="w-3 h-3" />
            {outcome.label}
          </span>
        ) : (
          <span className="text-xs text-[var(--text-muted)] italic">Awaiting</span>
        )}
      </td>
      <td className="px-4 py-3">
        <span className="text-xs text-[var(--text-muted)]">{date}</span>
      </td>
    </tr>
  )
}
