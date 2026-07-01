import { useState, type KeyboardEvent } from 'react'

interface Props {
  tickers: string[]
  onAdd: (ticker: string) => void
  onRemove: (ticker: string) => void
}

export default function TickerInputPanel({ tickers, onAdd, onRemove }: Props) {
  const [input, setInput] = useState('')

  const handleAdd = () => {
    const value = input.trim().toUpperCase()
    if (value && !tickers.includes(value)) {
      onAdd(value)
    }
    setInput('')
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') handleAdd()
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
      <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
        Stocks to Analyze
      </h2>

      <div className="flex gap-2 mb-4">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Enter ticker symbol (e.g. NVDA)"
          className="flex-1 border border-gray-300 rounded-lg px-4 py-2 text-sm font-mono uppercase focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          maxLength={10}
        />
        <button
          onClick={handleAdd}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          Add
        </button>
      </div>

      {tickers.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {tickers.map((ticker) => (
            <span
              key={ticker}
              className="inline-flex items-center gap-1 bg-blue-50 border border-blue-200 text-blue-800 text-sm font-mono font-semibold px-3 py-1 rounded-full"
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
      )}

      {tickers.length === 0 && (
        <p className="text-gray-400 text-sm">No tickers added yet. Type a symbol above and press Enter.</p>
      )}
    </div>
  )
}
