import { useState, useId } from 'react'
import { Info } from 'lucide-react'

interface Props {
  score: number // -1.0 to 1.0
}

export default function SentimentBar({ score }: Props) {
  const [showTooltip, setShowTooltip] = useState(false)
  const tooltipId = useId()
  const clamped = Math.max(-1, Math.min(1, score))

  const color =
    clamped >= 0.3 ? 'bg-emerald-500' : clamped <= -0.3 ? 'bg-red-500' : 'bg-amber-400'

  const label =
    clamped >= 0.3 ? 'Positive' : clamped <= -0.3 ? 'Negative' : 'Neutral'

  return (
    <div>
      <div className="flex justify-between items-center text-xs text-[var(--text-muted)] mb-1">
        <span>Bearish</span>
        <span className="font-medium text-[var(--text-secondary)] flex items-center gap-1.5">
          Sentiment: <span className={clamped >= 0.3 ? 'text-[var(--bullish)]' : clamped <= -0.3 ? 'text-[var(--bearish)]' : 'text-[var(--neutral)]'}>{label}</span>
          {' '}({clamped > 0 ? '+' : ''}{clamped.toFixed(2)})
          <span className="relative inline-flex">
            <button
              type="button"
              onClick={() => setShowTooltip((v) => !v)}
              onBlur={() => setShowTooltip(false)}
              onKeyDown={(e) => { if (e.key === 'Escape') setShowTooltip(false) }}
              className="text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors focus-ring rounded"
              aria-label="Sentiment score explanation"
              aria-expanded={showTooltip}
              aria-describedby={showTooltip ? tooltipId : undefined}
            >
              <Info className="w-3 h-3" />
            </button>
            {showTooltip && (
              <div
                id={tooltipId}
                className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 px-3 py-2 rounded-lg bg-[var(--surface-elevated)] border border-[var(--border)] shadow-lg text-[10px] text-[var(--text-secondary)] leading-relaxed z-20 animate-fade-in"
                role="tooltip"
              >
                <p className="font-medium text-[var(--text-primary)] mb-1">Sentiment Scale</p>
                <p>Ranges from -1.0 (max bearish) to +1.0 (max bullish). Zero is neutral.</p>
                <p className="mt-1 text-[var(--text-muted)]">Based on multi-agent analysis of news tone, analyst sentiment, and market signals.</p>
              </div>
            )}
          </span>
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
      {/* Scale markers */}
      <div className="flex justify-between text-[10px] text-[var(--text-muted)] mt-0.5 px-0.5 font-mono">
        <span>-1.0</span>
        <span>0</span>
        <span>+1.0</span>
      </div>
    </div>
  )
}
