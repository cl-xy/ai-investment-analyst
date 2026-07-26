import { useState, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Search, Sparkles, X } from 'lucide-react'

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
  const navigate = useNavigate()

  const handleAdd = () => {
    const value = input.trim().toUpperCase()
    if (value && !tickers.includes(value)) onAdd(value)
    setInput('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleAdd()
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
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Enter ticker symbol, e.g. NVDA"
              className="w-full border border-[var(--border)] bg-[var(--surface)] rounded-lg pl-10 pr-4 py-3 text-sm font-mono uppercase text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)] focus:border-transparent transition-shadow"
              maxLength={10}
              autoFocus
            />
          </div>
          <button
            onClick={handleAdd}
            className="bg-[var(--accent)] hover:bg-[var(--accent)]/90 text-white px-4 py-3 rounded-lg text-sm font-medium transition-colors focus-ring flex items-center gap-1.5"
          >
            <Plus className="w-4 h-4" />
            Add
          </button>
        </div>
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
                  className="text-[var(--text-muted)] hover:text-[var(--bearish)] transition-colors"
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
          className="w-full bg-[var(--bullish)] hover:bg-[var(--bullish)]/90 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-3 rounded-lg transition-colors text-sm focus-ring"
        >
          Analyze {tickers.length} stock{tickers.length > 1 ? 's' : ''}
        </button>
      )}

      {/* Quick add suggestions */}
      {tickers.length === 0 && (
        <div className="w-full">
          <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-3">
            Popular tickers
          </p>
          <div className="flex flex-wrap gap-2">
            {DEMO_TICKERS.map((ticker) => (
              <button
                key={ticker}
                onClick={() => onAdd(ticker)}
                className="text-xs font-mono font-medium px-2.5 py-1.5 rounded-md bg-[var(--surface)] border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--accent)] transition-colors focus-ring"
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
