import { TrendingUp, TrendingDown, Scale, ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'
import { useAnalysisStore } from '../stores/analysisStore'
import Markdown from './Markdown'

/** Safely extract a display string from an argument that may be a string or an object. */
function toDisplayString(value: unknown): string {
  if (typeof value === 'string') return value
  if (value && typeof value === 'object') {
    const obj = value as Record<string, unknown>
    return (obj.claim as string) || (obj.text as string) || JSON.stringify(value)
  }
  return String(value ?? '')
}

const ROLE_CONFIG = {
  bull: {
    label: 'Bull Analyst',
    icon: TrendingUp,
    color: 'var(--bullish)',
    bgClass: 'bg-[var(--bullish)]/10 border-[var(--bullish)]/20',
    textClass: 'text-[var(--bullish)]',
  },
  bear: {
    label: 'Bear Analyst',
    icon: TrendingDown,
    color: 'var(--bearish)',
    bgClass: 'bg-[var(--bearish)]/10 border-[var(--bearish)]/20',
    textClass: 'text-[var(--bearish)]',
  },
  moderator: {
    label: 'Chief Investment Officer',
    icon: Scale,
    color: 'var(--accent)',
    bgClass: 'bg-[var(--accent)]/10 border-[var(--accent)]/20',
    textClass: 'text-[var(--accent)]',
  },
} as const

interface DebatePanelProps {
  ticker: string
}

export default function DebatePanel({ ticker }: DebatePanelProps) {
  const debate = useAnalysisStore((s) => s.debates[ticker])
  const [expanded, setExpanded] = useState(true)

  if (!debate || (debate.turns.length === 0 && !debate.isActive)) return null

  return (
    <div className="w-full rounded-xl border border-[var(--border)] bg-[var(--surface)] overflow-hidden">
      {/* Header */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-[var(--surface-elevated)] transition-colors"
        aria-expanded={expanded}
        aria-controls={`debate-${ticker}`}
      >
        <div className="flex items-center gap-2">
          <Scale className="w-4 h-4 text-[var(--accent)]" />
          <span className="text-sm font-semibold text-[var(--text-primary)]">
            Investment Committee Debate
          </span>
          {debate.isActive && (
            <span className="flex items-center gap-1 text-[10px] font-medium text-[var(--live)] uppercase tracking-wider">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--live)] animate-pulse" />
              Live
            </span>
          )}
          {debate.verdict && (
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
              debate.verdict.signal === 'buy' ? 'bg-[var(--bullish)]/15 text-[var(--bullish)]' :
              debate.verdict.signal === 'sell' ? 'bg-[var(--bearish)]/15 text-[var(--bearish)]' :
              'bg-[var(--text-muted)]/15 text-[var(--text-secondary)]'
            }`}>
              {(debate.verdict.signal ?? 'hold').toUpperCase()}
            </span>
          )}
        </div>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-[var(--text-muted)]" />
        ) : (
          <ChevronDown className="w-4 h-4 text-[var(--text-muted)]" />
        )}
      </button>

      {/* Debate turns */}
      {expanded && (
        <div id={`debate-${ticker}`} className="px-4 pb-4 space-y-3">
          {debate.turns.map((turn, i) => {
            const config = ROLE_CONFIG[turn.role]
            const Icon = config.icon

            return (
              <div
                key={i}
                className={`rounded-lg border p-3 ${config.bgClass} animate-fade-in`}
                style={{ animationDelay: `${i * 100}ms` }}
              >
                {/* Turn header */}
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Icon className="w-3.5 h-3.5" style={{ color: config.color }} />
                    <span className={`text-xs font-semibold ${config.textClass}`}>
                      {config.label}
                    </span>
                    <span className="text-[10px] text-[var(--text-muted)] font-medium uppercase">
                      {turn.confidence} confidence
                    </span>
                  </div>
                  {turn.duration_ms > 0 && (
                    <span className="text-[10px] text-[var(--text-muted)]">
                      {(turn.duration_ms / 1000).toFixed(1)}s
                    </span>
                  )}
                </div>

                {/* Thesis */}
                <Markdown className="mb-2">{turn.thesis}</Markdown>

                {/* Arguments */}
                {turn.key_arguments.length > 0 && (
                  <ul className="space-y-1">
                    {turn.key_arguments.map((arg, j) => (
                      <li
                        key={j}
                        className="flex items-start gap-2 text-xs text-[var(--text-secondary)] leading-relaxed"
                      >
                        <span className="shrink-0 mt-1 w-1 h-1 rounded-full" style={{ backgroundColor: config.color }} />
                        {toDisplayString(arg)}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )
          })}

          {/* Verdict */}
          {debate.verdict && (
            <div className="rounded-lg border-2 border-[var(--accent)]/30 bg-[var(--accent)]/5 p-4 animate-fade-in">
              <div className="flex items-center gap-2 mb-2">
                <Scale className="w-4 h-4 text-[var(--accent)]" />
                <span className="text-xs font-bold text-[var(--accent)] uppercase tracking-wider">
                  Verdict
                </span>
                <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${
                  debate.verdict.signal === 'buy' ? 'bg-[var(--bullish)]/20 text-[var(--bullish)]' :
                  debate.verdict.signal === 'sell' ? 'bg-[var(--bearish)]/20 text-[var(--bearish)]' :
                  'bg-[var(--text-muted)]/20 text-[var(--text-secondary)]'
                }`}>
                  {debate.verdict.signal.toUpperCase()} ({debate.verdict.confidence})
                </span>
              </div>
              <Markdown className="mb-3">{debate.verdict.verdict_rationale}</Markdown>
              {debate.verdict.key_disagreements.length > 0 && (
                <div>
                  <p className="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wider mb-1">
                    Key Disagreements
                  </p>
                  <ul className="space-y-1">
                    {debate.verdict.key_disagreements.map((d, i) => (
                      <li key={i} className="text-xs text-[var(--text-secondary)] flex items-start gap-2">
                        <span className="shrink-0 mt-1 w-1 h-1 rounded-full bg-[var(--warning)]" />
                        {toDisplayString(d)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Loading state for active debate */}
          {debate.isActive && (
            <div className="flex items-center gap-2 py-2">
              <div className="flex gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-xs text-[var(--text-muted)]">
                {debate.turns.length === 0 && 'Bull analyst preparing case...'}
                {debate.turns.length === 1 && 'Bear analyst preparing rebuttal...'}
                {debate.turns.length === 2 && 'CIO deliberating verdict...'}
                {debate.turns.length >= 3 && 'Analysts deliberating...'}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
