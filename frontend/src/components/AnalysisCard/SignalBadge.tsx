import { AlertCircle, TrendingUp, Minus, TrendingDown, type LucideIcon } from 'lucide-react'

type Signal = 'buy' | 'hold' | 'sell' | 'insufficient_data'
type Confidence = 'high' | 'medium' | 'low'

interface Props {
  signal: Signal
  confidence: Confidence
}

const SIGNAL_CONFIG: Record<Signal, { label: string; color: string; bg: string; icon: LucideIcon }> = {
  buy: { label: 'BUY', color: 'text-[var(--bullish)]', bg: 'bg-emerald-500/10 border-emerald-500/30', icon: TrendingUp },
  hold: { label: 'HOLD', color: 'text-[var(--neutral)]', bg: 'bg-amber-500/10 border-amber-500/30', icon: Minus },
  sell: { label: 'SELL', color: 'text-[var(--bearish)]', bg: 'bg-red-500/10 border-red-500/30', icon: TrendingDown },
  insufficient_data: { label: 'INSUFFICIENT DATA', color: 'text-[var(--text-muted)]', bg: 'bg-[var(--surface)] border-[var(--border)]', icon: AlertCircle },
}

const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
}

const CONFIDENCE_COLOR: Record<Confidence, string> = {
  high: 'text-[var(--text-primary)]',
  medium: 'text-[var(--neutral)]',
  low: 'text-[var(--text-muted)]',
}

export default function SignalBadge({ signal, confidence }: Props) {
  const cfg = SIGNAL_CONFIG[signal] ?? SIGNAL_CONFIG.insufficient_data
  const safeConfidence = confidence && CONFIDENCE_COLOR[confidence] ? confidence : 'low'

  if (signal === 'insufficient_data' || !SIGNAL_CONFIG[signal]) {
    return (
      <div
        className={`inline-flex flex-col items-center px-5 py-3 rounded-xl border ${cfg.bg} max-w-[200px]`}
        role="status"
        aria-label="Signal: Insufficient data"
      >
        <AlertCircle className="w-5 h-5 text-[var(--text-muted)] mb-1" aria-hidden="true" />
        <span className={`font-bold text-sm ${cfg.color}`}>{cfg.label}</span>
        <p className="text-[10px] text-[var(--text-muted)] text-center mt-1.5 leading-relaxed">
          Not enough data sources returned results. Try a higher-volume ticker or check back during market hours.
        </p>
      </div>
    )
  }

  const Icon = cfg.icon

  return (
    <div
      className={`inline-flex flex-col items-center px-5 py-3 rounded-xl border ${cfg.bg}`}
      role="status"
      aria-label={`Signal: ${cfg.label}, ${CONFIDENCE_LABEL[safeConfidence]} confidence`}
    >
      <Icon className={`w-6 h-6 ${cfg.color}`} aria-hidden="true" />
      <span className={`font-bold text-lg ${cfg.color}`}>{cfg.label}</span>
      <span className={`text-xs font-medium mt-0.5 ${CONFIDENCE_COLOR[safeConfidence]}`}>
        {CONFIDENCE_LABEL[safeConfidence]} Confidence
      </span>
    </div>
  )
}
