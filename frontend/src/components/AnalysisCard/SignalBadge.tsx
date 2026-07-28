import { AlertCircle } from 'lucide-react'

type Signal = 'buy' | 'hold' | 'sell' | 'insufficient_data'
type Confidence = 'high' | 'medium' | 'low'

interface Props {
  signal: Signal
  confidence: Confidence
}

const SIGNAL_CONFIG: Record<Signal, { label: string; color: string; bg: string; emoji: string }> = {
  buy: { label: 'BUY', color: 'text-[var(--bullish)]', bg: 'bg-emerald-500/10 border-emerald-500/30', emoji: '🟢' },
  hold: { label: 'HOLD', color: 'text-[var(--neutral)]', bg: 'bg-amber-500/10 border-amber-500/30', emoji: '🟡' },
  sell: { label: 'SELL', color: 'text-[var(--bearish)]', bg: 'bg-red-500/10 border-red-500/30', emoji: '🔴' },
  insufficient_data: { label: 'INSUFFICIENT DATA', color: 'text-[var(--text-muted)]', bg: 'bg-[var(--surface)] border-[var(--border)]', emoji: '⚪' },
}

const CONFIDENCE_COLOR: Record<Confidence, string> = {
  high: 'text-[var(--bullish)]',
  medium: 'text-[var(--neutral)]',
  low: 'text-[var(--text-muted)]',
}

export default function SignalBadge({ signal, confidence }: Props) {
  const cfg = SIGNAL_CONFIG[signal]

  if (signal === 'insufficient_data') {
    return (
      <div className={`inline-flex flex-col items-center px-5 py-3 rounded-xl border ${cfg.bg} max-w-[200px]`}>
        <AlertCircle className="w-5 h-5 text-[var(--text-muted)] mb-1" />
        <span className={`font-bold text-sm ${cfg.color}`}>{cfg.label}</span>
        <p className="text-[10px] text-[var(--text-muted)] text-center mt-1.5 leading-relaxed">
          Not enough data sources returned results. Try a higher-volume ticker or check back during market hours.
        </p>
      </div>
    )
  }

  return (
    <div className={`inline-flex flex-col items-center px-5 py-3 rounded-xl border ${cfg.bg}`}>
      <span className="text-2xl">{cfg.emoji}</span>
      <span className={`font-bold text-lg ${cfg.color}`}>{cfg.label}</span>
      <span className={`text-xs font-medium mt-0.5 ${CONFIDENCE_COLOR[confidence]}`}>
        {confidence.charAt(0).toUpperCase() + confidence.slice(1)} Confidence
      </span>
    </div>
  )
}
