import { useEffect, useRef } from 'react'
import { X, Database, Clock, CheckCircle2 } from 'lucide-react'
import type { Citation, StreamEvent, ToolResultPayload } from '../types/stream'

interface EvidenceDrawerProps {
  citation: Citation | null
  toolResults: StreamEvent[]
  onClose: () => void
}

export default function EvidenceDrawer({ citation, toolResults, onClose }: EvidenceDrawerProps) {
  const drawerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [onClose])

  if (!citation) return null

  // Find matching tool result by source_id or provider
  const matchingResult = toolResults.find((ev) => {
    const payload = ev.payload as unknown as ToolResultPayload
    return payload.source_id === citation.source_id || ev.tool === citation.provider
  })

  const payload = matchingResult?.payload as unknown as ToolResultPayload | undefined

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40 transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer */}
      <div
        ref={drawerRef}
        className="fixed right-0 top-0 bottom-0 w-full max-w-md bg-[var(--surface-elevated)] border-l border-[var(--border)] z-50 overflow-y-auto shadow-xl animate-slide-in-right"
        role="dialog"
        aria-label="Evidence details"
        aria-modal="true"
      >
        {/* Header */}
        <div className="sticky top-0 bg-[var(--surface-elevated)] border-b border-[var(--border)] px-5 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-[var(--accent)]" />
            <span className="text-sm font-medium text-[var(--text-primary)]">Evidence</span>
          </div>
          <button
            onClick={onClose}
            className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors focus-ring rounded p-1"
            aria-label="Close evidence drawer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="px-5 py-4 space-y-5">
          {/* Claim */}
          <div>
            <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
              Claim
            </h3>
            <p className="text-sm text-[var(--text-primary)] leading-relaxed">
              {citation.claim}
            </p>
          </div>

          {/* Provider */}
          <div>
            <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
              Data Source
            </h3>
            <div className="flex items-center gap-2">
              <span className="text-sm font-mono px-2 py-1 rounded bg-[var(--surface)] border border-[var(--border)] text-[var(--text-secondary)]">
                {citation.provider}
              </span>
              <span className="text-xs text-[var(--text-muted)]">
                {citation.source_id}
              </span>
            </div>
          </div>

          {/* Tool result metadata */}
          {payload && (
            <div>
              <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
                Retrieval Details
              </h3>
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                  <span className="text-[var(--text-secondary)]">
                    {payload.success ? 'Successfully retrieved' : 'Retrieval failed'}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <Clock className="w-3.5 h-3.5 text-[var(--text-muted)]" />
                  <span className="text-[var(--text-secondary)]">
                    {payload.duration_ms}ms latency
                  </span>
                </div>
                {payload.cached && (
                  <span className="inline-flex text-xs font-medium px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-500">
                    Served from cache
                  </span>
                )}
                {!payload.cached && (
                  <span className="inline-flex text-xs font-medium px-2 py-0.5 rounded bg-blue-500/10 text-blue-500">
                    Live API call
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Raw payload */}
          {matchingResult && (
            <div>
              <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
                Raw Tool Output
              </h3>
              <pre className="p-3 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-[10px] font-mono text-[var(--text-muted)] overflow-x-auto max-h-60 overflow-y-auto">
                {JSON.stringify(matchingResult.payload, null, 2)}
              </pre>
            </div>
          )}

          {!matchingResult && (
            <div className="rounded-lg bg-[var(--surface)] border border-[var(--border)] p-4 text-center">
              <p className="text-sm text-[var(--text-muted)]">
                Raw tool output not available for this citation.
              </p>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
