import { useState } from 'react'
import { ArrowRight, Plus, X, Scale } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_URL || ''

interface CompareAnalysis {
  ticker: string
  signal: string
  confidence: string
  sentiment_score: number
  news_summary?: string
  risk_flags: string[]
  price_data: Record<string, unknown>
  fundamentals: Record<string, unknown>
}

interface CompareResult {
  tickers: string[]
  analyses: Record<string, CompareAnalysis>
}

export default function ComparePage() {
  const [tickers, setTickers] = useState<string[]>(['', ''])
  const [result, setResult] = useState<CompareResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const updateTicker = (idx: number, value: string) => {
    const updated = [...tickers]
    updated[idx] = value.toUpperCase()
    setTickers(updated)
  }

  const addSlot = () => {
    if (tickers.length < 3) setTickers([...tickers, ''])
  }

  const removeSlot = (idx: number) => {
    if (tickers.length > 2) setTickers(tickers.filter((_, i) => i !== idx))
  }

  const handleCompare = async () => {
    const valid = tickers.filter((t) => t.trim())
    if (valid.length < 2) return

    setLoading(true)
    setError(null)
    try {
      const res = await fetch(
        `${API_BASE}/api/compare?tickers=${encodeURIComponent(valid.join(','))}`
      )
      if (!res.ok) {
        const data = await res.json()
        throw new Error(data.detail || 'Comparison failed')
      }
      setResult(await res.json())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Comparison failed')
    } finally {
      setLoading(false)
    }
  }

  const signalColor = (signal: string) => {
    switch (signal) {
      case 'buy': return 'text-[var(--bullish)]'
      case 'sell': return 'text-[var(--bearish)]'
      case 'hold': return 'text-[var(--neutral)]'
      default: return 'text-[var(--text-muted)]'
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-2">
          <Scale className="w-5 h-5 text-[var(--accent)]" />
          <h1 className="text-xl font-semibold text-[var(--text-primary)]">
            Compare Stocks
          </h1>
        </div>
        <p className="text-sm text-[var(--text-muted)]">
          Enter 2-3 tickers to see a side-by-side comparison of signals, sentiment, and risk.
        </p>
      </div>

      {/* Input row */}
      <div className="flex items-end gap-3 mb-8">
        {tickers.map((ticker, idx) => (
          <div key={idx} className="relative">
            <input
              type="text"
              value={ticker}
              onChange={(e) => updateTicker(idx, e.target.value)}
              placeholder={`Ticker ${idx + 1}`}
              className="w-28 border border-[var(--border)] bg-[var(--surface)] rounded-lg px-3 py-2.5 text-sm font-mono uppercase text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)] transition-shadow"
              maxLength={10}
            />
            {tickers.length > 2 && (
              <button
                onClick={() => removeSlot(idx)}
                className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-[var(--surface-elevated)] border border-[var(--border)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--bearish)] transition-colors"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        ))}

        {tickers.length < 3 && (
          <button
            onClick={addSlot}
            className="w-10 h-10 rounded-lg border border-dashed border-[var(--border)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--accent)] hover:border-[var(--accent)] transition-colors"
          >
            <Plus className="w-4 h-4" />
          </button>
        )}

        <button
          onClick={handleCompare}
          disabled={loading || tickers.filter((t) => t.trim()).length < 2}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[var(--accent)] text-white text-sm font-medium hover:bg-[var(--accent)]/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus-ring"
        >
          {loading ? 'Comparing...' : 'Compare'}
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 mb-6 text-sm text-red-500">
          {error}
        </div>
      )}

      {/* Results table */}
      {result && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)]">
                <th className="text-left px-5 py-3 text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
                  Metric
                </th>
                {result.tickers.map((t) => (
                  <th key={t} className="text-center px-5 py-3 font-mono font-semibold text-[var(--text-primary)]">
                    {t}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              <tr>
                <td className="px-5 py-3 text-[var(--text-secondary)]">Signal</td>
                {result.tickers.map((t) => (
                  <td key={t} className={`text-center px-5 py-3 font-medium capitalize ${signalColor(result.analyses[t]?.signal)}`}>
                    {result.analyses[t]?.signal || '-'}
                  </td>
                ))}
              </tr>
              <tr>
                <td className="px-5 py-3 text-[var(--text-secondary)]">Confidence</td>
                {result.tickers.map((t) => (
                  <td key={t} className="text-center px-5 py-3 text-[var(--text-primary)] capitalize">
                    {result.analyses[t]?.confidence || '-'}
                  </td>
                ))}
              </tr>
              <tr>
                <td className="px-5 py-3 text-[var(--text-secondary)]">Sentiment</td>
                {result.tickers.map((t) => {
                  const score = result.analyses[t]?.sentiment_score ?? 0
                  return (
                    <td key={t} className={`text-center px-5 py-3 font-mono ${score >= 0 ? 'text-[var(--bullish)]' : 'text-[var(--bearish)]'}`}>
                      {score.toFixed(2)}
                    </td>
                  )
                })}
              </tr>
              <tr>
                <td className="px-5 py-3 text-[var(--text-secondary)]">Risk Flags</td>
                {result.tickers.map((t) => (
                  <td key={t} className="text-center px-5 py-3 text-[var(--text-muted)]">
                    {result.analyses[t]?.risk_flags?.length || 0}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
