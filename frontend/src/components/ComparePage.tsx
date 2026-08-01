import { useMemo, useState, useRef, useCallback, useEffect, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Loader2, Plus, X, Scale } from 'lucide-react'

import { API_BASE, authHeaders } from '../api/config'
import { useCompareStore } from '../stores/compareStore'
import Markdown from './Markdown'

const POPULAR_TICKERS = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'SPY', 'QQQ', 'BRK.B']
const TICKER_PATTERN = /^[A-Z0-9][A-Z0-9.]{0,9}$/

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

interface RankedTicker {
  ticker: string
  rank: number
  reasoning: string
}

interface ComparisonNarrative {
  status: 'ok' | 'failed'
  error?: string | null
  summary?: string
  relative_ranking?: RankedTicker[]
  key_differentiators?: string[]
}

interface CompareResult {
  tickers: string[]
  analyses: Record<string, CompareAnalysis>
  comparison?: ComparisonNarrative | null
}

function CompareTableSkeleton() {
  const cols = 3
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] overflow-hidden skeleton-delayed">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--border)]">
            <th className="text-left px-5 py-3">
              <div className="h-3 w-16 rounded bg-[var(--surface)] animate-shimmer" />
            </th>
            {Array.from({ length: cols }).map((_, i) => (
              <th key={i} className="text-center px-5 py-3">
                <div className="h-3 w-12 rounded bg-[var(--surface)] animate-shimmer mx-auto" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--border)]">
          {Array.from({ length: 4 }).map((_, row) => (
            <tr key={row}>
              <td className="px-5 py-3">
                <div className="h-3 w-20 rounded bg-[var(--surface)] animate-shimmer" />
              </td>
              {Array.from({ length: cols }).map((_, col) => (
                <td key={col} className="text-center px-5 py-3">
                  <div className="h-3 w-10 rounded bg-[var(--surface)] animate-shimmer mx-auto" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function ComparePage() {
  const { tickers, setTicker, addSlot, removeSlot } = useCompareStore()
  const [result, setResult] = useState<CompareResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [focusedInput, setFocusedInput] = useState<number | null>(null)
  const [activeDescendant, setActiveDescendant] = useState(-1)
  const abortRef = useRef<AbortController | null>(null)

  // Abort in-flight request on unmount
  useEffect(() => {
    return () => { abortRef.current?.abort() }
  }, [])

  const updateTicker = useCallback((idx: number, value: string) => {
    setTicker(idx, value.toUpperCase())
  }, [setTicker])

  const suggestions = useMemo(() => {
    if (focusedInput === null) return []
    const ticker = tickers[focusedInput] || ''
    return POPULAR_TICKERS.filter((t) => t.startsWith(ticker.toUpperCase()) && t !== ticker.toUpperCase() && !tickers.includes(t)).slice(0, 5)
  }, [focusedInput, tickers])

  const handleComboboxKeyDown = useCallback((e: KeyboardEvent<HTMLInputElement>, idx: number) => {
    if (focusedInput !== idx || suggestions.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveDescendant((prev) => Math.min(prev + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveDescendant((prev) => Math.max(prev - 1, -1))
    } else if (e.key === 'Enter' && activeDescendant >= 0 && activeDescendant < suggestions.length) {
      e.preventDefault()
      updateTicker(idx, suggestions[activeDescendant])
      setFocusedInput(null)
      setActiveDescendant(-1)
    } else if (e.key === 'Escape') {
      setFocusedInput(null)
      setActiveDescendant(-1)
    }
  }, [focusedInput, suggestions, activeDescendant, updateTicker])

  const handleInputBlur = useCallback((e: React.FocusEvent<HTMLInputElement>) => {
    // Keep dropdown open if focus moves to an element inside the same combobox container
    const container = e.currentTarget.closest('[data-combobox]')
    if (container && container.contains(e.relatedTarget as Node)) return
    setFocusedInput(null)
    setActiveDescendant(-1)
  }, [])

  const handleCompare = async () => {
    const valid = [...new Set(tickers.map((t) => t.trim().toUpperCase()).filter((t) => t && TICKER_PATTERN.test(t)))]
    if (valid.length < 2) return

    // Abort any in-flight request
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller

    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await fetch(
        `${API_BASE}/api/compare?tickers=${encodeURIComponent(valid.join(','))}`,
        { headers: authHeaders(), signal: controller.signal }
      )
      if (!res.ok) {
        let message = 'Comparison failed'
        try {
          const data = await res.json()
          if (data.detail && typeof data.detail === 'string') message = data.detail
        } catch { /* non-JSON error body, use default message */ }
        throw new Error(message)
      }
      setResult(await res.json())
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      setError(err instanceof Error ? err.message : 'Comparison failed')
    } finally {
      if (!controller.signal.aborted) setLoading(false)
    }
  }

  const signalColor = (signal: string | undefined) => {
    switch (signal?.toLowerCase()) {
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
        {tickers.map((ticker, idx) => {
          const listboxId = `ticker-listbox-${idx}`
          const isOpen = focusedInput === idx && suggestions.length > 0
          return (
            <div key={idx} className="relative" data-combobox>
              <input
                type="text"
                value={ticker}
                onChange={(e) => { updateTicker(idx, e.target.value); setActiveDescendant(-1) }}
                onFocus={() => { setFocusedInput(idx); setActiveDescendant(-1) }}
                onBlur={handleInputBlur}
                onKeyDown={(e) => handleComboboxKeyDown(e, idx)}
                placeholder={`Ticker ${idx + 1}`}
                role="combobox"
                aria-label={`Ticker ${idx + 1}`}
                aria-expanded={isOpen}
                aria-controls={isOpen ? listboxId : undefined}
                aria-activedescendant={isOpen && activeDescendant >= 0 ? `${listboxId}-opt-${activeDescendant}` : undefined}
                aria-autocomplete="list"
                className="w-32 border border-[var(--border)] bg-[var(--surface)] rounded-lg px-3 py-2.5 text-sm font-mono uppercase text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)] transition-shadow focus-ring"
                maxLength={10}
              />
              {isOpen && (
                <div
                  id={listboxId}
                  role="listbox"
                  aria-label="Ticker suggestions"
                  className="absolute top-full left-0 mt-1 w-32 rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] shadow-lg py-1 z-50"
                >
                  {suggestions.map((s, i) => (
                    <div
                      key={s}
                      id={`${listboxId}-opt-${i}`}
                      role="option"
                      aria-selected={activeDescendant === i}
                      onMouseDown={(e) => { e.preventDefault(); updateTicker(idx, s); setFocusedInput(null); setActiveDescendant(-1) }}
                      className={`block w-full text-left px-3 py-1.5 text-xs font-mono text-[var(--text-primary)] cursor-pointer transition-colors ${activeDescendant === i ? 'bg-[var(--accent-bg)] text-[var(--accent)]' : 'hover:bg-[var(--surface)]'}`}
                    >
                      {s}
                    </div>
                  ))}
                </div>
              )}
              {tickers.length > 2 && (
                <button
                  onClick={() => removeSlot(idx)}
                  className="absolute -top-2 -right-2 min-w-[28px] min-h-[28px] rounded-full bg-[var(--surface-elevated)] border border-[var(--border)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--bearish)] transition-colors"
                  aria-label={`Remove ticker ${idx + 1}`}
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
          )
        })}

        {tickers.length < 3 && (
          <button
            onClick={addSlot}
            aria-label="Add ticker"
            className="w-10 h-10 rounded-lg border border-dashed border-[var(--border)] flex items-center justify-center text-[var(--text-muted)] hover:text-[var(--accent)] hover:border-[var(--accent)] transition-colors"
          >
            <Plus className="w-4 h-4" />
          </button>
        )}

        <button
          onClick={handleCompare}
          disabled={loading || [...new Set(tickers.map((t) => t.trim().toUpperCase()).filter((t) => t && TICKER_PATTERN.test(t)))].length < 2}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg bg-[var(--accent)] text-white text-sm font-medium hover:bg-[var(--accent)]/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors focus-ring"
        >
          {loading ? <><Loader2 className="w-4 h-4 animate-spin" /> Comparing...</> : 'Compare'}
          {!loading && <ArrowRight className="w-4 h-4" />}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div role="alert" className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 mb-6 text-sm text-red-500">
          {error}
        </div>
      )}

      {/* Skeleton loading state */}
      {loading && <CompareTableSkeleton />}

      {/* Results table */}
      {result && (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)]">
                <th scope="col" className="text-left px-5 py-3 text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
                  Metric
                </th>
                {result.tickers.map((t) => (
                  <th scope="col" key={t} className="text-center px-5 py-3 font-mono font-semibold text-[var(--text-primary)]">
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
                  const raw = result.analyses[t]?.sentiment_score
                  const score = typeof raw === 'number' && isFinite(raw) ? raw : 0
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

      {/* Comparative narrative */}
      {result?.comparison?.status === 'failed' && (
        <div className="mt-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 text-sm text-[var(--text-muted)]">
          Comparison narrative unavailable, but the metrics table above is still accurate.
        </div>
      )}

      {result?.comparison?.status === 'ok' && (
        <div className="mt-4 rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5 space-y-4">
          {result.comparison.summary && (
            <Markdown>{result.comparison.summary}</Markdown>
          )}

          {!!result.comparison.relative_ranking?.length && (
            <div>
              <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
                Relative Ranking
              </h3>
              <ol className="space-y-1.5">
                {[...result.comparison.relative_ranking]
                  .sort((a, b) => a.rank - b.rank)
                  .map((r) => (
                    <li key={r.ticker} className="text-sm text-[var(--text-primary)]">
                      <span className="font-mono font-semibold">{r.rank}. {r.ticker}</span>
                      {r.reasoning && (
                        <span className="text-[var(--text-muted)]">: {r.reasoning}</span>
                      )}
                    </li>
                  ))}
              </ol>
            </div>
          )}

          {!!result.comparison.key_differentiators?.length && (
            <div>
              <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
                Key Differentiators
              </h3>
              <ul className="list-disc list-inside space-y-1">
                {result.comparison.key_differentiators.map((d, i) => (
                  <li key={i} className="text-sm text-[var(--text-secondary)]">{d}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {result && (
        <div className="mt-4 flex flex-wrap gap-2">
          {result.tickers.map((t) => (
            <Link key={t} to={`/analyze?tickers=${encodeURIComponent(t)}`} className="text-xs px-3 py-1.5 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--accent)] hover:border-[var(--accent)] transition-colors focus-ring">
              Analyze {t}
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
