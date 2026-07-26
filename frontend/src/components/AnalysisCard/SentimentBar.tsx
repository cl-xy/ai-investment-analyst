interface Props {
  score: number // -1.0 to 1.0
}

export default function SentimentBar({ score }: Props) {
  const clamped = Math.max(-1, Math.min(1, score))

  const color =
    clamped >= 0.3 ? 'bg-emerald-500' : clamped <= -0.3 ? 'bg-red-500' : 'bg-amber-400'

  const label =
    clamped >= 0.3 ? 'Positive' : clamped <= -0.3 ? 'Negative' : 'Neutral'

  return (
    <div>
      <div className="flex justify-between text-xs text-[var(--text-muted)] mb-1">
        <span>Bearish</span>
        <span className="font-medium text-[var(--text-secondary)]">
          Sentiment: <span className={clamped >= 0.3 ? 'text-[var(--bullish)]' : clamped <= -0.3 ? 'text-[var(--bearish)]' : 'text-[var(--neutral)]'}>{label}</span>
          {' '}({clamped > 0 ? '+' : ''}{clamped.toFixed(2)})
        </span>
        <span>Bullish</span>
      </div>
      <div className="relative h-3 bg-[var(--surface)] rounded-full overflow-hidden">
        {/* center tick */}
        <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-[var(--text-muted)] z-10" />
        <div
          className={`absolute top-0 bottom-0 ${color} rounded-full transition-all`}
          style={
            clamped >= 0
              ? { left: '50%', width: `${(clamped / 1) * 50}%` }
              : { right: '50%', width: `${(Math.abs(clamped) / 1) * 50}%` }
          }
        />
      </div>
    </div>
  )
}
