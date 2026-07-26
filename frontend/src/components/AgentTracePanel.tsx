import { useAnalysisStore } from '../stores/analysisStore'
import { TraceEvent } from './TraceEvent'
import { Activity, CheckCircle2, XCircle, Clock } from 'lucide-react'

/**
 * Real-time agent execution trace panel.
 * Shows a vertical timeline of node/tool events with status indicators,
 * latency, and cache hit/miss badges.
 */
export default function AgentTracePanel() {
  const { events, currentNode, isStreaming, runMeta } = useAnalysisStore()

  // Filter to meaningful events (skip heartbeats and raw llm_tokens for the timeline)
  const traceEvents = events.filter(
    (e) =>
      e.type !== 'heartbeat' &&
      e.type !== 'llm_token' &&
      e.type !== 'run_started',
  )

  const isComplete = !isStreaming && events.some((e) => e.type === 'run_completed')
  const hasError = events.some(
    (e) => e.type === 'error' && !(e.payload as { recoverable?: boolean }).recoverable,
  )

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-[var(--border)]">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-[var(--accent)]" />
          <span className="text-sm font-medium text-[var(--text-primary)]">
            Agent Trace
          </span>
        </div>
        <StatusBadge
          isStreaming={isStreaming}
          isComplete={isComplete}
          hasError={hasError}
        />
      </div>

      {/* Timeline */}
      <div className="px-5 py-4 space-y-1 max-h-[600px] overflow-y-auto">
        {traceEvents.length === 0 && isStreaming && (
          <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
            <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse" />
            Initializing agent...
          </div>
        )}

        {traceEvents.map((event) => (
          <TraceEvent
            key={event.seq}
            event={event}
            isActive={event.type === 'node_started' && event.node === currentNode}
          />
        ))}
      </div>

      {/* Footer: run metadata */}
      {runMeta && (isComplete || hasError) && (
        <div className="px-5 py-3 border-t border-[var(--border)] flex items-center gap-4 text-xs text-[var(--text-muted)]">
          {runMeta.totalDurationMs != null && (
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {(runMeta.totalDurationMs / 1000).toFixed(1)}s
            </span>
          )}
          {runMeta.totalTokens != null && runMeta.totalTokens > 0 && (
            <span>{runMeta.totalTokens.toLocaleString()} tokens</span>
          )}
          {runMeta.costUsd != null && runMeta.costUsd > 0 && (
            <span>${runMeta.costUsd.toFixed(4)}</span>
          )}
        </div>
      )}
    </div>
  )
}

function StatusBadge({
  isStreaming,
  isComplete,
  hasError,
}: {
  isStreaming: boolean
  isComplete: boolean
  hasError: boolean
}) {
  if (hasError) {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-red-500/10 text-red-500">
        <XCircle className="w-3 h-3" />
        Failed
      </span>
    )
  }
  if (isComplete) {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-500">
        <CheckCircle2 className="w-3 h-3" />
        Complete
      </span>
    )
  }
  if (isStreaming) {
    return (
      <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-[var(--accent)]/10 text-[var(--accent)]">
        <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse" />
        Streaming
      </span>
    )
  }
  return null
}
