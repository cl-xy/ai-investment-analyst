import { Shield, Database, Clock, WifiOff, AlertTriangle } from 'lucide-react'

// --- ConfidenceBadge ---

interface ConfidenceBadgeProps {
  level: 'high' | 'medium' | 'low'
  label?: string
  compact?: boolean
}

const confidenceConfig = {
  high: {
    dotClass: 'bg-[var(--bullish)]',
    textClass: 'text-[var(--bullish)]',
    text: 'High',
  },
  medium: {
    dotClass: 'bg-[var(--neutral)]',
    textClass: 'text-[var(--neutral)]',
    text: 'Medium',
  },
  low: {
    dotClass: 'bg-transparent border border-[var(--bearish)]',
    textClass: 'text-[var(--bearish)]',
    text: 'Low',
  },
} as const

export function ConfidenceBadge({ level, label, compact = false }: ConfidenceBadgeProps) {
  const config = confidenceConfig[level]
  const ariaText = `${label ?? 'Confidence'}: ${config.text}`

  if (compact) {
    return (
      <span
        className="inline-flex items-center"
        aria-label={ariaText}
        title={ariaText}
      >
        <span className={`w-2 h-2 rounded-full ${config.dotClass}`} />
      </span>
    )
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 text-[10px] font-medium px-1.5 py-0.5 rounded
        bg-[var(--surface)] ${config.textClass}`}
      aria-label={ariaText}
    >
      <span className={`w-2 h-2 rounded-full ${config.dotClass}`} />
      {label && <span className="text-[var(--text-muted)]">{label}:</span>}
      {config.text}
    </span>
  )
}

// --- ProvenanceBadge ---

interface ProvenanceBadgeProps {
  source: 'yfinance' | 'newsapi' | 'sec_edgar' | 'openrouter' | 'cache' | 'unknown'
  freshness: 'live' | 'recent' | 'stale' | 'cached'
  retrievedAt?: string
  compact?: boolean
}

const sourceLabels: Record<ProvenanceBadgeProps['source'], string> = {
  yfinance: 'Yahoo Finance',
  newsapi: 'NewsAPI',
  sec_edgar: 'SEC EDGAR',
  openrouter: 'OpenRouter',
  cache: 'Cache',
  unknown: 'Unknown',
}

const freshnessConfig = {
  live: { dotClass: 'bg-[var(--live)] animate-pulse', text: 'Live' },
  recent: { dotClass: 'bg-[var(--bullish)]', text: 'Recent' },
  stale: { dotClass: 'bg-[var(--neutral)]', text: 'Stale' },
  cached: { dotClass: 'bg-[var(--cached)]', text: 'Cached' },
} as const

function SourceIcon({ source }: { source: ProvenanceBadgeProps['source'] }) {
  const cls = 'w-2.5 h-2.5'
  switch (source) {
    case 'yfinance':
    case 'newsapi':
    case 'sec_edgar':
      return <Database className={cls} />
    case 'openrouter':
      return <Shield className={cls} />
    case 'cache':
      return <Clock className={cls} />
    default:
      return <WifiOff className={cls} />
  }
}

export function ProvenanceBadge({ source, freshness, retrievedAt, compact = false }: ProvenanceBadgeProps) {
  const fConfig = freshnessConfig[freshness]
  const label = sourceLabels[source]
  const ariaText = `Source: ${label}, ${fConfig.text}${retrievedAt ? `, retrieved ${new Date(retrievedAt).toLocaleString()}` : ''}`

  const tooltip = retrievedAt
    ? `${label} (${fConfig.text}) - Retrieved: ${new Date(retrievedAt).toLocaleString()}`
    : `${label} (${fConfig.text})`

  if (compact) {
    return (
      <span
        className="inline-flex items-center gap-1"
        aria-label={ariaText}
        title={tooltip}
      >
        <span className={`w-1.5 h-1.5 rounded-full ${fConfig.dotClass}`} />
        <SourceIcon source={source} />
      </span>
    )
  }

  return (
    <span
      className="group relative inline-flex items-center gap-1.5 text-[10px] font-medium
        px-1.5 py-0.5 rounded bg-[var(--surface)] text-[var(--text-secondary)]"
      aria-label={ariaText}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${fConfig.dotClass}`} />
      <SourceIcon source={source} />
      <span>{label}</span>
      {/* Tooltip on hover */}
      {retrievedAt && (
        <span
          className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5
            whitespace-nowrap rounded bg-[var(--surface-elevated)] border border-[var(--border)]
            px-2 py-1 text-[9px] text-[var(--text-muted)] opacity-0 transition-opacity
            duration-[var(--motion-micro)] group-hover:opacity-100 group-focus-within:opacity-100"
          role="tooltip"
        >
          Retrieved: {new Date(retrievedAt).toLocaleString()}
        </span>
      )}
    </span>
  )
}

// --- SignalStrengthMeter ---

interface SignalStrengthMeterProps {
  score: number // -1 to 1
  size?: 'sm' | 'md'
}

export function SignalStrengthMeter({ score, size = 'sm' }: SignalStrengthMeterProps) {
  const clamped = Math.max(-1, Math.min(1, score))
  const barCount = 5
  const heights = size === 'sm' ? [4, 6, 8, 10, 12] : [6, 9, 12, 15, 18]
  const barWidth = size === 'sm' ? 3 : 4
  const gap = size === 'sm' ? 1 : 1.5
  const maxH = heights[barCount - 1]

  // Determine how many bars to fill and from which direction
  // Positive (bullish): fill left to right
  // Negative (bearish): fill right to left
  // Near zero (neutral): fill from center outward
  const absScore = Math.abs(clamped)
  const filledCount = Math.round(absScore * barCount)

  const isBullish = clamped > 0.1
  const isBearish = clamped < -0.1
  // Neutral when between -0.1 and 0.1

  let fillColor: string
  if (isBullish) fillColor = 'var(--bullish)'
  else if (isBearish) fillColor = 'var(--bearish)'
  else fillColor = 'var(--neutral)'

  const getBarFilled = (index: number): boolean => {
    if (isBullish) {
      // Fill from left
      return index < filledCount
    } else if (isBearish) {
      // Fill from right
      return index >= barCount - filledCount
    } else {
      // Neutral: fill from center outward
      const center = Math.floor(barCount / 2)
      const dist = Math.abs(index - center)
      return dist < filledCount
    }
  }

  const totalWidth = barCount * barWidth + (barCount - 1) * gap
  const ariaText = `Signal strength: ${clamped > 0 ? '+' : ''}${(clamped * 100).toFixed(0)}%`

  return (
    <span
      className="inline-flex items-end"
      style={{ width: totalWidth, height: maxH }}
      aria-label={ariaText}
      title={ariaText}
      role="meter"
      aria-valuemin={-1}
      aria-valuemax={1}
      aria-valuenow={clamped}
    >
      {heights.map((h, i) => {
        const filled = getBarFilled(i)
        return (
          <span
            key={i}
            className="rounded-[1px] transition-colors duration-[var(--motion-micro)]"
            style={{
              width: barWidth,
              height: h,
              marginLeft: i > 0 ? gap : 0,
              backgroundColor: filled ? fillColor : 'var(--border)',
            }}
          />
        )
      })}
    </span>
  )
}

// --- DataQualityIndicator ---

interface DataQualityIndicatorProps {
  dataGaps: string[]
  totalSources: number
  successfulSources: number
}

export function DataQualityIndicator({ dataGaps, totalSources, successfulSources }: DataQualityIndicatorProps) {
  const segments = totalSources
  const filled = Math.min(successfulSources, totalSources)
  const hasGaps = dataGaps.length > 0

  const ariaText = `Data quality: ${filled}/${segments} sources available${hasGaps ? `. Missing: ${dataGaps.join(', ')}` : ''}`
  const tooltip = hasGaps
    ? `${filled}/${segments} sources. Missing: ${dataGaps.join(', ')}`
    : `${filled}/${segments} sources available`

  return (
    <span
      className="group relative inline-flex items-center gap-1.5 text-[10px] font-medium
        px-1.5 py-0.5 rounded bg-[var(--surface)] text-[var(--text-secondary)]"
      aria-label={ariaText}
      title={tooltip}
    >
      {/* Segmented bar */}
      <span className="inline-flex items-center gap-[2px]">
        {Array.from({ length: segments }).map((_, i) => (
          <span
            key={i}
            className="rounded-[1px] transition-colors duration-[var(--motion-micro)]"
            style={{
              width: 6,
              height: 10,
              backgroundColor: i < filled ? 'var(--bullish)' : 'var(--border)',
            }}
          />
        ))}
      </span>

      {/* Warning icon for gaps */}
      {hasGaps && (
        <AlertTriangle className="w-2.5 h-2.5 text-[var(--neutral)]" />
      )}

      <span className="text-[var(--text-muted)]">
        {filled}/{segments}
      </span>

      {/* Tooltip listing gaps */}
      {hasGaps && (
        <span
          className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5
            whitespace-nowrap rounded bg-[var(--surface-elevated)] border border-[var(--border)]
            px-2 py-1 text-[9px] text-[var(--text-muted)] opacity-0 transition-opacity
            duration-[var(--motion-micro)] group-hover:opacity-100 group-focus-within:opacity-100"
          role="tooltip"
        >
          Missing: {dataGaps.join(', ')}
        </span>
      )}
    </span>
  )
}
