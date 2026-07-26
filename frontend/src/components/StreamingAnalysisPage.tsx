import { useEffect, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useAnalysisStore } from '../stores/analysisStore'
import { useAnalysisStream } from '../hooks/useAnalysisStream'
import AgentTracePanel from './AgentTracePanel'
import DataFreshness from './DataFreshness'
import EvidenceDrawer from './EvidenceDrawer'
import { ArrowLeft, AlertCircle } from 'lucide-react'
import type { AnalysisOutput, Citation } from '../types/stream'

/**
 * Streaming analysis page. The centerpiece demo experience.
 * Shows the agent trace panel on the left and progressive analysis cards on the right.
 */
export default function StreamingAnalysisPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { connect, disconnect } = useAnalysisStream()
  const { analyses, isStreaming, error, events } = useAnalysisStore()
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null)

  const toolResults = events.filter((e) => e.type === 'tool_result')

  const tickerParam = searchParams.get('tickers') || ''
  const tickers = tickerParam.split(',').filter(Boolean)

  useEffect(() => {
    const tickerList = tickerParam.split(',').filter(Boolean)
    if (tickerList.length > 0) {
      connect(tickerList)
      document.title = `Analyzing ${tickerList.join(', ')}... | AI Investment Analyst`
    }
    return () => {
      disconnect()
      document.title = 'AI Investment Analyst'
    }
    // Re-run if tickers change (e.g. navigation without remount)
    // connect/disconnect are stable refs from useCallback
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tickerParam])

  if (tickers.length === 0) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-12 text-center">
        <AlertCircle className="w-8 h-8 text-[var(--text-muted)] mx-auto mb-3" />
        <p className="text-[var(--text-secondary)]">No tickers specified.</p>
        <button
          onClick={() => navigate('/')}
          className="mt-4 text-sm text-[var(--accent)] hover:underline focus-ring rounded"
        >
          Go back to watchlist
        </button>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto px-6 py-6">
      {/* Back button */}
      <button
        onClick={() => navigate('/')}
        className="flex items-center gap-1.5 text-sm text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors mb-6 focus-ring rounded"
      >
        <ArrowLeft className="w-4 h-4" />
        Back
      </button>

      {/* Ticker header */}
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">
          Analyzing {tickers.join(', ')}
        </h1>
        {isStreaming && (
          <p className="text-sm text-[var(--text-muted)] mt-1">
            Streaming results in real-time...
          </p>
        )}
      </div>

      {/* Main layout: trace left, cards right */}
      <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-6">
        {/* Trace panel */}
        <div className="lg:sticky lg:top-6 lg:self-start">
          <AgentTracePanel />
        </div>

        {/* Analysis cards (progressive) */}
        <div className="space-y-6">
          {Object.entries(analyses).map(([ticker, analysis]) => (
            <StreamAnalysisCard
              key={ticker}
              analysis={analysis}
              onCitationClick={setActiveCitation}
            />
          ))}

          {/* Skeleton cards for pending tickers */}
          {tickers
            .filter((t) => !analyses[t.toUpperCase()])
            .map((ticker) => (
              <SkeletonCard key={ticker} ticker={ticker.toUpperCase()} />
            ))}

          {/* Error state */}
          {error && (
            <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-5">
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-red-500 mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-red-500">Analysis failed</p>
                  <p className="text-sm text-[var(--text-secondary)] mt-1">{error}</p>
                  <button
                    onClick={() => connect(tickers)}
                    className="mt-3 text-sm text-[var(--accent)] hover:underline focus-ring rounded"
                  >
                    Retry analysis
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Evidence drawer */}
      <EvidenceDrawer
        citation={activeCitation}
        toolResults={toolResults}
        onClose={() => setActiveCitation(null)}
      />
    </div>
  )
}

function StreamAnalysisCard({ analysis, onCitationClick }: { analysis: AnalysisOutput; onCitationClick?: (citation: Citation) => void }) {
  const signalColors = {
    buy: { bg: 'bg-emerald-500/10', text: 'text-emerald-500', label: 'Buy' },
    hold: { bg: 'bg-amber-500/10', text: 'text-amber-500', label: 'Hold' },
    sell: { bg: 'bg-red-500/10', text: 'text-red-500', label: 'Sell' },
    insufficient_data: { bg: 'bg-zinc-500/10', text: 'text-zinc-400', label: 'Insufficient Data' },
  }

  const signal = signalColors[analysis.signal] || signalColors.insufficient_data

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold font-mono text-[var(--text-primary)]">
            {analysis.ticker}
          </h2>
          {analysis.thesis && (
            <p className="text-sm text-[var(--text-secondary)] mt-1 max-w-lg">
              {analysis.thesis}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${signal.bg} ${signal.text}`}>
            {signal.label}
          </span>
          <span className="text-xs font-medium px-2 py-1 rounded-full bg-[var(--surface)] text-[var(--text-muted)]">
            {analysis.confidence}
          </span>
          <DataFreshness retrievedAt={analysis.price_data?.retrieved_at as string} />
        </div>
      </div>

      {/* Sentiment bar */}
      <div className="mb-5">
        <div className="flex items-center justify-between text-xs text-[var(--text-muted)] mb-1">
          <span>Bearish</span>
          <span className="font-mono">{analysis.sentiment_score.toFixed(2)}</span>
          <span>Bullish</span>
        </div>
        <div className="h-1.5 bg-[var(--surface)] rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-300"
            style={{
              width: `${((analysis.sentiment_score + 1) / 2) * 100}%`,
              backgroundColor: analysis.sentiment_score >= 0 ? 'var(--bullish)' : 'var(--bearish)',
            }}
          />
        </div>
      </div>

      {/* Bull/Bear cases */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        {analysis.bull_case && analysis.bull_case.length > 0 && (
          <div>
            <h3 className="text-xs font-medium text-emerald-500 uppercase tracking-wider mb-2">
              Bull Case
            </h3>
            <ul className="space-y-1">
              {analysis.bull_case.map((item, i) => (
                <li key={i} className="text-sm text-[var(--text-secondary)] flex gap-2">
                  <span className="text-emerald-500 shrink-0">+</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}
        {analysis.bear_case && analysis.bear_case.length > 0 && (
          <div>
            <h3 className="text-xs font-medium text-red-500 uppercase tracking-wider mb-2">
              Bear Case
            </h3>
            <ul className="space-y-1">
              {analysis.bear_case.map((item, i) => (
                <li key={i} className="text-sm text-[var(--text-secondary)] flex gap-2">
                  <span className="text-red-500 shrink-0">−</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Risk flags */}
      {analysis.risk_flags.length > 0 && (
        <div className="mb-4">
          <h3 className="text-xs font-medium text-amber-500 uppercase tracking-wider mb-2">
            Risk Flags
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {analysis.risk_flags.map((flag, i) => (
              <span
                key={i}
                className="text-xs px-2 py-0.5 rounded bg-amber-500/10 text-amber-500"
              >
                {flag}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Data gaps */}
      {analysis.data_gaps && analysis.data_gaps.length > 0 && (
        <div className="mt-4 pt-4 border-t border-[var(--border)]">
          <p className="text-xs text-[var(--text-muted)]">
            ⚠ Based on partial data. Unavailable: {analysis.data_gaps.join(', ')}
          </p>
        </div>
      )}

      {/* Citations */}
      {analysis.citations && analysis.citations.length > 0 && (
        <div className="mt-4 pt-4 border-t border-[var(--border)]">
          <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
            Sources
          </h3>
          <div className="flex flex-wrap gap-1.5">
            {analysis.citations.map((cite, i) => (
              <button
                key={i}
                onClick={() => onCitationClick?.(cite)}
                className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--surface)] text-[var(--text-muted)] border border-[var(--border)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors cursor-pointer focus-ring"
                title={cite.claim}
              >
                {cite.provider}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function SkeletonCard({ ticker }: { ticker: string }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className="text-lg font-semibold font-mono text-[var(--text-primary)]">
            {ticker}
          </span>
          <div className="w-16 h-5 rounded-full animate-shimmer" />
        </div>
        <div className="w-12 h-6 rounded-full animate-shimmer" />
      </div>
      <div className="space-y-3">
        <div className="h-4 w-full rounded animate-shimmer" />
        <div className="h-4 w-3/4 rounded animate-shimmer" />
        <div className="h-4 w-5/6 rounded animate-shimmer" />
      </div>
      <div className="grid grid-cols-2 gap-4 mt-5">
        <div className="space-y-2">
          <div className="h-3 w-16 rounded animate-shimmer" />
          <div className="h-3 w-full rounded animate-shimmer" />
          <div className="h-3 w-4/5 rounded animate-shimmer" />
        </div>
        <div className="space-y-2">
          <div className="h-3 w-16 rounded animate-shimmer" />
          <div className="h-3 w-full rounded animate-shimmer" />
          <div className="h-3 w-4/5 rounded animate-shimmer" />
        </div>
      </div>
    </div>
  )
}
