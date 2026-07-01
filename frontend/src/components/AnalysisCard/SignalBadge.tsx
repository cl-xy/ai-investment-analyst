type Signal = 'buy' | 'hold' | 'sell' | 'insufficient_data'
type Confidence = 'high' | 'medium' | 'low'

interface Props {
  signal: Signal
  confidence: Confidence
}

const SIGNAL_CONFIG: Record<Signal, { label: string; color: string; bg: string; emoji: string }> = {
  buy: { label: 'BUY', color: 'text-green-800', bg: 'bg-green-100 border-green-300', emoji: '🟢' },
  hold: { label: 'HOLD', color: 'text-yellow-800', bg: 'bg-yellow-100 border-yellow-300', emoji: '🟡' },
  sell: { label: 'SELL', color: 'text-red-800', bg: 'bg-red-100 border-red-300', emoji: '🔴' },
  insufficient_data: { label: 'INSUFFICIENT DATA', color: 'text-gray-600', bg: 'bg-gray-100 border-gray-300', emoji: '⚪' },
}

const CONFIDENCE_COLOR: Record<Confidence, string> = {
  high: 'text-green-600',
  medium: 'text-yellow-600',
  low: 'text-gray-500',
}

export default function SignalBadge({ signal, confidence }: Props) {
  const cfg = SIGNAL_CONFIG[signal]
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
