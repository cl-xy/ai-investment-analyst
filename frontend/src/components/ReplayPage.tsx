import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTraceReplay, type ReplaySpeed } from '../hooks/useTraceReplay'
import { useAnalysisStore } from '../stores/analysisStore'
import { API_BASE, authHeaders } from '../api/config'
import AgentTracePanel from './AgentTracePanel'
import DebatePanel from './DebatePanel'
import type { AnalysisOutput, PeerComparisonPayload, StreamEvent } from '../types/stream'
import {
  Play,
  Pause,
  SkipForward,
  SkipBack,
  Zap,
  Clock,
  Activity,
  AlertCircle,
  Search,
  Star,
  ChevronRight,
} from 'lucide-react'

interface TraceSummary {
  id: string
  run_id: string
  tickers: string[]
  duration_ms: number
  status: string
  signal: string | null
  created_at: string
  is_featured: boolean
}

interface TraceDetail {
  id: string
  run_id: string
  tickers: string[]
  events: StreamEvent[]
  duration_ms: number
  status: string
  signal: string | null
  created_at: string
}

/**
 * Trace replay page. Lets users step through previously recorded analyses
 * like a debugger, reusing existing trace/analysis rendering components.
 */
export default function ReplayPage() {
  const [traces, setTraces] = useState<TraceSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filterTicker, setFilterTicker] = useState('')
  const [activeTrace, setActiveTrace] = useState<TraceDetail | null>(null)
  const [loadingTrace, setLoadingTrace] = useState(false)

  const replay = useTraceReplay()
  const { analyses, debates, peerComparison } = useAnalysisStore()

  // Fetch trace list
  const fetchTraces = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (filterTicker.trim()) {
        params.set('ticker', filterTicker.trim().toUpperCase())
      }
      const url = `${API_BASE}/api/replay/traces?${params.toString()}`
      const res = await fetch(url, { headers: authHeaders() })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      setTraces(data.traces || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load traces')
    } finally {
      setLoading(false)
    }
  }, [filterTicker])

  useEffect(() => {
    fetchTraces()
  }, [fetchTraces])

  // Load a specific trace
  const loadTrace = useCallback(async (traceId: string) => {
    setLoadingTrace(true)
    setError(null)
    try {
      const url = `${API_BASE}/api/replay/${traceId}`
      const res = await fetch(url, { headers: authHeaders() })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: TraceDetail = await res.json()
      setActiveTrace(data)
      replay.loadTrace(data.events)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load trace')
    } finally {
      setLoadingTrace(false)
    }
  }, [replay])

  // Load featured trace (instant mode)
  const loadFeatured = useCallback(async () => {
    setLoadingTrace(true)
    setError(null)
    try {
      const url = `${API_BASE}/api/replay/featured`
      const res = await fetch(url, { headers: authHeaders() })
      if (!res.ok) {
        if (res.status === 404) {
          setError('No featured trace available yet. Run an analysis first.')
          setLoadingTrace(false)
          return
        }
        throw new Error(`HTTP ${res.status}`)
      }
      const data: TraceDetail = await res.json()
      setActiveTrace(data)
      replay.loadInstant(data.events)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load featured trace')
    } finally {
      setLoadingTrace(false)
    }
  }, [replay])

  // Back to trace list
  const exitReplay = useCallback(() => {
    replay.pause()
    setActiveTrace(null)
    replay.loadTrace([])
  }, [replay])

  // Active replay view
  if (activeTrace) {
    return (
      <div className="max-w-7xl mx-auto px-6 py-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <button
              onClick={exitReplay}
              className="text-sm text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors mb-2 focus-ring rounded"
            >
              &larr; Back to traces
            </button>
            <h1 className="text-xl font-semibold text-[var(--text-primary)]">
              Replaying {activeTrace.tickers.join(', ')}
            </h1>
            <p className="text-sm text-[var(--text-muted)] mt-1">
              {new Date(activeTrace.created_at).toLocaleDateString()} &middot;{' '}
              {(activeTrace.duration_ms / 1000).toFixed(1)}s original duration
            </p>
          </div>
          <StatusPill status={activeTrace.status} signal={activeTrace.signal} />
        </div>

        {/* Replay controls */}
        <ReplayControls
          isPlaying={replay.isPlaying}
          position={replay.position}
          totalEvents={replay.totalEvents}
          speed={replay.speed}
          isComplete={replay.isComplete}
          onPlay={replay.play}
          onPause={replay.pause}
          onStepForward={replay.stepForward}
          onStepBackward={replay.stepBackward}
          onSeek={replay.seekTo}
          onSpeedChange={replay.setSpeed}
        />

        {/* Main layout (mirrors StreamingAnalysisPage) */}
        <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-6 mt-6">
          <div className="lg:sticky lg:top-6 lg:self-start">
            <AgentTracePanel />
          </div>

          <div className="space-y-6">
            {/* Debate panels */}
            {activeTrace.tickers.map((t) => {
              const ticker = t.toUpperCase()
              if (debates[ticker] && debates[ticker].turns.length > 0) {
                return <DebatePanel key={`debate-${ticker}`} ticker={ticker} />
              }
              return null
            })}

            {/* Analysis cards */}
            {Object.entries(analyses).map(([ticker, analysis]) => (
              <ReplayAnalysisCard key={ticker} analysis={analysis} />
            ))}

            {/* Sector peers */}
            {peerComparison && <ReplaySectorPeers peerComparison={peerComparison} />}

            {/* Timeline visualization */}
            <TimelineView events={replay.events} position={replay.position} onSeek={replay.seekTo} />
          </div>
        </div>
      </div>
    )
  }

  // Trace list view
  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Trace Replay</h1>
        <p className="text-sm text-[var(--text-muted)] mt-1">
          Step through recorded analyses like a debugger. No LLM calls needed.
        </p>
      </div>

      {/* Featured demo button */}
      <button
        onClick={loadFeatured}
        disabled={loadingTrace}
        className="w-full mb-6 rounded-xl border-2 border-dashed border-[var(--accent)]/30 bg-[var(--accent)]/5 p-5 flex items-center gap-4 hover:border-[var(--accent)]/60 transition-colors focus-ring"
      >
        <div className="w-10 h-10 rounded-lg bg-[var(--accent)]/10 flex items-center justify-center shrink-0">
          <Zap className="w-5 h-5 text-[var(--accent)]" />
        </div>
        <div className="text-left flex-1">
          <p className="text-sm font-medium text-[var(--accent)]">Featured Demo</p>
          <p className="text-xs text-[var(--text-muted)] mt-0.5">
            Pre-cached NVDA analysis. Loads instantly, shows the full pipeline.
          </p>
        </div>
        <ChevronRight className="w-5 h-5 text-[var(--accent)]" />
      </button>

      {/* Filter */}
      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
        <input
          type="text"
          placeholder="Filter by ticker..."
          value={filterTicker}
          onChange={(e) => setFilterTicker(e.target.value)}
          className="w-full pl-9 pr-4 py-2.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus-ring"
        />
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-4 mb-4 flex items-center gap-3">
          <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
          <p className="text-sm text-red-500">{error}</p>
          <button onClick={() => setError(null)} className="ml-auto text-xs text-red-500 underline">
            dismiss
          </button>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="w-5 h-5 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
        </div>
      )}

      {/* Trace list */}
      {!loading && traces.length === 0 && (
        <div className="text-center py-12">
          <Activity className="w-8 h-8 text-[var(--text-muted)] mx-auto mb-3" />
          <p className="text-sm text-[var(--text-muted)]">
            No traces recorded yet. Run an analysis to capture a trace.
          </p>
          <Link
            to="/"
            className="inline-block mt-4 text-sm text-[var(--accent)] hover:underline focus-ring rounded"
          >
            Go to Analyze
          </Link>
        </div>
      )}

      {!loading && traces.length > 0 && (
        <div className="space-y-2">
          {traces.map((trace) => (
            <button
              key={trace.id}
              onClick={() => loadTrace(trace.id)}
              disabled={loadingTrace}
              className="w-full text-left rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] p-4 hover:border-[var(--accent)] transition-colors focus-ring flex items-center gap-4"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  {trace.is_featured && <Star className="w-3.5 h-3.5 text-amber-500" />}
                  <span className="font-mono text-sm font-semibold text-[var(--text-primary)]">
                    {trace.tickers.join(', ')}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-1 text-xs text-[var(--text-muted)]">
                  <span>{new Date(trace.created_at).toLocaleDateString()}</span>
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {(trace.duration_ms / 1000).toFixed(1)}s
                  </span>
                </div>
              </div>
              <StatusPill status={trace.status} signal={trace.signal} />
              <ChevronRight className="w-4 h-4 text-[var(--text-muted)]" />
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function ReplayControls({
  isPlaying,
  position,
  totalEvents,
  speed,
  isComplete,
  onPlay,
  onPause,
  onStepForward,
  onStepBackward,
  onSeek,
  onSpeedChange,
}: {
  isPlaying: boolean
  position: number
  totalEvents: number
  speed: ReplaySpeed
  isComplete: boolean
  onPlay: () => void
  onPause: () => void
  onStepForward: () => void
  onStepBackward: () => void
  onSeek: (pos: number) => void
  onSpeedChange: (speed: ReplaySpeed) => void
}) {
  const progress = totalEvents > 0 ? (position / totalEvents) * 100 : 0

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-4">
      <div className="flex items-center gap-4">
        {/* Transport controls */}
        <div className="flex items-center gap-1">
          <button
            onClick={onStepBackward}
            disabled={position <= 0}
            className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-[var(--surface)] transition-colors disabled:opacity-30 focus-ring"
            aria-label="Step backward"
          >
            <SkipBack className="w-4 h-4 text-[var(--text-secondary)]" />
          </button>

          <button
            onClick={isPlaying ? onPause : onPlay}
            disabled={isComplete}
            className="w-10 h-10 rounded-lg flex items-center justify-center bg-[var(--accent)] text-white hover:bg-[var(--accent)]/90 transition-colors disabled:opacity-50 focus-ring"
            aria-label={isPlaying ? 'Pause' : 'Play'}
          >
            {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
          </button>

          <button
            onClick={onStepForward}
            disabled={position >= totalEvents}
            className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-[var(--surface)] transition-colors disabled:opacity-30 focus-ring"
            aria-label="Step forward"
          >
            <SkipForward className="w-4 h-4 text-[var(--text-secondary)]" />
          </button>
        </div>

        {/* Progress bar */}
        <div className="flex-1">
          <input
            type="range"
            min={0}
            max={totalEvents}
            value={position}
            onChange={(e) => onSeek(Number(e.target.value))}
            className="w-full h-1.5 rounded-full appearance-none bg-[var(--surface)] cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-[var(--accent)]"
            aria-label="Replay position"
          />
          <div className="flex justify-between text-[10px] text-[var(--text-muted)] mt-1">
            <span>Event {position} / {totalEvents}</span>
            <span>{progress.toFixed(0)}%</span>
          </div>
        </div>

        {/* Speed selector */}
        <div className="flex items-center gap-1">
          {(['1x', '2x', '4x', 'instant'] as ReplaySpeed[]).map((s) => (
            <button
              key={s}
              onClick={() => onSpeedChange(s)}
              className={[
                'text-xs font-medium px-2 py-1 rounded transition-colors focus-ring',
                speed === s
                  ? 'bg-[var(--accent)] text-white'
                  : 'text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--surface)]',
              ].join(' ')}
            >
              {s === 'instant' ? <Zap className="w-3 h-3 inline" /> : s}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function TimelineView({
  events,
  position,
  onSeek,
}: {
  events: StreamEvent[]
  position: number
  onSeek: (pos: number) => void
}) {
  if (events.length === 0) return null

  // Group events by node for timeline visualization
  const nodeGroups: { node: string; startIdx: number; endIdx: number; durationMs: number }[] = []
  let currentNode: string | null = null
  let nodeStart = 0

  for (let i = 0; i < events.length; i++) {
    const e = events[i]
    if (e.type === 'node_started' && e.node) {
      if (currentNode) {
        nodeGroups.push({ node: currentNode, startIdx: nodeStart, endIdx: i - 1, durationMs: 0 })
      }
      currentNode = e.node
      nodeStart = i
    }
    if (e.type === 'node_completed' && e.node === currentNode) {
      const dur = (e.payload as { duration_ms?: number }).duration_ms || 0
      nodeGroups.push({ node: currentNode, startIdx: nodeStart, endIdx: i, durationMs: dur })
      currentNode = null
    }
  }
  if (currentNode) {
    nodeGroups.push({ node: currentNode, startIdx: nodeStart, endIdx: events.length - 1, durationMs: 0 })
  }

  const nodeColors: Record<string, string> = {
    router: 'bg-blue-500',
    fetch_data: 'bg-cyan-500',
    debate: 'bg-purple-500',
    peer_compare: 'bg-teal-500',
    generate_report: 'bg-amber-500',
    compare: 'bg-indigo-500',
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5">
      <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-3">
        Pipeline Timeline
      </h3>
      <div className="relative">
        {/* Timeline bar */}
        <div className="h-6 bg-[var(--surface)] rounded-full overflow-hidden flex">
          {nodeGroups.map((group, i) => {
            const widthPct = ((group.endIdx - group.startIdx + 1) / events.length) * 100
            const color = nodeColors[group.node] || 'bg-zinc-500'
            return (
              <button
                key={i}
                onClick={() => onSeek(group.startIdx)}
                className={`${color} opacity-60 hover:opacity-100 transition-opacity relative group`}
                style={{ width: `${Math.max(widthPct, 2)}%` }}
                title={`${group.node} (${group.durationMs ? (group.durationMs / 1000).toFixed(1) + 's' : '...'})`}
              >
                <span className="absolute inset-0 flex items-center justify-center text-[9px] font-medium text-white truncate px-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  {group.node}
                </span>
              </button>
            )
          })}
        </div>

        {/* Position indicator */}
        {events.length > 0 && (
          <div
            className="absolute top-0 w-0.5 h-6 bg-white/80 pointer-events-none"
            style={{ left: `${(position / events.length) * 100}%` }}
          />
        )}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 mt-3">
        {nodeGroups.map((group, i) => {
          const color = nodeColors[group.node] || 'bg-zinc-500'
          return (
            <div key={i} className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
              <div className={`w-2 h-2 rounded-full ${color}`} />
              <span>{group.node}</span>
              {group.durationMs > 0 && (
                <span className="text-[var(--text-muted)]">
                  ({(group.durationMs / 1000).toFixed(1)}s)
                </span>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ReplayAnalysisCard({ analysis }: { analysis: AnalysisOutput }) {
  const signalColors = {
    buy: { bg: 'bg-emerald-500/10', text: 'text-emerald-500', label: 'Buy' },
    hold: { bg: 'bg-amber-500/10', text: 'text-amber-500', label: 'Hold' },
    sell: { bg: 'bg-red-500/10', text: 'text-red-500', label: 'Sell' },
    insufficient_data: { bg: 'bg-zinc-500/10', text: 'text-zinc-400', label: 'Insufficient Data' },
  }

  const signal = signalColors[analysis.signal] || signalColors.insufficient_data

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-6 animate-fade-in">
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
                  <span className="text-red-500 shrink-0">&minus;</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Risk flags */}
      {analysis.risk_flags.length > 0 && (
        <div>
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
    </div>
  )
}

function ReplaySectorPeers({ peerComparison }: { peerComparison: PeerComparisonPayload }) {
  if (peerComparison.peers.length === 0) return null

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] p-5 animate-fade-in">
      <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-3">
        Sector Peers &middot; {peerComparison.sector}
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {peerComparison.peers.map((peer) => (
          <div
            key={peer.ticker}
            className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-2.5"
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
        ))}
      </div>
    </div>
  )
}

function StatusPill({ status, signal }: { status: string; signal: string | null }) {
  const statusConfig = {
    success: { bg: 'bg-emerald-500/10', text: 'text-emerald-500' },
    degraded: { bg: 'bg-amber-500/10', text: 'text-amber-500' },
    failed: { bg: 'bg-red-500/10', text: 'text-red-500' },
  }

  const config = statusConfig[status as keyof typeof statusConfig] || statusConfig.success

  return (
    <div className="flex items-center gap-2">
      {signal && (
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${config.bg} ${config.text} capitalize`}>
          {signal}
        </span>
      )}
      <span className={`text-xs px-2 py-0.5 rounded-full ${config.bg} ${config.text}`}>
        {status}
      </span>
    </div>
  )
}
