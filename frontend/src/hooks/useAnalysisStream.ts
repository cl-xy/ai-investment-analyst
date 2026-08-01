import { useCallback, useEffect, useRef } from 'react'
import { useAnalysisStore } from '../stores/analysisStore'
import { useSaveStatusStore } from '../stores/saveStatusStore'
import { API_BASE, authParam } from '../api/config'
import type {
  AnalysisCompletePayload,
  DebateTurnPayload,
  DebateVerdictPayload,
  PeerComparisonPayload,
  RunCompletedPayload,
  StreamEvent,
} from '../types/stream'

const INITIAL_RETRY_DELAY = 1_000

/**
 * Hook for managing SSE connection to the analysis streaming endpoint.
 * Handles reconnection with a single fixed-delay retry and progressive event dispatch.
 * Uses a generation counter to prevent stale EventSource callbacks from corrupting state.
 */
export function useAnalysisStream() {
  const eventSourceRef = useRef<EventSource | null>(null)
  const retryCountRef = useRef(0)
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const generationRef = useRef(0)
  // Track run_id and last event sequence for reconnect resume
  const runIdRef = useRef<string | null>(null)
  const lastEventIdRef = useRef<number>(0)

  const {
    startStream,
    addEvent,
    setAnalysis,
    setComplete,
    setError,
    addDebateTurn,
    setDebateVerdict,
    setPeerComparison,
    reset,
  } = useAnalysisStore()

  const { setSaving, setSaved, setFailed } = useSaveStatusStore()

  const closeTransport = useCallback(() => {
    // Close the EventSource and cancel pending retries without touching store state.
    // Used internally by connect/retry to replace the transport.
    generationRef.current += 1
    if (retryTimeoutRef.current) {
      clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [])

  const disconnect = useCallback(() => {
    // Terminal disconnect: close transport AND mark the stream as stopped in the store.
    // Called on unmount or explicit user cancel (not during connect/retry).
    closeTransport()
    const { isStreaming } = useAnalysisStore.getState()
    if (isStreaming) {
      useAnalysisStore.setState({ isStreaming: false, currentNode: null })
    }
  }, [closeTransport])

  const connect = useCallback(
    (tickers: string[], isRetry = false) => {
      closeTransport()
      // On retry with a known run_id, don't reset state (we're resuming).
      // On fresh connections, always reset.
      if (!isRetry || !runIdRef.current) {
        reset()
        runIdRef.current = null
        lastEventIdRef.current = 0
      }
      if (!isRetry) {
        retryCountRef.current = 0
      }

      // Increment generation so stale callbacks from previous connections are ignored
      const currentGeneration = ++generationRef.current

      // Snapshot tickers to prevent mutation between now and a potential retry timeout
      const normalizedTickers = tickers.map((t) => t.trim().toUpperCase())
      const tickerParam = normalizedTickers.join(',')
      const auth = authParam()
      const separator = auth ? '&' : ''
      // On retry, pass run_id and last_event_id for server-side resume/replay
      let resumeParams = ''
      if (isRetry && runIdRef.current) {
        resumeParams = `&run_id=${encodeURIComponent(runIdRef.current)}&last_event_id=${lastEventIdRef.current}`
      }
      const url = `${API_BASE}/api/analyze/stream?tickers=${encodeURIComponent(tickerParam)}${separator}${auth}${resumeParams}`

      const es = new EventSource(url)
      eventSourceRef.current = es
      setSaving()

      const handleEvent = (e: MessageEvent) => {
        // Guard: ignore events from stale connections
        if (generationRef.current !== currentGeneration) return

        // Track last event ID for reconnect resume
        if (e.lastEventId) {
          const seq = parseInt(e.lastEventId, 10)
          if (!isNaN(seq)) lastEventIdRef.current = seq
        }

        try {
          const event: StreamEvent = JSON.parse(e.data)

          // First event initializes the stream
          if (event.type === 'run_started') {
            runIdRef.current = event.run_id
            startStream(event.run_id, event.correlation_id)
          }

          addEvent(event)

          // Progressive analysis delivery
          if (event.type === 'analysis_complete') {
            const payload = event.payload as unknown as AnalysisCompletePayload
            setAnalysis(payload.ticker, payload.analysis)
          }

          // Debate events
          if (event.type === 'debate_turn') {
            const payload = event.payload as unknown as DebateTurnPayload
            addDebateTurn(payload.ticker, payload)
          }
          if (event.type === 'debate_verdict') {
            const payload = event.payload as unknown as DebateVerdictPayload
            setDebateVerdict(payload.ticker, payload)
          }

          // Auto sector-peer comparison (single-ticker analyses only)
          if (event.type === 'peer_comparison_ready') {
            const payload = event.payload as unknown as PeerComparisonPayload
            setPeerComparison(payload)
          }

          // Stream complete
          if (event.type === 'run_completed') {
            const payload = event.payload as unknown as RunCompletedPayload
            setComplete(payload)
            setSaved()
            disconnect()
          }

          // Error handling
          if (event.type === 'error') {
            const msg = (event.payload as { message?: string }).message || 'Unknown error'
            const recoverable = (event.payload as { recoverable?: boolean }).recoverable
            if (!recoverable) {
              setError(msg)
              setFailed(msg)
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
        'debate_started',
        'debate_turn',
        'debate_verdict',
        'peer_comparison_ready',
      ]
      for (const type of eventTypes) {
        es.addEventListener(type, handleEvent)
      }

      es.onerror = () => {
        // Guard: ignore errors from stale connections
        if (generationRef.current !== currentGeneration) return

        // Close explicitly to prevent native EventSource auto-reconnect
        es.close()
        if (eventSourceRef.current === es) {
          eventSourceRef.current = null
        }

        // Each reconnect starts a NEW analysis run on the backend, which wastes
        // OpenRouter rate-limit budget and causes CORS failures when Fly's proxy
        // returns errors without CORS headers. With run_id resume support, the
        // retry will replay from the last seen event instead of starting fresh.
        // Only retry once for transient network blips; after that, surface the error.
        if (retryCountRef.current < 1) {
          const delay = INITIAL_RETRY_DELAY
          retryCountRef.current += 1
          retryTimeoutRef.current = setTimeout(() => connect(normalizedTickers, true), delay)
        } else {
          setError('Connection lost. Please try again.')
          setFailed('Connection lost')
        }
      }
    },
    [
      closeTransport,
      reset,
      startStream,
      addEvent,
      setAnalysis,
      setComplete,
      setError,
      addDebateTurn,
      setDebateVerdict,
      setPeerComparison,
      setSaving,
      setSaved,
      setFailed,
    ],
  )

  // Clean up on unmount to prevent leaked connections and stale callbacks
  useEffect(() => {
    return () => disconnect()
  }, [disconnect])

  return { connect, disconnect }
}
