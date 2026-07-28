import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { TrendingUp, TrendingDown, Minus, BarChart3, AlertCircle } from 'lucide-react'
import SearchInput from './ui/SearchInput'

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
  const [searchTerm, setSearchTerm] = useState('')
  const [signalFilter, setSignalFilter] = useState<'all' | 'buy' | 'hold' | 'sell'>('all')
  const [sortField, setSortField] = useState<'ticker' | 'signal' | 'date'>('date')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')

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

  const toggleSort = (field: 'ticker' | 'signal' | 'date') => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortField(field)
      setSortDir('desc')
    }
  }

  const filteredSignals = useMemo(() => {
    let signals = data.signals.filter((s) => {
      const matchesTicker = s.ticker.toLowerCase().includes(searchTerm.toLowerCase())
      const matchesSignal = signalFilter === 'all' || s.signal === signalFilter
      return matchesTicker && matchesSignal
    })
    signals.sort((a, b) => {
      let cmp = 0
      if (sortField === 'ticker') cmp = a.ticker.localeCompare(b.ticker)
      else if (sortField === 'signal') cmp = a.signal.localeCompare(b.signal)
      else cmp = new Date(a.signal_date).getTime() - new Date(b.signal_date).getTime()
      return sortDir === 'asc' ? cmp : -cmp
    })
    return signals
  }, [data.signals, searchTerm, signalFilter, sortField, sortDir])

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <div className="mb-8">
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">Signal History</h1>
        <p className="text-sm text-[var(--text-secondary)] mt-1">
          Track record of all analysis signals issued by the system.
        </p>
      </div>

      {/* Summary cards (clickable filters) */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <button
          onClick={() => setSignalFilter(signalFilter === 'all' ? 'all' : 'all')}
          className={`rounded-lg border bg-[var(--surface-elevated)] p-4 text-left transition-all cursor-pointer ${signalFilter === 'all' ? 'border-[var(--accent)] ring-1 ring-[var(--accent)]' : 'border-[var(--border)] hover:border-[var(--text-muted)]'}`}
          aria-pressed={signalFilter === 'all'}
          aria-label="Show all signals"
        >
          <p className="text-xs text-[var(--text-muted)] uppercase tracking-wider">Total Signals</p>
          <p className="text-2xl font-semibold font-mono text-[var(--text-primary)] mt-1">
            {data.summary.total}
          </p>
        </button>
        <button
          onClick={() => setSignalFilter(signalFilter === 'buy' ? 'all' : 'buy')}
          className={`rounded-lg border bg-[var(--surface-elevated)] p-4 text-left transition-all cursor-pointer ${signalFilter === 'buy' ? 'border-emerald-500 ring-1 ring-emerald-500' : 'border-[var(--border)] hover:border-emerald-500/50'}`}
          aria-pressed={signalFilter === 'buy'}
          aria-label="Filter by buy signals"
        >
          <p className="text-xs text-emerald-500 uppercase tracking-wider">Buy</p>
          <p className="text-2xl font-semibold font-mono text-emerald-500 mt-1">
            {data.summary.buy_count}
          </p>
        </button>
        <button
          onClick={() => setSignalFilter(signalFilter === 'hold' ? 'all' : 'hold')}
          className={`rounded-lg border bg-[var(--surface-elevated)] p-4 text-left transition-all cursor-pointer ${signalFilter === 'hold' ? 'border-amber-500 ring-1 ring-amber-500' : 'border-[var(--border)] hover:border-amber-500/50'}`}
          aria-pressed={signalFilter === 'hold'}
          aria-label="Filter by hold signals"
        >
          <p className="text-xs text-amber-500 uppercase tracking-wider">Hold</p>
          <p className="text-2xl font-semibold font-mono text-amber-500 mt-1">
            {data.summary.hold_count}
          </p>
        </button>
        <button
          onClick={() => setSignalFilter(signalFilter === 'sell' ? 'all' : 'sell')}
          className={`rounded-lg border bg-[var(--surface-elevated)] p-4 text-left transition-all cursor-pointer ${signalFilter === 'sell' ? 'border-red-500 ring-1 ring-red-500' : 'border-[var(--border)] hover:border-red-500/50'}`}
          aria-pressed={signalFilter === 'sell'}
          aria-label="Filter by sell signals"
        >
          <p className="text-xs text-red-500 uppercase tracking-wider">Sell</p>
          <p className="text-2xl font-semibold font-mono text-red-500 mt-1">
            {data.summary.sell_count}
          </p>
        </button>
      </div>

      {/* Search bar */}
      <div className="flex items-center gap-3 mb-4">
        <SearchInput
          value={searchTerm}
          onChange={setSearchTerm}
          placeholder="Search by ticker..."
          aria-label="Search signals by ticker"
          className="flex-1 max-w-xs"
        />
        {signalFilter !== 'all' && (
          <button
            onClick={() => setSignalFilter('all')}
            className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${signalColor(signalFilter)}`}
            aria-label="Clear signal filter"
          >
            {signalFilter.toUpperCase()} &times;
          </button>
        )}
        <span className="text-xs text-[var(--text-muted)]">
          {filteredSignals.length} signal{filteredSignals.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Signal table */}
      <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)]">
                <th className="text-left px-4 py-3 text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider cursor-pointer hover:text-[var(--text-secondary)] select-none" onClick={() => toggleSort('ticker')}>Ticker {sortField === 'ticker' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider cursor-pointer hover:text-[var(--text-secondary)] select-none" onClick={() => toggleSort('signal')}>Signal {sortField === 'signal' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Confidence</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Sentiment</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider cursor-pointer hover:text-[var(--text-secondary)] select-none" onClick={() => toggleSort('date')}>Date {sortField === 'date' && (sortDir === 'asc' ? '↑' : '↓')}</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Days</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredSignals.map((s, i) => (
                <tr key={i} className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--surface)]">
                  <td className="px-4 py-3 font-mono font-medium text-[var(--text-primary)]">{s.ticker}</td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => setSignalFilter(signalFilter === s.signal ? 'all' : s.signal)}
                      className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full cursor-pointer transition-opacity hover:opacity-80 ${signalColor(s.signal)}`}
                      aria-label={`Filter by ${s.signal} signals`}
                    >
                      {signalIcon(s.signal)}
                      {s.signal.toUpperCase()}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-[var(--text-secondary)] capitalize">{s.confidence}</td>
                  <td className="px-4 py-3 font-mono text-[var(--text-secondary)]">
                    {s.sentiment_score.toFixed(2)}
                  </td>
                  <td className="px-4 py-3 text-[var(--text-muted)]">
                    {new Date(s.signal_date).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-[var(--text-muted)]">{s.days_held}d</td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      to={`/analyze?tickers=${s.ticker}`}
                      className="text-xs text-[var(--accent)] hover:underline"
                    >
                      Re-run
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
