import { useState, useEffect, useRef, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Search, Sparkles, X, AlertCircle } from 'lucide-react'
import { useRecentTickers } from '../hooks/useRecentTickers'
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
  // First-run welcome banner (read-only initializer for render purity)
  const [showWelcome, setShowWelcome] = useState(() => {
    try {
      return !(
        localStorage.getItem('invest-state:welcome-dismissed') ||
        localStorage.getItem('invest-welcome-dismissed')
      )
    } catch {
      return true
    }
  })

  // Migrate legacy localStorage key after commit (side effects belong in effects)
  useEffect(() => {
    try {
      const legacy = localStorage.getItem('invest-welcome-dismissed')
      if (legacy) {
        localStorage.setItem('invest-state:welcome-dismissed', legacy)
        localStorage.removeItem('invest-welcome-dismissed')
      }
    } catch { /* storage unavailable, ignore */ }
  }, [])

  const dismissWelcome = () => {
    try {
      localStorage.setItem('invest-state:welcome-dismissed', '1')
    } catch { /* quota exceeded, ignore */ }
    setShowWelcome(false)
  }
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  // #23: Frequency-weighted recents
  const { getSuggestions } = useRecentTickers()
  const recentSuggestions = getSuggestions(tickers)
  const suggestions = recentSuggestions.length > 0 ? recentSuggestions : DEMO_TICKERS

  const addTicker = (raw: string) => {
    const value = normalizeTicker(raw)
    if (!value || tickers.includes(value)) return false
    onAdd(value)
    return true
  }

  const handleAdd = () => {
    const error = getTickerError(input)
    if (error) {
      setInputError(error)
      return
    }
    addTicker(input)
    setInput('')
    setInputError(null)
    // Return focus to input after adding
    inputRef.current?.focus()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleAdd()
      return
    }
    // Clear error only on actual typing keys (not modifiers, arrows, etc.)
    if (inputError && e.key.length === 1) setInputError(null)
  }

  const handleDemoAnalyze = () => {
    navigate(`/analyze?tickers=NVDA`)
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-16 flex flex-col items-center gap-10">
      {/* First-run welcome banner */}
      {showWelcome && (
        <div className="w-full rounded-xl border border-[var(--accent)]/20 bg-[var(--accent-bg)] p-5 relative">
          <button
            type="button"
            onClick={dismissWelcome}
            className="absolute top-3 right-3 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors min-w-[28px] min-h-[28px] flex items-center justify-center"
            aria-label="Dismiss welcome message"
          >
            <X className="w-3.5 h-3.5" />
          </button>
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1.5">Welcome to Investment Analyst</h3>
          <p className="text-xs text-[var(--text-secondary)] leading-relaxed max-w-md">
            Add stock tickers to your watchlist, then click Analyze to run a multi-agent AI analysis with real-time streaming. Your results are saved in History.
          </p>
          <div className="flex items-center gap-4 mt-3 text-[10px] text-[var(--text-muted)]">
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)]" />Add tickers</span>
            <span>→</span>
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[var(--bullish)]" />Run analysis</span>
            <span>→</span>
            <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-[var(--live)]" />Review results</span>
          </div>
        </div>
      )}

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
        type="button"
        onClick={handleDemoAnalyze}
        className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[var(--accent-bg)] text-[var(--accent)] text-sm font-medium hover:bg-[var(--accent)]/20 hover:shadow-[0_0_12px_var(--accent-bg)] active:shadow-none active:scale-[0.97] transition-[color,background-color,transform,box-shadow] duration-150 focus-ring"
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
              data-hint-target="watchlist-input"
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
            type="button"
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
                  type="button"
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
          type="button"
          onClick={onAnalyze}
          disabled={loading}
          className="w-full bg-[var(--bullish)] hover:bg-[var(--bullish)]/90 hover:shadow-[0_0_16px_var(--bullish-bg)] active:shadow-none disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-3 rounded-lg transition-[color,background-color,transform,box-shadow] duration-150 text-sm focus-ring active:brightness-90"
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
                type="button"
                onClick={() => addTicker(ticker)}
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
