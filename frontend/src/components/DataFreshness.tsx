import { Clock } from 'lucide-react'

interface DataFreshnessProps {
  retrievedAt: string | null | undefined
  className?: string
}

/**
 * "Data as of" badge showing how fresh the analysis data is.
 * Converts ISO timestamps to relative time (e.g., "2h ago", "5m ago").
 */
export default function DataFreshness({ retrievedAt, className = '' }: DataFreshnessProps) {
  if (!retrievedAt) return null

  const timestamp = new Date(retrievedAt)
  if (isNaN(timestamp.getTime())) return null

  const now = new Date()
  const diffMs = now.getTime() - timestamp.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const diffHr = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHr / 24)

  let label: string
  if (diffMin < 1) label = 'just now'
  else if (diffMin < 60) label = `${diffMin}m ago`
  else if (diffHr < 24) label = `${diffHr}h ago`
  else label = `${diffDay}d ago`

  const isStale = diffHr >= 24

  return (
    <span
      className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded ${
        isStale
          ? 'bg-amber-500/10 text-amber-500'
          : 'bg-[var(--surface)] text-[var(--text-muted)]'
      } ${className}`}
      title={`Data retrieved at ${timestamp.toLocaleString()}`}
    >
      <Clock className="w-2.5 h-2.5" />
      {isStale ? `stale: ${label}` : `as of ${label}`}
    </span>
  )
}
