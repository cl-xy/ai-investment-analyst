import { useState, useRef, useEffect, useCallback } from 'react'
import { Download, FileJson, FileText, ChevronDown, Check } from 'lucide-react'
import { toastSuccess } from '../stores/toastStore'

interface AnalysisData {
  ticker: string
  signal: 'buy' | 'hold' | 'sell' | 'insufficient_data'
  confidence: string
  sentiment_score: number
  thesis?: string
  bull_case?: string[]
  bear_case?: string[]
  risk_flags?: string[]
  data_gaps?: string[]
  citations?: Array<{ provider: string; claim: string }>
}

interface RunMeta {
  run_id: string
  startedAt: string
  totalDurationMs?: number
  totalTokens?: number
}

interface DebateData {
  turns: Array<{ role: string; thesis: string; confidence: string; key_arguments: string[] }>
  verdict: { signal?: string; final_signal?: string; verdict_rationale?: string; rationale?: string; key_disagreements: string[] } | null
}

export interface ReportExportButtonProps {
  analyses: Record<string, AnalysisData>
  runMeta?: RunMeta | null
  debates?: Record<string, DebateData>
  disabled?: boolean
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${Math.round(ms / 1000)}s`
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
}

function getTickerLabel(analyses: Record<string, AnalysisData>): string {
  const tickers = Object.keys(analyses)
  if (tickers.length === 1) return tickers[0]
  if (tickers.length <= 3) return tickers.join('_')
  return `${tickers.length}_tickers`
}

function getFilename(analyses: Record<string, AnalysisData>, ext: string): string {
  const label = getTickerLabel(analyses)
  const date = new Date().toISOString().slice(0, 10)
  return `${label}_analysis_${date}.${ext}`
}

function triggerDownload(content: string, filename: string, mimeType: string) {
  const blob = new Blob([content], { type: mimeType })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function generateReport(
  analyses: Record<string, AnalysisData>,
  runMeta?: RunMeta | null,
  debates?: Record<string, DebateData>
): { json: string; markdown: string } {
  // JSON report
  const jsonReport = {
    version: '1.0',
    generated_at: new Date().toISOString(),
    run_id: runMeta?.run_id ?? null,
    duration_ms: runMeta?.totalDurationMs ?? null,
    analyses,
    debates: debates ?? {},
  }
  const jsonString = JSON.stringify(jsonReport, null, 2)

  // Markdown report
  const lines: string[] = []
  lines.push('# Investment Analysis Report')

  const metaParts: string[] = []
  metaParts.push(`Generated: ${formatDate(new Date().toISOString())}`)
  if (runMeta?.totalDurationMs) {
    metaParts.push(`Duration: ${formatDuration(runMeta.totalDurationMs)}`)
  }
  if (runMeta?.totalTokens) {
    metaParts.push(`Tokens: ${runMeta.totalTokens.toLocaleString()}`)
  }
  lines.push(metaParts.join(' | '))
  lines.push('')

  for (const [ticker, analysis] of Object.entries(analyses)) {
    const signal = analysis.signal.replace('_', ' ')
    const signalLabel = signal.charAt(0).toUpperCase() + signal.slice(1)
    lines.push(`## ${ticker} - ${signalLabel} (${analysis.confidence} Confidence)`)

    if (analysis.thesis) {
      lines.push(`**Thesis:** ${analysis.thesis}`)
      lines.push('')
    }

    const sentimentLabel =
      analysis.sentiment_score > 0.3
        ? 'Bullish'
        : analysis.sentiment_score < -0.3
          ? 'Bearish'
          : 'Neutral'
    lines.push(`### Sentiment: ${analysis.sentiment_score.toFixed(2)} (${sentimentLabel})`)
    lines.push('')

    if (analysis.bull_case && analysis.bull_case.length > 0) {
      lines.push('### Bull Case')
      for (const point of analysis.bull_case) {
        lines.push(`- ${point}`)
      }
      lines.push('')
    }

    if (analysis.bear_case && analysis.bear_case.length > 0) {
      lines.push('### Bear Case')
      for (const point of analysis.bear_case) {
        lines.push(`- ${point}`)
      }
      lines.push('')
    }

    if (analysis.risk_flags && analysis.risk_flags.length > 0) {
      lines.push('### Risk Flags')
      for (const flag of analysis.risk_flags) {
        lines.push(`- ${flag}`)
      }
      lines.push('')
    }

    if (analysis.data_gaps && analysis.data_gaps.length > 0) {
      lines.push('### Data Gaps')
      for (const gap of analysis.data_gaps) {
        lines.push(`- ${gap}`)
      }
      lines.push('')
    }

    if (analysis.citations && analysis.citations.length > 0) {
      lines.push('### Sources')
      for (const cite of analysis.citations) {
        lines.push(`- **${cite.provider}**: ${cite.claim}`)
      }
      lines.push('')
    }

    // Debate summary for this ticker
    const debate = debates?.[ticker]
    if (debate && debate.verdict) {
      const verdictSignal = debate.verdict.final_signal || debate.verdict.signal || 'unknown'
      const verdictRationale = debate.verdict.rationale || debate.verdict.verdict_rationale || ''
      lines.push('### Debate Summary')
      lines.push(`**Verdict:** ${verdictSignal.charAt(0).toUpperCase() + verdictSignal.slice(1)}`)
      lines.push(`**Rationale:** ${verdictRationale}`)
      if (debate.verdict.key_disagreements.length > 0) {
        lines.push('**Key Disagreements:**')
        for (const d of debate.verdict.key_disagreements) {
          lines.push(`- ${d}`)
        }
      }
      lines.push('')
    }

    lines.push('---')
    lines.push('')
  }

  lines.push('*Report generated by AI Investment Analyst*')

  return { json: jsonString, markdown: lines.join('\n') }
}

export function ReportExportButton({
  analyses,
  runMeta,
  debates,
  disabled = false,
}: ReportExportButtonProps) {
  const [open, setOpen] = useState(false)
  const [recentExport, setRecentExport] = useState<'json' | 'md' | null>(null)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const hasData = Object.keys(analyses).length > 0
  const isDisabled = disabled || !hasData

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  // Close dropdown on Escape
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape' && open) {
        setOpen(false)
      }
    }
    if (open) {
      document.addEventListener('keydown', handleKeyDown)
    }
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open])

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  const showCheckmark = useCallback((type: 'json' | 'md') => {
    setRecentExport(type)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      setRecentExport(null)
      timerRef.current = null
    }, 2000)
  }, [])

  const handleExportJson = useCallback(() => {
    const { json } = generateReport(analyses, runMeta, debates)
    const filename = getFilename(analyses, 'json')
    triggerDownload(json, filename, 'application/json')
    toastSuccess('JSON report exported')
    showCheckmark('json')
    setOpen(false)
  }, [analyses, runMeta, debates, showCheckmark])

  const handleExportMarkdown = useCallback(() => {
    const { markdown } = generateReport(analyses, runMeta, debates)
    const filename = getFilename(analyses, 'md')
    triggerDownload(markdown, filename, 'text/markdown')
    toastSuccess('Markdown report exported')
    showCheckmark('md')
    setOpen(false)
  }, [analyses, runMeta, debates, showCheckmark])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        if (!open) {
          setOpen(true)
        }
      }
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        setOpen((prev) => !prev)
      }
    },
    [open]
  )

  const handleOptionKeyDown = useCallback(
    (e: React.KeyboardEvent, action: () => void, otherRef: 'json' | 'md') => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        action()
      }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault()
        // Move focus to the other option
        const container = dropdownRef.current
        if (container) {
          const items = container.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')
          const currentIdx = otherRef === 'md' ? 0 : 1
          const nextIdx = currentIdx === 0 ? 1 : 0
          items[nextIdx]?.focus()
        }
      }
      if (e.key === 'Escape') {
        setOpen(false)
      }
    },
    []
  )

  return (
    <div className="relative inline-block" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => !isDisabled && setOpen((prev) => !prev)}
        onKeyDown={handleKeyDown}
        disabled={isDisabled}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label="Export report"
        className={`
          inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg
          border border-[var(--border)] bg-[var(--surface)] text-[var(--text-primary)]
          transition-colors duration-150 ease-out
          hover:bg-[var(--surface-elevated)] hover:border-[var(--accent)]
          focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40
          disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-[var(--surface)] disabled:hover:border-[var(--border)]
        `}
      >
        {recentExport ? (
          <Check className="w-4 h-4 text-[var(--accent)]" />
        ) : (
          <Download className="w-4 h-4" />
        )}
        <span>Export</span>
        <ChevronDown className={`w-3.5 h-3.5 transition-transform duration-150 ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Export format options"
          className={`
            absolute right-0 top-full mt-1 z-50 w-48
            rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)]
            shadow-lg shadow-black/10
            py-1 animate-in fade-in slide-in-from-top-1 duration-150
          `}
        >
          <button
            role="menuitem"
            tabIndex={0}
            onClick={handleExportJson}
            onKeyDown={(e) => handleOptionKeyDown(e, handleExportJson, 'md')}
            className={`
              w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left
              text-[var(--text-primary)] hover:bg-[var(--accent-bg)]
              transition-colors duration-100
              focus:outline-none focus:bg-[var(--accent-bg)]
            `}
          >
            {recentExport === 'json' ? (
              <Check className="w-4 h-4 text-[var(--accent)]" />
            ) : (
              <FileJson className="w-4 h-4 text-[var(--text-muted)]" />
            )}
            <span>Export JSON</span>
          </button>
          <button
            role="menuitem"
            tabIndex={0}
            onClick={handleExportMarkdown}
            onKeyDown={(e) => handleOptionKeyDown(e, handleExportMarkdown, 'json')}
            className={`
              w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left
              text-[var(--text-primary)] hover:bg-[var(--accent-bg)]
              transition-colors duration-100
              focus:outline-none focus:bg-[var(--accent-bg)]
            `}
          >
            {recentExport === 'md' ? (
              <Check className="w-4 h-4 text-[var(--accent)]" />
            ) : (
              <FileText className="w-4 h-4 text-[var(--text-muted)]" />
            )}
            <span>Export Markdown</span>
          </button>
        </div>
      )}
    </div>
  )
}
