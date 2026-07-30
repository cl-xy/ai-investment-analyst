import { Grid3x3, ArrowUpDown } from 'lucide-react'
import { useId } from 'react'
import { useRovingGrid } from '../hooks/useRovingGrid'

interface WatchlistGridProps {
  analyses: Array<{
    ticker: string
    signal: 'buy' | 'hold' | 'sell' | 'insufficient_data'
    confidence: string
    sentiment_score: number
    thesis?: string
    timestamp?: string
  }>
  onSelect?: (ticker: string) => void
}

const COLUMNS = ['Ticker', 'Signal', 'Confidence', 'Sentiment', 'Thesis'] as const
const COL_COUNT = COLUMNS.length

function getSignalStyle(signal: string): React.CSSProperties {
  switch (signal) {
    case 'buy':
      return { color: 'var(--bullish)', fontWeight: 600 }
    case 'sell':
      return { color: 'var(--bearish)', fontWeight: 600 }
    case 'hold':
      return { color: 'var(--neutral)', fontWeight: 600 }
    default:
      return { color: 'var(--text-muted)' }
  }
}

function formatSignal(signal: string): string {
  if (signal === 'insufficient_data') return 'N/A'
  return signal.charAt(0).toUpperCase() + signal.slice(1)
}

function truncateThesis(thesis: string | undefined, maxLen = 48): string {
  if (!thesis) return '—'
  if (thesis.length <= maxLen) return thesis
  return thesis.slice(0, maxLen).trimEnd() + '...'
}

export function WatchlistGrid({ analyses, onSelect }: WatchlistGridProps) {
  const hintId = useId()

  const { activeRow, activeCol, getGridProps, getCellProps } = useRovingGrid({
    rows: analyses.length,
    cols: COL_COUNT,
    onActivate: (row) => {
      const analysis = analyses[row]
      if (analysis && onSelect) {
        onSelect(analysis.ticker)
      }
    },
  })

  const gridProps = getGridProps()

  if (analyses.length === 0) {
    return (
      <div
        className="flex flex-col items-center justify-center gap-2 py-12"
        style={{ color: 'var(--text-muted)' }}
      >
        <Grid3x3 size={32} strokeWidth={1.5} />
        <p className="text-sm">No analyses to display</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <div
        {...gridProps}
        ref={gridProps.ref as unknown as React.Ref<HTMLDivElement>}
        aria-label="Watchlist analysis results"
        aria-describedby={hintId}
        className="w-full overflow-x-auto rounded-lg"
        style={{
          border: '1px solid var(--border)',
          background: 'var(--surface)',
        }}
      >
        {/* Header row (not navigable) */}
        <div
          role="row"
          aria-hidden="true"
          className="grid items-center gap-0 text-xs font-medium"
          style={{
            gridTemplateColumns: '80px 72px 96px 88px 1fr',
            borderBottom: '1px solid var(--border-subtle)',
            background: 'var(--surface-elevated)',
            color: 'var(--text-secondary)',
            padding: '8px 12px',
          }}
        >
          {COLUMNS.map((col) => (
            <div key={col} className="flex items-center gap-1 select-none">
              {col}
              {(col === 'Confidence' || col === 'Sentiment') && (
                <ArrowUpDown size={11} style={{ opacity: 0.5 }} />
              )}
            </div>
          ))}
        </div>

        {/* Data rows */}
        {analyses.map((analysis, rowIdx) => (
          <div
            key={analysis.ticker + (analysis.timestamp || rowIdx)}
            role="row"
            className="grid items-center gap-0 text-sm"
            style={{
              gridTemplateColumns: '80px 72px 96px 88px 1fr',
              borderBottom:
                rowIdx < analyses.length - 1 ? '1px solid var(--border-subtle)' : undefined,
            }}
          >
            {/* Ticker */}
            <div
              {...getCellProps(rowIdx, 0)}
              className="px-3 py-2 font-mono text-xs font-semibold outline-none"
              style={{
                color: 'var(--text-primary)',
                ...(activeRow === rowIdx && activeCol === 0
                  ? {
                      background: 'var(--accent-bg)',
                      boxShadow: 'inset 0 0 0 1.5px var(--ring)',
                      borderRadius: '4px',
                    }
                  : {}),
              }}
            >
              {analysis.ticker}
            </div>

            {/* Signal */}
            <div
              {...getCellProps(rowIdx, 1)}
              className="px-3 py-2 text-xs outline-none"
              style={{
                ...getSignalStyle(analysis.signal),
                ...(activeRow === rowIdx && activeCol === 1
                  ? {
                      background: 'var(--accent-bg)',
                      boxShadow: 'inset 0 0 0 1.5px var(--ring)',
                      borderRadius: '4px',
                    }
                  : {}),
              }}
            >
              {formatSignal(analysis.signal)}
            </div>

            {/* Confidence */}
            <div
              {...getCellProps(rowIdx, 2)}
              className="px-3 py-2 font-mono text-xs outline-none"
              style={{
                color: 'var(--text-primary)',
                ...(activeRow === rowIdx && activeCol === 2
                  ? {
                      background: 'var(--accent-bg)',
                      boxShadow: 'inset 0 0 0 1.5px var(--ring)',
                      borderRadius: '4px',
                    }
                  : {}),
              }}
            >
              {analysis.confidence}
            </div>

            {/* Sentiment */}
            <div
              {...getCellProps(rowIdx, 3)}
              className="px-3 py-2 font-mono text-xs outline-none"
              style={{
                color: 'var(--text-primary)',
                ...(activeRow === rowIdx && activeCol === 3
                  ? {
                      background: 'var(--accent-bg)',
                      boxShadow: 'inset 0 0 0 1.5px var(--ring)',
                      borderRadius: '4px',
                    }
                  : {}),
              }}
            >
              {analysis.sentiment_score.toFixed(2)}
            </div>

            {/* Thesis */}
            <div
              {...getCellProps(rowIdx, 4)}
              className="px-3 py-2 text-xs outline-none truncate"
              style={{
                color: 'var(--text-secondary)',
                ...(activeRow === rowIdx && activeCol === 4
                  ? {
                      background: 'var(--accent-bg)',
                      boxShadow: 'inset 0 0 0 1.5px var(--ring)',
                      borderRadius: '4px',
                    }
                  : {}),
              }}
              title={analysis.thesis || undefined}
            >
              {truncateThesis(analysis.thesis)}
            </div>
          </div>
        ))}
      </div>

      {/* Keyboard hint footer */}
      <p
        id={hintId}
        className="text-xs select-none"
        style={{ color: 'var(--text-muted)', paddingLeft: '4px' }}
      >
        Arrow keys to navigate, Enter to view analysis
      </p>
    </div>
  )
}
