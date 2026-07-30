import { useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { Link } from 'react-router-dom'
import { TrendingUp, Sparkles, AlertCircle } from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { getExploreStocks, getStockDetail } from '../api/exploreService'
import { formatPrice, formatVolume } from '../utils/formatters'
import type { ExploreResponse, StockDetail, TrendingStock } from '../types/analysis'

// Reads theme colors from CSS custom properties, re-renders on theme change
// Stable subscribe/snapshot refs avoid re-creating the observer per component instance.
const _subscribe = (cb: () => void) => {
  const observer = new MutationObserver(cb)
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  return () => observer.disconnect()
}
const _getSnapshot = () => document.documentElement.getAttribute('data-theme') ?? 'petroleum'
const _getServerSnapshot = () => 'petroleum'

function useThemeColors() {
  const theme = useSyncExternalStore(_subscribe, _getSnapshot, _getServerSnapshot)
  return useMemo(() => {
    const root = document.documentElement
    const get = (v: string) => getComputedStyle(root).getPropertyValue(v).trim() || undefined
    return {
      bullish: get('--bullish') ?? '#10b981',
      bearish: get('--bearish') ?? '#ef4444',
      textMuted: get('--text-muted') ?? '#9ca3af',
    }
  }, [theme])
}

function ChangeBadge({ changePct }: { changePct: number | null }) {
  if (changePct === null) return <span className="text-[var(--text-muted)] text-sm">-</span>
  const rounded = Math.round(changePct * 100) / 100
  const positive = rounded >= 0
  return (
    <span
      className={[
        'text-sm font-semibold tabular-nums',
        positive ? 'text-[var(--bullish)]' : 'text-[var(--bearish)]',
      ].join(' ')}
    >
      {positive ? '+' : ''}{rounded.toFixed(2)}%
    </span>
  )
}

function PriceChart({ history, changePct, ticker }: { history: StockDetail['price_history']; changePct: number | null; ticker: string }) {
  const { bullish, bearish, textMuted } = useThemeColors()
  const isPositive = changePct === null || changePct >= 0
  const color = isPositive ? bullish : bearish
  // #34: Unique gradient IDs to prevent collision across multiple charts
  const safeTicker = ticker.replace(/[^a-zA-Z0-9]/g, '_')
  const gradId = `grad-${safeTicker}-${isPositive ? 'up' : 'down'}`

  if (!history || history.length === 0) {
    return <div className="flex items-center justify-center h-32 text-[var(--text-muted)] text-sm">No price data available</div>
  }

  const minClose = Math.min(...history.map((p) => p.close))
  const maxClose = Math.max(...history.map((p) => p.close))
  const padding = (maxClose - minClose) * 0.1 || 1
  const domainMin = Math.max(0, minClose - padding)

  return (
    <ResponsiveContainer width="100%" height={140}>
      <AreaChart data={history} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.25} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: textMuted }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: string) => {
            const d = new Date(v + 'T00:00:00Z')
            return `${d.toLocaleString('default', { month: 'short', timeZone: 'UTC' })} ${d.getUTCDate()}`
          }}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={[domainMin, maxClose + padding]}
          tick={{ fontSize: 10, fill: textMuted }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: number) => `$${v.toFixed(0)}`}
          width={48}
        />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid var(--border)', backgroundColor: 'var(--surface-elevated)', color: 'var(--text-primary)' }}
          formatter={(v: unknown) => [`$${(v as number).toFixed(2)}`, 'Close']}
          labelFormatter={(label: unknown) => {
            const d = new Date(String(label) + 'T00:00:00Z')
            return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' })
          }}
        />
        <Area
          type="monotone"
          dataKey="close"
          stroke={color}
          strokeWidth={2}
          fill={`url(#${gradId})`}
          dot={false}
          activeDot={{ r: 4, fill: color }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

function DetailPanel({ ticker, changePct }: { ticker: string; changePct: number | null }) {
  const [detail, setDetail] = useState<StockDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getStockDetail(ticker)
      .then((d) => { if (!cancelled) { setDetail(d); setLoading(false) } })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load details')
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [ticker, retryCount])

  if (loading) {
    return (
      <div className="px-5 pb-5 pt-2 space-y-3">
        <div className="h-3 bg-[var(--surface)] rounded w-24 animate-shimmer" />
        <div className="h-3 bg-[var(--surface)] rounded w-full animate-shimmer" />
        <div className="h-3 bg-[var(--surface)] rounded w-5/6 animate-shimmer" />
        <div className="h-32 bg-[var(--surface)] rounded-xl mt-3 animate-shimmer" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="px-5 pb-4 pt-2">
        <div className="flex items-start gap-2 text-sm">
          <AlertCircle className="w-4 h-4 text-[var(--error)] mt-0.5 shrink-0" />
          <div>
            <p className="text-[var(--error)]">{error}</p>
            <button
              onClick={() => setRetryCount((c) => c + 1)}
              className="mt-1.5 text-xs text-[var(--accent)] hover:underline focus-ring rounded"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (!detail) return null

  return (
    <div className="px-5 pb-5 pt-1 bg-[var(--surface)] border-t border-[var(--border)] space-y-4">
      {/* Industry badge */}
      {detail.industry && (
        <span className="inline-block text-xs font-medium bg-[var(--accent-bg)] text-[var(--accent)] border border-[var(--accent)]/20 rounded-full px-3 py-0.5">
          {detail.industry}
        </span>
      )}

      {/* Description */}
      {detail.description && (
        <p className="text-sm text-[var(--text-secondary)] leading-relaxed line-clamp-4">
          {detail.description}
        </p>
      )}

      {/* Price chart */}
      <div>
        <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">30-Day Price</p>
        <div role="figure" aria-label={`30-day price chart for ${ticker}`}>
          <PriceChart history={detail.price_history ?? []} changePct={changePct} ticker={ticker} />
          {/* Accessible data summary for keyboard/screen-reader users */}
          {detail.price_history && detail.price_history.length > 0 && (
            <p className="sr-only">
              {ticker} 30-day price range: low ${Math.min(...detail.price_history.map(p => p.close)).toFixed(2)}, high ${Math.max(...detail.price_history.map(p => p.close)).toFixed(2)}, latest ${detail.price_history[detail.price_history.length - 1].close.toFixed(2)}.{changePct !== null ? ` Change: ${changePct >= 0 ? '+' : ''}${changePct.toFixed(2)}%.` : ''}
            </p>
          )}
        </div>
      </div>

      {/* Trending reason */}
      {(detail.trending_reason ?? []).length > 0 && (
        <div>
          <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">Why It's Trending</p>
          <ul className="space-y-1.5">
            {(detail.trending_reason ?? []).map((item, i) => (
              <li key={i} className="flex gap-2 text-sm text-[var(--text-secondary)]">
                <span className="text-[var(--accent)] shrink-0">•</span>
                {item.url && /^https?:\/\//i.test(item.url) ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:text-[var(--accent)] hover:underline transition-colors"
                  >
                    {item.title}
                  </a>
                ) : (
                  <span>{item.title}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <Link
        to={`/analyze?tickers=${encodeURIComponent(ticker)}`}
        className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-2 rounded-lg bg-[var(--accent-bg)] text-[var(--accent)] border border-[var(--accent)]/20 hover:bg-[var(--accent)]/20 transition-colors focus-ring mt-4"
      >
        <Sparkles className="w-3.5 h-3.5" />
        Analyze {ticker}
      </Link>
    </div>
  )
}

function StockRow({
  stock,
  expanded,
  onToggle,
}: {
  stock: TrendingStock
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <div>
      <div
        className="flex items-center gap-4 py-3.5 px-5 hover:bg-[var(--surface)] transition-colors cursor-pointer select-none"
        onClick={onToggle}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onToggle() } }}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-label={`${stock.ticker} ${stock.name}, ${stock.change_pct !== null ? `${stock.change_pct >= 0 ? '+' : ''}${stock.change_pct.toFixed(2)}%` : ''}`}
      >
        <span className="w-7 text-right text-sm text-[var(--text-muted)] font-mono shrink-0">
          {stock.rank}
        </span>
        <div className="flex-1 min-w-0">
          <span className="font-mono font-bold text-[var(--text-primary)] text-sm">{stock.ticker}</span>
          <span className="ml-2 text-sm text-[var(--text-muted)] truncate hidden sm:inline">{stock.name}</span>
        </div>
        <div className="flex items-center gap-6 shrink-0">
          <span className="text-sm font-semibold tabular-nums text-[var(--text-secondary)] w-20 text-right">
            {formatPrice(stock.price)}
          </span>
          <div className="w-20 text-right">
            <ChangeBadge changePct={stock.change_pct} />
          </div>
          <span className="text-xs text-[var(--text-muted)] tabular-nums w-16 text-right hidden md:block">
            {formatVolume(stock.volume)}
          </span>
          <span className={`text-[var(--text-muted)] transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}>
            ▾
          </span>
        </div>
      </div>
      {expanded && <DetailPanel ticker={stock.ticker} changePct={stock.change_pct} />}
    </div>
  )
}

function SkeletonRow({ rank }: { rank: number }) {
  return (
    <div className="flex items-center gap-4 py-3.5 px-5 skeleton-delayed">
      <span className="w-7 text-right text-sm text-[var(--text-muted)] font-mono shrink-0">{rank}</span>
      <div className="flex-1">
        <div className="h-4 bg-[var(--surface)] rounded w-24 animate-shimmer" />
      </div>
      <div className="flex items-center gap-6 shrink-0">
        <div className="h-4 bg-[var(--surface)] rounded w-20 animate-shimmer" />
        <div className="h-4 bg-[var(--surface)] rounded w-16 animate-shimmer" />
        <div className="h-4 bg-[var(--surface)] rounded w-14 hidden md:block animate-shimmer" />
      </div>
    </div>
  )
}

export default function ExplorePage() {
  const [data, setData] = useState<ExploreResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null)
  const [retryCount, setRetryCount] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getExploreStocks()
      .then((res) => { if (!cancelled) { setData(res); setLoading(false) } })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load trending stocks')
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [retryCount])

  const updatedAt = data?.updated_at
    ? new Date(data.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : null

  function handleToggle(ticker: string) {
    setExpandedTicker((prev) => (prev === ticker ? null : ticker))
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-[var(--text-primary)] tracking-tight flex items-center gap-2">
          <TrendingUp className="w-6 h-6 text-[var(--accent)]" />
          Trending Stocks
        </h2>
        <p className="text-[var(--text-muted)] text-sm mt-1">
          Most-watched US stocks on Yahoo Finance right now. Click a row to see details.
          {updatedAt && <span className="ml-2 text-[var(--text-muted)]">Updated {updatedAt}</span>}
        </p>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl px-5 py-4 text-red-500 text-sm">
          {error}
          <button
            onClick={() => setRetryCount((c) => c + 1)}
            className="ml-3 text-xs font-medium text-[var(--accent)] hover:underline focus-ring rounded"
          >
            Retry
          </button>
        </div>
      )}

      {!error && (
        <div className="bg-[var(--surface-elevated)] rounded-2xl border border-[var(--border)] shadow-sm overflow-hidden">
          {/* Header row */}
          <div className="flex items-center gap-4 py-2.5 px-5 bg-[var(--surface)] border-b border-[var(--border)]">
            <span className="w-7" />
            <span className="flex-1 text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide">Ticker</span>
            <div className="flex items-center gap-6 shrink-0">
              <span className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide w-20 text-right">Price</span>
              <span className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide w-20 text-right">Change</span>
              <span className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wide w-16 text-right hidden md:block">Volume</span>
              <span className="w-4" />
            </div>
          </div>

          {/* Rows */}
          <div className="divide-y divide-[var(--border)]">
            {loading
              ? Array.from({ length: 15 }, (_, i) => <SkeletonRow key={i} rank={i + 1} />)
              : (data?.stocks ?? []).length === 0
                ? (
                  <div className="py-12 text-center text-sm text-[var(--text-muted)]">
                    No trending stocks available right now. Check back later.
                  </div>
                )
                : (data?.stocks ?? []).map((stock) => (
                  <StockRow
                    key={stock.ticker}
                    stock={stock}
                    expanded={expandedTicker === stock.ticker}
                    onToggle={() => handleToggle(stock.ticker)}
                  />
                ))
            }
          </div>
        </div>
      )}
    </div>
  )
}
