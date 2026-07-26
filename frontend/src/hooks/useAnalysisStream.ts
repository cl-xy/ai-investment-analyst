import { useCallback, useRef } from 'react'
import { useAnalysisStore } from '../stores/analysisStore'
import type {
  AnalysisCompletePayload,
  RunCompletedPayload,
  StreamEvent,
} from '../types/stream'

const API_BASE = import.meta.env.VITE_API_URL || ''
const MAX_RETRY_DELAY = 30_000
const INITIAL_RETRY_DELAY = 1_000

/**
 * Hook for managing SSE connection to the analysis streaming endpoint.
 * Handles reconnection with exponential backoff and progressive event dispatch.
 */
export function useAnalysisStream() {
  const eventSourceRef = useRef<EventSource | null>(null)
  const retryCountRef = useRef(0)
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { startStream, addEvent, setAnalysis, setComplete, setError, reset } =
    useAnalysisStore()

  const disconnect = useCallback(() => {
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [])

  const connect = useCallback(
    (tickers: string[], isRetry = false) => {
      disconnect()
      if (!isRetry) {
        // Only reset on user-initiated connections, not retries
        reset()
        retryCountRef.current = 0
      }

      const tickerParam = tickers.map((t) => t.trim().toUpperCase()).join(',')
      const url = `${API_BASE}/api/analyze/stream?tickers=${encodeURIComponent(tickerParam)}`

      const es = new EventSource(url)
      eventSourceRef.current = es

      const handleEvent = (e: MessageEvent) => {
        try {
          const event: StreamEvent = JSON.parse(e.data)

          // First event initializes the stream
          if (event.type === 'run_started') {
            startStream(event.run_id)
          }

          addEvent(event)

          // Progressive analysis delivery
          if (event.type === 'analysis_complete') {
            const payload = event.payload as unknown as AnalysisCompletePayload
            setAnalysis(payload.ticker, payload.analysis)
          }

          // Stream complete
          if (event.type === 'run_completed') {
            const payload = event.payload as unknown as RunCompletedPayload
            setComplete(payload)
            disconnect()
          }

          // Error handling
          if (event.type === 'error') {
            const msg = (event.payload as { message?: string }).message || 'Unknown error'
            const recoverable = (event.payload as { recoverable?: boolean }).recoverable
            if (!recoverable) {
              setError(msg)
              disconnect()
            }
          }
        } catch {
          // Ignore malformed events (e.g. heartbeats with no parseable data)
        }
      }

      // Listen to all domain event types
      const eventTypes = [
        'run_started',
        'node_started',
        'node_completed',
        'tool_call',
        'tool_result',
        'llm_token',
        'citation',
        'warning',
        'error',
        'analysis_complete',
        'run_completed',
        'heartbeat',
      ]
      for (const type of eventTypes) {
        es.addEventListener(type, handleEvent)
      }

      es.onerror = () => {
        // EventSource auto-reconnects, but we handle backoff ourselves
        if (es.readyState === EventSource.CLOSED) {
          const delay = Math.min(
            INITIAL_RETRY_DELAY * 2 ** retryCountRef.current,
            MAX_RETRY_DELAY,
          )
          retryCountRef.current += 1

          if (retryCountRef.current <= 5) {
            retryTimeoutRef.current = setTimeout(() => connect(tickers, true), delay)
          } else {
            setError('Connection lost. Please try again.')
          }
        }
      }
    },
    [disconnect, reset, startStream, addEvent, setAnalysis, setComplete, setError],
  )

  return { connect, disconnect }
}
