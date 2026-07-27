import { useEffect, useState } from 'react'
import { TrendingUp, TrendingDown, Minus, BarChart3, AlertCircle } from 'lucide-react'

interface SignalRecord {
  ticker: string
  signal: 'buy' | 'hold' | 'sell'
  confidence: 'high' | 'medium' | 'low'
  sentiment_score: number
  signal_date: string
  days_held: number
  analysis_id: string
}

interface BacktestData {
  signals: SignalRecord[]
  summary: {
    total: number
    buy_count: number
    hold_count: number
    sell_count: number
  }
}

import { API_BASE, authHeaders } from '../api/config'

export default function BacktestPage() {
  const [data, setData] = useState<BacktestData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/backtest`, { headers: authHeaders() })
      .then((r) => {
        if (!r.ok) throw new Error('Failed to fetch backtest data')
        return r.json()
      })
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-12">
        <div className="space-y-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 rounded-lg animate-shimmer" />
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-12 text-center">
        <AlertCircle className="w-8 h-8 text-[var(--text-muted)] mx-auto mb-3" />
        <p className="text-[var(--text-secondary)]">{error}</p>
      </div>
    )
  }

  if (!data || data.signals.length === 0) {
    return (
      <div className="max-w-5xl mx-auto px-6 py-12 text-center">
        <BarChart3 className="w-8 h-8 text-[var(--text-muted)] mx-auto mb-3" />
        <p className="text-[var(--text-secondary)]">No historical signals yet.</p>
        <p className="text-sm text-[var(--text-muted)] mt-1">
          Run some analyses to build signal history.
        </p>
      </div>
    )
  }

  const signalIcon = (signal: string) => {
    if (signal === 'buy') return <TrendingUp className="w-4 h-4 text-emerald-500" />
    if (signal === 'sell') return <TrendingDown className="w-4 h-4 text-red-500" />
    return <Minus className="w-4 h-4 text-amber-500" />
  }

  const signalColor = (signal: string) => {
    if (signal === 'buy') return 'text-emerald-500 bg-emerald-500/10'
    if (signal === 'sell') return 'text-red-500 bg-red-500/10'
    return 'text-amber-500 bg-amber-500/10'
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">Signal History</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">
          Track record of all analysis signals issued by the system.
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] p-4">
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">Total Signals</p>
          <p className="text-2xl font-semibold font-mono text-[var(--text-primary)] mt-1">
            {data.summary.total}
          </p>
        </div>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] p-4">
          <p className="text-xs text-emerald-500 uppercase tracking-wider">Buy</p>
          <p className="text-2xl font-semibold font-mono text-emerald-500 mt-1">
            {data.summary.buy_count}
          </p>
        </div>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] p-4">
          <p className="text-xs text-amber-500 uppercase tracking-wider">Hold</p>
          <p className="text-2xl font-semibold font-mono text-amber-500 mt-1">
            {data.summary.hold_count}
          </p>
        </div>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] p-4">
          <p className="text-xs text-red-500 uppercase tracking-wider">Sell</p>
          <p className="text-2xl font-semibold font-mono text-red-500 mt-1">
            {data.summary.sell_count}
          </p>
        </div>
      </div>

      {/* Signal table */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)]">
                <th className="text-left px-4 py-3 text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Ticker</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Signal</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Confidence</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Sentiment</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Date</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Days</th>
              </tr>
            </thead>
            <tbody>
              {data.signals.map((s, i) => (
                <tr key={i} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface)]">
                  <td className="px-4 py-3 font-mono font-medium text-[var(--text-primary)]">{s.ticker}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full ${signalColor(s.signal)}`}>
                      {signalIcon(s.signal)}
                      {s.signal.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-[var(--text-secondary)] capitalize">{s.confidence}</td>
                  <td className="px-4 py-3 font-mono text-[var(--text-secondary)]">
                    {s.sentiment_score.toFixed(2)}
                  </td>
                  <td className="px-4 py-3 text-[var(--text-muted)]">
                    {new Date(s.signal_date).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-[var(--text-muted)]">{s.days_held}d</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
