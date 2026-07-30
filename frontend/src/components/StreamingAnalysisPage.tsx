import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import { useAnalysisStore } from '../stores/analysisStore'
import { useAnalysisStream } from '../hooks/useAnalysisStream'
import AgentTracePanel from './AgentTracePanel'
import DataFreshness from './DataFreshness'
import DebatePanel from './DebatePanel'
import EvidenceDrawer from './EvidenceDrawer'
import InvestmentDisclaimer from './InvestmentDisclaimer'
import { ArrowLeft, AlertCircle, Play, Clock, Layers, ChevronDown } from 'lucide-react'
import type { AnalysisOutput, Citation, PeerComparisonPayload, StreamEvent } from '../types/stream'

/**
 * Streaming analysis page. The centerpiece demo experience.
 * Shows the agent trace panel on the left and progressive analysis cards on the right.
 */
export default function StreamingAnalysisPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { connect, disconnect } = useAnalysisStream()
  const { analyses, isStreaming, error, events, debates, peerComparison } = useAnalysisStore()
  const [activeCitation, setActiveCitation] = useState<Citation | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const hasConnectedRef = useRef(false)

  const toolResults = useMemo(() => events.filter((e) => e.type === 'tool_result'), [events])

  const tickerParam = searchParams.get('tickers') || ''
  const tickers = tickerParam.split(',').filter(Boolean)

  // Only treat as "already active" if actively streaming for THIS ticker set
  const currentTickerKey = tickers.map((t) => t.toUpperCase()).sort().join(',')
  const storeTickerKey = Object.keys(analyses).sort().join(',')
  const alreadyActive = isStreaming && storeTickerKey === currentTickerKey

  useEffect(() => {
    if (!confirmed && !alreadyActive) return
    if (hasConnectedRef.current) return
    const tickerList = tickerParam.split(',').filter(Boolean)
    if (tickerList.length > 0) {
      hasConnectedRef.current = true
      connect(tickerList)
      document.title = `Analyzing ${tickerList.join(', ')}... | AI Investment Analyst`
    }
    return () => {
      disconnect()
      hasConnectedRef.current = false
      document.title = 'AI Investment Analyst'
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tickerParam, confirmed])

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

  // Pre-flight confirmation screen
  if (!confirmed && !alreadyActive) {
    return (
      <div className="max-w-lg mx-auto px-6 py-16">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-8">
          <h2 className="text-lg font-semibold text-[var(--text-primary)] mb-4">
            Ready to analyze
          </h2>
          <div className="space-y-3 mb-6">
            <div className="flex flex-wrap gap-2">
              {tickers.map((t) => (
                <span
                  key={t}
                  className="font-mono text-sm px-3 py-1 rounded-full bg-[var(--accent-bg)] text-[var(--accent)] font-medium"
                >
                  {t.toUpperCase()}
                </span>
              ))}
            </div>
            <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
              <Clock className="w-4 h-4" />
              <span>~2 minutes per ticker (multi-agent debate)</span>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => setConfirmed(true)}
              className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-[var(--accent)] text-white text-sm font-medium hover:bg-[var(--accent)]/90 transition-colors focus-ring"
            >
              <Play className="w-4 h-4" />
              Start Analysis
            </button>
            <Link
              to="/"
              className="text-sm text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
            >
              Back to watchlist
            </Link>
          </div>
        </div>
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
        <InvestmentDisclaimer />
      </div>

      {/* Progress bar (visible while streaming) */}
      {isStreaming && <ProgressBar events={events} />}

      {/* Main layout: trace left, cards right */}
      <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-6">
        {/* Trace panel: collapsible on mobile to save viewport space */}
        <MobileCollapsibleTrace />

        {/* Analysis cards (progressive) */}
        <div className="space-y-6">
          {/* Debate panels (render during active debate before analysis completes) */}
          {tickers.map((t) => {
            const ticker = t.toUpperCase()
            if (debates[ticker] && debates[ticker].turns.length > 0) {
              return <DebatePanel key={`debate-${ticker}`} ticker={ticker} />
            }
            return null
          })}

          {Object.entries(analyses).map(([ticker, analysis]) => (
            <StreamAnalysisCard
              key={ticker}
              analysis={analysis}
              onCitationClick={setActiveCitation}
            />
          ))}

          {/* Sector peers (single-ticker analyses only) */}
          {peerComparison && <SectorPeersCard peerComparison={peerComparison} />}

          {/* Skeleton cards for pending tickers */}
          {tickers
            .filter((t) => !analyses[t.toUpperCase()])
            .map((ticker) => (
              <SkeletonCard key={ticker} ticker={ticker.toUpperCase()} />
            ))}

          {/* Error state */}
          {error && (
            <div className="rounded-xl border border-[var(--error)]/20 bg-[var(--error-bg)] p-5">
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-[var(--error)] mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-[var(--error)]">Analysis failed</p>
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

          {/* Next steps CTAs (shown after analysis completes) */}
          {!isStreaming && Object.keys(analyses).length > 0 && (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
              <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-3">Next Steps</p>
              <div className="flex flex-wrap gap-2">
                {tickers.length >= 2 && (
                  <Link to={`/compare?tickers=${tickers.join(',')}`} className="text-xs px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--accent)] hover:border-[var(--accent)] transition-colors focus-ring">
                    Compare these stocks
                  </Link>
                )}
                <Link to="/dashboard" className="text-xs px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--accent)] hover:border-[var(--accent)] transition-colors focus-ring">
                  View in History
                </Link>
                <Link to="/chat" className="text-xs px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--accent)] hover:border-[var(--accent)] transition-colors focus-ring">
                  Ask about this analysis
                </Link>
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

// Phase definitions for the progress bar, ordered by pipeline sequence.
// Progress caps at 95% until run_completed arrives.
const PHASES = [
  { node: 'router', label: 'Routing analysis...', progress: 5 },
  { node: 'fetch_data', label: 'Gathering market data...', progress: 20 },
  { node: 'analyze', label: 'Analyzing fundamentals...', progress: 45 },
  { node: 'debate', label: 'Running investment debate...', progress: 70 },
  { node: 'report', label: 'Synthesizing report...', progress: 90 },
] as const

function ProgressBar({ events }: { events: StreamEvent[] }) {
  const [startTime] = useState(() => Date.now())
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const interval = setInterval(() => setElapsed(Date.now() - startTime), 1000)
    return () => clearInterval(interval)
  }, [startTime])

  // Determine current phase from the most recent node_started event
  const currentPhase = useMemo(() => {
    for (let i = events.length - 1; i >= 0; i--) {
      const ev = events[i]
      if (ev.type === 'node_started' && ev.node) {
        const match = PHASES.find((p) => p.node === ev.node)
        if (match) return match
      }
    }
    return { node: '', label: 'Starting analysis...', progress: 2 }
  }, [events])

  const minutes = Math.floor(elapsed / 60000)
  const seconds = Math.floor((elapsed % 60000) / 1000)
  const timeStr = `${minutes}:${seconds.toString().padStart(2, '0')}`

  return (
    <div className="mb-6">
      <div className="flex items-center justify-between mb-1.5">
        <p className="text-sm text-[var(--text-secondary)]">{currentPhase.label}</p>
        <span className="text-xs text-[var(--text-muted)] font-mono">{timeStr}</span>
      </div>
      <div className="h-[2px] w-full rounded-full bg-[var(--surface)] overflow-hidden">
        <div
          className="h-full rounded-full progress-bar-fill"
          style={{ width: `${currentPhase.progress}%` }}
        />
      </div>
      <style>{`
        .progress-bar-fill {
          background-color: var(--accent);
          transition: width 1s ease-out;
        }
        @media (prefers-reduced-motion: reduce) {
          .progress-bar-fill {
            transition: none;
          }
        }
      `}</style>
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
          {analysis.earnings?.next_earnings_date && (
            <p className="text-xs text-[var(--text-muted)] mt-1">
              Next earnings: {analysis.earnings.next_earnings_date}
              {typeof analysis.earnings.days_until_earnings === 'number' &&
                ` (${analysis.earnings.days_until_earnings} days)`}
            </p>
          )}
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
          <div className="flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-amber-500 mt-0.5 shrink-0" />
            <div>
              <p className="text-xs font-medium text-[var(--text-secondary)]">
                Based on partial data
              </p>
              <p className="text-xs text-[var(--text-muted)] mt-0.5">
                Unavailable: {analysis.data_gaps.join(', ')}
              </p>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                Try again during US market hours for better coverage.
              </p>
            </div>
          </div>
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

function SectorPeersCard({ peerComparison }: { peerComparison: PeerComparisonPayload }) {
  if (peerComparison.peers.length === 0) return null

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5 animate-fade-in">
      <div className="flex items-center gap-2 mb-3">
        <Layers className="w-4 h-4 text-[var(--text-muted)]" />
        <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
          Sector Peers &middot; {peerComparison.sector}
        </h3>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {peerComparison.peers.map((peer) => (
          <Link
            key={peer.ticker}
            to={`/analyze?tickers=${peer.ticker}`}
            className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5 hover:border-[var(--accent)] transition-colors focus-ring"
          >
            <div>
              <span className="font-mono text-sm font-semibold text-[var(--text-primary)]">
                {peer.ticker}
              </span>
              {peer.current_price != null && (
                <span className="ml-2 text-xs font-mono text-[var(--text-muted)]">
                  ${peer.current_price.toFixed(2)}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {peer.signal ? (
                <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-[var(--accent-bg)] text-[var(--accent)] capitalize">
                  {peer.signal}
                </span>
              ) : (
                <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--surface)] text-[var(--text-muted)]">
                  Fundamentals only
                </span>
              )}
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}

function MobileCollapsibleTrace() {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <div className="lg:sticky lg:top-6 lg:self-start">
      {/* Mobile toggle (hidden on desktop where trace is always visible) */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="lg:hidden w-full flex items-center justify-between px-4 py-3 mb-2 rounded-lg bg-[var(--surface-elevated)] border border-[var(--border)] text-sm font-medium text-[var(--text-secondary)] focus-ring"
        aria-expanded={!collapsed}
        aria-controls="trace-panel-content"
      >
        <span>Agent Trace</span>
        <ChevronDown className={`w-4 h-4 transition-transform ${collapsed ? '' : 'rotate-180'}`} />
      </button>
      <div
        id="trace-panel-content"
        className={collapsed ? 'hidden lg:block' : ''}
      >
        <AgentTracePanel />
      </div>
    </div>
  )
}

function SkeletonCard({ ticker }: { ticker: string }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-6 skeleton-delayed">
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
