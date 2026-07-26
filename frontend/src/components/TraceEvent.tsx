import type { StreamEvent, ToolResultPayload } from '../types/stream'
import {
  CheckCircle2,
  XCircle,
  Circle,
  Loader2,
  Database,
  Zap,
  AlertTriangle,
} from 'lucide-react'

interface TraceEventProps {
  event: StreamEvent
  isActive: boolean
}

/**
 * Single row in the agent trace timeline.
 * Renders differently based on event type with appropriate status indicators.
 */
export function TraceEvent({ event, isActive }: TraceEventProps) {
  switch (event.type) {
    case 'node_started':
      return <NodeEvent event={event} isActive={isActive} />
    case 'node_completed':
      return <NodeCompleteEvent event={event} />
    case 'tool_call':
      return <ToolCallEvent event={event} />
    case 'tool_result':
      return <ToolResultEvent event={event} />
    case 'analysis_complete':
      return <AnalysisEvent event={event} />
    case 'error':
      return <ErrorEvent event={event} />
    case 'warning':
      return <WarningEvent event={event} />
    case 'run_completed':
      return null // Handled in footer
    default:
      return null
  }
}

function NodeEvent({ event, isActive }: { event: StreamEvent; isActive: boolean }) {
  const name = formatNodeName(event.node || '')
  return (
    <div className="flex items-center gap-2 py-1.5">
      {isActive ? (
        <Loader2 className="w-3.5 h-3.5 text-[var(--accent)] animate-spin" />
      ) : (
        <Circle className="w-3.5 h-3.5 text-[var(--text-muted)]" />
      )}
      <span className="text-sm font-medium text-[var(--text-primary)]">{name}</span>
      {isActive && (
        <span className="text-xs text-[var(--text-muted)]">running...</span>
      )}
    </div>
  )
}

function NodeCompleteEvent({ event }: { event: StreamEvent }) {
  const name = formatNodeName((event.payload as { node_name?: string }).node_name || '')
  const durationMs = (event.payload as { duration_ms?: number }).duration_ms
  return (
    <div className="flex items-center gap-2 py-1.5">
      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
      <span className="text-sm text-[var(--text-secondary)]">{name}</span>
      {durationMs != null && (
        <span className="text-xs font-mono text-[var(--text-muted)] ml-auto">
          {durationMs < 1000 ? `${durationMs}ms` : `${(durationMs / 1000).toFixed(1)}s`}
        </span>
      )}
    </div>
  )
}

function ToolCallEvent({ event }: { event: StreamEvent }) {
  const toolName = (event.payload as { tool_name?: string }).tool_name || event.tool || ''
  return (
    <div className="flex items-center gap-2 py-1 pl-6">
      <Zap className="w-3 h-3 text-[var(--text-muted)]" />
      <span className="text-xs text-[var(--text-muted)] font-mono">{toolName}</span>
    </div>
  )
}

function ToolResultEvent({ event }: { event: StreamEvent }) {
  const payload = event.payload as unknown as ToolResultPayload
  const success = payload.success
  const cached = payload.cached

  return (
    <div className="flex items-center gap-2 py-1 pl-6">
      {success ? (
        <CheckCircle2 className="w-3 h-3 text-emerald-500" />
      ) : (
        <XCircle className="w-3 h-3 text-red-500" />
      )}
      <span className="text-xs font-mono text-[var(--text-secondary)]">
        {payload.tool_name}
      </span>
      {cached && (
        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-500">
          cached
        </span>
      )}
      {!cached && success && (
        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-500">
          live
        </span>
      )}
      {payload.duration_ms > 0 && (
        <span className="text-xs font-mono text-[var(--text-muted)] ml-auto">
          {payload.duration_ms}ms
        </span>
      )}
    </div>
  )
}

function AnalysisEvent({ event }: { event: StreamEvent }) {
  const ticker = (event.payload as { ticker?: string }).ticker || ''
  return (
    <div className="flex items-center gap-2 py-1.5">
      <Database className="w-3.5 h-3.5 text-[var(--accent)]" />
      <span className="text-sm font-medium text-[var(--text-primary)]">
        Analysis ready: {ticker}
      </span>
    </div>
  )
}

function ErrorEvent({ event }: { event: StreamEvent }) {
  const message = (event.payload as { message?: string }).message || 'Unknown error'
  return (
    <div className="flex items-center gap-2 py-1.5">
      <XCircle className="w-3.5 h-3.5 text-red-500" />
      <span className="text-sm text-red-500">{message}</span>
    </div>
  )
}

function WarningEvent({ event }: { event: StreamEvent }) {
  const message = (event.payload as { message?: string }).message || ''
  return (
    <div className="flex items-center gap-2 py-1.5">
      <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
      <span className="text-sm text-amber-500">{message}</span>
    </div>
  )
}

function formatNodeName(name: string): string {
  const names: Record<string, string> = {
    router: 'Router',
    fetch_data: 'Fetch Data',
    analyze_ticker: 'Analyze',
    generate_report: 'Generate Report',
    chat: 'Chat',
    portfolio_ops: 'Portfolio',
  }
  return names[name] || name
}
