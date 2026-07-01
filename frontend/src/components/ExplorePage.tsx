import { useEffect, useState } from 'react'
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
import type { ExploreResponse, StockDetail, TrendingStock } from '../types/analysis'

function formatPrice(price: number | null): string {
  if (price === null) return '—'
  return `$${price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatVolume(volume: number | null): string {
  if (volume === null) return '—'
  if (volume >= 1_000_000_000) return `${(volume / 1_000_000_000).toFixed(1)}B`
  if (volume >= 1_000_000) return `${(volume / 1_000_000).toFixed(1)}M`
  if (volume >= 1_000) return `${(volume / 1_000).toFixed(0)}K`
  return volume.toString()
}

function ChangeBadge({ changePct }: { changePct: number | null }) {
  if (changePct === null) return <span className="text-gray-400 text-sm">—</span>
  const positive = changePct >= 0
  return (
    <span
      className={[
        'text-sm font-semibold tabular-nums',
        positive ? 'text-emerald-600' : 'text-red-500',
      ].join(' ')}
    >
      {positive ? '+' : ''}{changePct.toFixed(2)}%
    </span>
  )
}

function PriceChart({ history, changePct }: { history: StockDetail['price_history']; changePct: number | null }) {
  const isPositive = changePct === null || changePct >= 0
  const color = isPositive ? '#10b981' : '#ef4444'

  if (history.length === 0) {
    return <div className="flex items-center justify-center h-32 text-gray-400 text-sm">No price data available</div>
  }

  const minClose = Math.min(...history.map((p) => p.close))
  const maxClose = Math.max(...history.map((p) => p.close))
  const padding = (maxClose - minClose) * 0.1 || 1

  return (
    <ResponsiveContainer width="100%" height={140}>
      <AreaChart data={history} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={`grad-${isPositive ? 'up' : 'down'}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.25} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10, fill: '#9ca3af' }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: string) => {
            const d = new Date(v + 'T00:00:00Z')
            return `${d.toLocaleString('default', { month: 'short', timeZone: 'UTC' })} ${d.getUTCDate()}`
          }}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={[minClose - padding, maxClose + padding]}
          tick={{ fontSize: 10, fill: '#9ca3af' }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: number) => `$${v.toFixed(0)}`}
          width={48}
        />
        <Tooltip
          contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
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
          fill={`url(#grad-${isPositive ? 'up' : 'down'})`}
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
  }, [ticker])

  if (loading) {
    return (
      <div className="px-5 pb-5 pt-2 animate-pulse space-y-3">
        <div className="h-3 bg-gray-200 rounded w-24" />
        <div className="h-3 bg-gray-200 rounded w-full" />
        <div className="h-3 bg-gray-200 rounded w-5/6" />
        <div className="h-32 bg-gray-100 rounded-xl mt-3" />
      </div>
    )
  }

  if (error) {
    return <div className="px-5 pb-4 pt-2 text-sm text-red-500">{error}</div>
  }

  if (!detail) return null

  return (
    <div className="px-5 pb-5 pt-1 bg-gray-50 border-t border-gray-100 space-y-4">
      {/* Industry badge */}
      {detail.industry && (
        <span className="inline-block text-xs font-medium bg-blue-50 text-blue-700 border border-blue-100 rounded-full px-3 py-0.5">
          {detail.industry}
        </span>
      )}

      {/* Description */}
      {detail.description && (
        <p className="text-sm text-gray-600 leading-relaxed line-clamp-4">
          {detail.description}
        </p>
      )}

      {/* Price chart */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">30-Day Price</p>
        <PriceChart history={detail.price_history} changePct={changePct} />
      </div>

      {/* Trending reason */}
      {detail.trending_reason.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Why It's Trending</p>
          <ul className="space-y-1.5">
            {detail.trending_reason.map((item, i) => (
              <li key={i} className="flex gap-2 text-sm text-gray-700">
                <span className="text-blue-400 shrink-0">•</span>
                {item.url ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:text-blue-600 hover:underline transition-colors"
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
        className="flex items-center gap-4 py-3.5 px-5 hover:bg-gray-50 transition-colors cursor-pointer select-none"
        onClick={onToggle}
        role="button"
        aria-expanded={expanded}
      >
        <span className="w-7 text-right text-sm text-gray-400 font-mono shrink-0">
          {stock.rank}
        </span>
        <div className="flex-1 min-w-0">
          <span className="font-mono font-bold text-gray-900 text-sm">{stock.ticker}</span>
          <span className="ml-2 text-sm text-gray-500 truncate hidden sm:inline">{stock.name}</span>
        </div>
        <div className="flex items-center gap-6 shrink-0">
          <span className="text-sm font-semibold tabular-nums text-gray-800 w-20 text-right">
            {formatPrice(stock.price)}
          </span>
          <div className="w-20 text-right">
            <ChangeBadge changePct={stock.change_pct} />
          </div>
          <span className="text-xs text-gray-400 tabular-nums w-16 text-right hidden md:block">
            {formatVolume(stock.volume)}
          </span>
          <span className={`text-gray-400 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}>
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
    <div className="flex items-center gap-4 py-3.5 px-5 animate-pulse">
      <span className="w-7 text-right text-sm text-gray-300 font-mono shrink-0">{rank}</span>
      <div className="flex-1">
        <div className="h-4 bg-gray-200 rounded w-24" />
      </div>
      <div className="flex items-center gap-6 shrink-0">
        <div className="h-4 bg-gray-200 rounded w-20" />
        <div className="h-4 bg-gray-200 rounded w-16" />
        <div className="h-4 bg-gray-200 rounded w-14 hidden md:block" />
      </div>
    </div>
  )
}

export default function ExplorePage() {
  const [data, setData] = useState<ExploreResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedTicker, setExpandedTicker] = useState<string | null>(null)

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
  }, [])

  const updatedAt = data
    ? new Date(data.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : null

  function handleToggle(ticker: string) {
    setExpandedTicker((prev) => (prev === ticker ? null : ticker))
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-10">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-gray-900 tracking-tight">
          🔥 Trending Stocks
        </h2>
        <p className="text-gray-500 text-sm mt-1">
          Most-watched US stocks on Yahoo Finance right now. Click a row to see details.
          {updatedAt && <span className="ml-2 text-gray-400">Updated {updatedAt}</span>}
        </p>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-4 text-red-700 text-sm">
          {error}
        </div>
      )}

      {!error && (
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          {/* Header row */}
          <div className="flex items-center gap-4 py-2.5 px-5 bg-gray-50 border-b border-gray-100">
            <span className="w-7" />
            <span className="flex-1 text-xs font-semibold text-gray-400 uppercase tracking-wide">Ticker</span>
            <div className="flex items-center gap-6 shrink-0">
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide w-20 text-right">Price</span>
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide w-20 text-right">Change</span>
              <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide w-16 text-right hidden md:block">Volume</span>
              <span className="w-4" />
            </div>
          </div>

          {/* Rows */}
          <div className="divide-y divide-gray-100">
            {loading
              ? Array.from({ length: 15 }, (_, i) => <SkeletonRow key={i} rank={i + 1} />)
              : data?.stocks.map((stock) => (
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
