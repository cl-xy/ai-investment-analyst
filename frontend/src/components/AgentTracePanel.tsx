import { useAnalysisStore } from '../stores/analysisStore'
import { TraceEvent } from './TraceEvent'
import { Activity, CheckCircle2, XCircle, Clock, Copy, Check } from 'lucide-react'
import { useState, useCallback } from 'react'

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

      {/* Correlation ID badge */}
      {runMeta?.correlationId && (
        <div className="px-5 py-2 border-b border-[var(--border)]">
          <CorrelationIdBadge correlationId={runMeta.correlationId} />
        </div>
      )}

      {/* Accessible status summary - announces milestones only, not every event */}
      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {isComplete ? 'Analysis complete' : hasError ? 'Analysis failed' : isStreaming ? `Agent running: ${currentNode || 'initializing'}` : ''}
      </p>

      {/* Timeline */}
      <div className="px-5 py-4 space-y-1 max-h-[600px] overflow-y-auto" role="log" aria-label="Agent execution trace" aria-live="off">
        {traceEvents.length === 0 && isStreaming && (
          <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
            <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse" />
            Initializing agent...
          </div>
        )}

        {traceEvents.map((event, index) => (
          <div
            key={event.seq}
            className="trace-event-enter"
            style={{ animationDelay: `${index * 30}ms` }}
          >
            <TraceEvent
              event={event}
              isActive={event.type === 'node_started' && event.node === currentNode}
            />
          </div>
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

function CorrelationIdBadge({ correlationId }: { correlationId: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(correlationId).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }, [correlationId])

  return (
    <button
      onClick={handleCopy}
      className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-[var(--surface)] border border-[var(--border)] hover:border-[var(--accent)] transition-colors cursor-pointer"
      title="Click to copy correlation ID"
      aria-label={`Copy correlation ID: ${correlationId}`}
    >
      <span className="text-[10px] font-mono text-[var(--text-muted)] select-all">
        {correlationId}
      </span>
      {copied ? (
        <Check className="w-3 h-3 text-emerald-500 shrink-0" />
      ) : (
        <Copy className="w-3 h-3 text-[var(--text-muted)] shrink-0" />
      )}
    </button>
  )
}
