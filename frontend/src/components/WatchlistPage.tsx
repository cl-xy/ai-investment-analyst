import { useState, type KeyboardEvent } from 'react'

interface Props {
  tickers: string[]
  onAdd: (ticker: string) => void
  onRemove: (ticker: string) => void
  onAnalyze: () => void
  loading: boolean
}

export default function WatchlistPage({ tickers, onAdd, onRemove, onAnalyze, loading }: Props) {
  const [input, setInput] = useState('')

  const handleAdd = () => {
    const value = input.trim().toUpperCase()
    if (value) onAdd(value)
    setInput('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleAdd()
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-16 flex flex-col items-center gap-10">
      {/* Hero heading */}
      <div className="text-center space-y-2">
        <h2 className="text-3xl font-bold text-gray-900 tracking-tight">
          What stocks are you watching?
        </h2>
        <p className="text-gray-500 text-base">
          Add ticker symbols below, then run an AI-powered analysis.
        </p>
      </div>

      {/* Search bar */}
      <div className="w-full">
        <div className="flex gap-2 shadow-sm">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Enter ticker symbol, e.g. NVDA"
            className="flex-1 border border-gray-300 rounded-xl px-5 py-3.5 text-base font-mono uppercase focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            maxLength={10}
            autoFocus
          />
          <button
            onClick={handleAdd}
            className="bg-blue-600 hover:bg-blue-700 text-white px-5 py-3.5 rounded-xl text-sm font-semibold transition-colors whitespace-nowrap"
          >
            Add
          </button>
        </div>
      </div>

      {/* Watchlist pills */}
      {tickers.length > 0 && (
        <div className="w-full">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
            Watchlist · {tickers.length} stock{tickers.length > 1 ? 's' : ''}
          </p>
          <div className="flex flex-wrap gap-2">
            {tickers.map((ticker) => (
              <span
                key={ticker}
                className="inline-flex items-center gap-1 bg-blue-50 border border-blue-200 text-blue-800 text-sm font-mono font-semibold px-3 py-1.5 rounded-full"
              >
                {ticker}
                <button
                  onClick={() => onRemove(ticker)}
                  className="ml-1 text-blue-400 hover:text-blue-700 text-base leading-none"
                  aria-label={`Remove ${ticker}`}
                >
                  ×
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
          className="w-full bg-emerald-600 hover:bg-emerald-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3.5 rounded-xl transition-colors text-base"
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Analyzing… this may take up to a minute
            </span>
          ) : (
            '🔍 Analyze Stocks'
          )}
        </button>
      )}

      {tickers.length === 0 && (
        <p className="text-gray-400 text-sm">
          Type a symbol above and press <kbd className="bg-gray-100 border border-gray-300 rounded px-1.5 py-0.5 text-xs font-mono">Enter</kbd> or click Add.
        </p>
      )}
    </div>
  )
}
