import { useState, useRef, useMemo, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Search, Sparkles, X, AlertCircle } from 'lucide-react'
import { useRecentTickers } from '../hooks/useRecentTickers'
import { useContextualHints } from '../hooks/useContextualHints'
import { getTickerError, normalizeTicker } from '../utils/tickerValidation'

interface Props {
  tickers: string[]
  onAdd: (ticker: string) => void
  onRemove: (ticker: string) => void
  onAnalyze: () => void
  loading: boolean
}

const DEMO_TICKERS = ['NVDA', 'AAPL', 'TSLA', 'MSFT', 'GOOGL', 'AMZN', 'META', 'SPY']

export default function WatchlistPage({ tickers, onAdd, onRemove, onAnalyze, loading }: Props) {
  const [input, setInput] = useState('')
  // #29: Inline validation error
  const [inputError, setInputError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  // #23: Frequency-weighted recents
  const { getSuggestions } = useRecentTickers()
  const recentSuggestions = getSuggestions(tickers)
  const suggestions = recentSuggestions.length > 0 ? recentSuggestions : DEMO_TICKERS

  // Contextual hints for first-time users
  const hintDefs = useMemo(() => [
    {
      id: 'watchlist-first-ticker',
      target: '[data-hint-target="ticker-input"]',
      message: 'Type a stock ticker like AAPL or NVDA to get started',
      condition: () => tickers.length === 0,
    },
  ], [tickers.length])
  const { activeHint, dismiss } = useContextualHints(hintDefs)

  const handleAdd = () => {
    const value = normalizeTicker(input)
    const error = getTickerError(input)
    if (error) {
      setInputError(error)
      return
    }
    if (value && !tickers.includes(value)) onAdd(value)
    setInput('')
    setInputError(null)
    // Dismiss onboarding hint on first add
    if (activeHint?.id === 'watchlist-first-ticker') dismiss('watchlist-first-ticker')
    // Return focus to input after adding
    inputRef.current?.focus()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleAdd()
    if (inputError) setInputError(null)
  }

  const handleDemoAnalyze = () => {
    navigate(`/analyze?tickers=NVDA`)
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-16 flex flex-col items-center gap-10">
      {/* Hero */}
      <div className="text-center space-y-3">
        <h2 className="text-2xl font-semibold text-[var(--text-primary)] tracking-tight">
          What stocks are you watching?
        </h2>
        <p className="text-[var(--text-secondary)] text-sm max-w-md">
          Add ticker symbols below and run a multi-agent analysis with real-time streaming trace.
        </p>
      </div>

      {/* Demo CTA */}
      <button
        onClick={handleDemoAnalyze}
        className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[var(--accent-bg)] text-[var(--accent)] text-sm font-medium hover:bg-[var(--accent)]/20 transition-colors focus-ring"
      >
        <Sparkles className="w-4 h-4" />
        Try a live analysis (NVDA)
      </button>

      {/* Search input */}
      <div className="w-full">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => { setInput(e.target.value); if (inputError) setInputError(null) }}
              onKeyDown={handleKeyDown}
              placeholder="Enter ticker symbol, e.g. NVDA"
              aria-label="Ticker symbol input"
              data-hint-target="ticker-input"
              aria-describedby={inputError ? 'ticker-error' : undefined}
              aria-invalid={!!inputError}
              className={`w-full border bg-[var(--surface)] rounded-lg pl-10 pr-4 py-3 text-sm font-mono uppercase text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)] focus:border-transparent transition-shadow ${
                inputError ? 'border-red-500/50' : 'border-[var(--border)]'
              }`}
              maxLength={10}
              autoFocus
            />
          </div>
          <button
            onClick={handleAdd}
            className="bg-[var(--accent)] hover:bg-[var(--accent)]/90 text-white px-4 py-3 rounded-lg text-sm font-medium transition-colors focus-ring flex items-center gap-1.5 min-h-[44px] active:scale-[0.98]"
          >
            <Plus className="w-4 h-4" />
            Add
          </button>
        </div>
        {/* #29: Inline validation error */}
        {inputError && (
          <p id="ticker-error" className="flex items-center gap-1.5 text-xs text-red-500 mt-2" role="alert">
            <AlertCircle className="w-3 h-3" />
            {inputError}
          </p>
        )}
        {/* Contextual hint for first-time users */}
        {activeHint && !inputError && (
          <div className="mt-2.5 flex items-start gap-2 animate-fade-in">
            <p className="text-xs text-[var(--text-muted)] leading-relaxed">
              💡 {activeHint.message}
            </p>
            <button
              onClick={() => dismiss(activeHint.id)}
              className="shrink-0 text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
              aria-label="Dismiss hint"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        )}
      </div>

      {/* Watchlist pills */}
      {tickers.length > 0 && (
        <div className="w-full">
          <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-3">
            Watchlist · {tickers.length} stock{tickers.length > 1 ? 's' : ''}
          </p>
          <div className="flex flex-wrap gap-2">
            {tickers.map((ticker) => (
              <span
                key={ticker}
                className="inline-flex items-center gap-1.5 bg-[var(--surface-elevated)] border border-[var(--border)] text-[var(--text-primary)] text-sm font-mono font-medium px-3 py-1.5 rounded-lg"
              >
                {ticker}
                <button
                  onClick={() => onRemove(ticker)}
                  className="text-[var(--text-muted)] hover:text-[var(--bearish)] transition-colors min-w-[28px] min-h-[28px] flex items-center justify-center rounded"
                  aria-label={`Remove ${ticker}`}
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Analyze button */}
      {tickers.length > 0 && (
        <button
          onClick={onAnalyze}
          disabled={loading}
          className="w-full bg-[var(--bullish)] hover:bg-[var(--bullish)]/90 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-3 rounded-lg transition-[colors,transform] duration-100 text-sm focus-ring active:scale-[0.97]"
        >
          Analyze {tickers.length} stock{tickers.length > 1 ? 's' : ''}
        </button>
      )}

      {/* Quick add suggestions - #23: frequency-weighted recents */}
      {tickers.length === 0 && (
        <div className="w-full">
          <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-3">
            {recentSuggestions.length > 0 ? 'Recent tickers' : 'Popular tickers'}
          </p>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((ticker) => (
              <button
                key={ticker}
                onClick={() => onAdd(ticker)}
                className="text-xs font-mono font-medium px-2.5 py-1.5 rounded-md bg-[var(--surface)] border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--accent)] transition-colors focus-ring min-h-[36px]"
              >
                {ticker}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
