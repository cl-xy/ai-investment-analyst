import { useCallback, useEffect, useRef, useState } from 'react'
import { useAnalysisStore } from '../stores/analysisStore'
import type {
  AnalysisCompletePayload,
  DebateTurnPayload,
  DebateVerdictPayload,
  PeerComparisonPayload,
  RunCompletedPayload,
  StreamEvent,
} from '../types/stream'

export type ReplaySpeed = '1x' | '2x' | '4x' | 'instant'

interface ReplayState {
  isPlaying: boolean
  position: number
  totalEvents: number
  speed: ReplaySpeed
  isComplete: boolean
  events: StreamEvent[]
}

/**
 * Hook for managing trace replay state.
 * Feeds recorded events into the analysis store progressively,
 * simulating the real-time streaming experience.
 */
export function useTraceReplay() {
  const [state, setState] = useState<ReplayState>({
    isPlaying: false,
    position: 0,
    totalEvents: 0,
    speed: '1x',
    isComplete: false,
    events: [],
  })

  const eventsRef = useRef<StreamEvent[]>([])
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const positionRef = useRef(0)
  const isPlayingRef = useRef(false)
  const speedRef = useRef<ReplaySpeed>('1x')

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

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const processEvent = useCallback(
    (event: StreamEvent) => {
      if (event.type === 'run_started') {
        startStream(event.run_id)
      }

      addEvent(event)

      if (event.type === 'analysis_complete') {
        const payload = event.payload as unknown as AnalysisCompletePayload
        setAnalysis(payload.ticker, payload.analysis)
      }

      if (event.type === 'debate_turn') {
        const payload = event.payload as unknown as DebateTurnPayload
        addDebateTurn(payload.ticker, payload)
      }

      if (event.type === 'debate_verdict') {
        const payload = event.payload as unknown as DebateVerdictPayload
        setDebateVerdict(payload.ticker, payload)
      }

      if (event.type === 'peer_comparison_ready') {
        const payload = event.payload as unknown as PeerComparisonPayload
        setPeerComparison(payload)
      }

      if (event.type === 'run_completed') {
        const payload = event.payload as unknown as RunCompletedPayload
        setComplete(payload)
      }

      if (event.type === 'error') {
        const msg = (event.payload as { message?: string }).message || 'Unknown error'
        const recoverable = (event.payload as { recoverable?: boolean }).recoverable
        if (!recoverable) {
          setError(msg)
        }
      }
    },
    [startStream, addEvent, setAnalysis, setComplete, setError, addDebateTurn, setDebateVerdict, setPeerComparison],
  )

  const getDelayForSpeed = useCallback((deltaMs: number, speed: ReplaySpeed): number => {
    switch (speed) {
      case 'instant':
        return 0
      case '4x':
        return Math.min(deltaMs * 0.25, 2000)
      case '2x':
        return Math.min(deltaMs * 0.5, 3000)
      case '1x':
      default:
        return Math.min(deltaMs, 5000)
    }
  }, [])

  const playNextEvent = useCallback(() => {
    const events = eventsRef.current
    const pos = positionRef.current

    if (pos >= events.length || !isPlayingRef.current) {
      if (pos >= events.length) {
        setState((s) => ({ ...s, isPlaying: false, isComplete: true }))
        isPlayingRef.current = false
      }
      return
    }

    const event = events[pos]

    // Skip heartbeats (defensive; loadTrace already filters them)
    if (event.type === 'heartbeat') {
      positionRef.current = pos + 1
      setState((s) => ({ ...s, position: pos + 1 }))
      playNextEvent()
      return
    }

    try {
      processEvent(event)
    } catch (e) {
      // Prevent a single bad event from killing the entire timer chain
      console.error('[useTraceReplay] processEvent error:', e)
    }
    positionRef.current = pos + 1
    setState((s) => ({ ...s, position: pos + 1 }))

    // Calculate delay to next event
    if (pos + 1 < events.length) {
      const nextEvent = events[pos + 1]
      const currentTs = event.timestamp
      const nextTs = nextEvent.timestamp

      let deltaMs = 100 // default small gap
      if (currentTs && nextTs) {
        const currTime = new Date(currentTs).getTime()
        const nextTime = new Date(nextTs).getTime()
        if (Number.isFinite(currTime) && Number.isFinite(nextTime)) {
          deltaMs = nextTime - currTime
          if (deltaMs < 0) deltaMs = 50
        }
      }

      const delay = getDelayForSpeed(deltaMs, speedRef.current)
      if (speedRef.current === 'instant') {
        // Instant mode: batch process remaining events with microtask breaks
        timerRef.current = setTimeout(playNextEvent, 0)
      } else {
        // Ensure minimum 30ms between events for visible progression
        // (events may have near-identical timestamps from batch storage)
        const effectiveDelay = Math.max(delay, 30)
        timerRef.current = setTimeout(playNextEvent, effectiveDelay)
      }
    } else {
      // Last event
      setState((s) => ({ ...s, isPlaying: false, isComplete: true }))
      isPlayingRef.current = false
    }
  }, [processEvent, getDelayForSpeed])

  const loadTrace = useCallback(
    (events: StreamEvent[]) => {
      clearTimer()
      reset()

      // Filter out heartbeats for display purposes
      const meaningful = events.filter((e) => e.type !== 'heartbeat')
      eventsRef.current = meaningful
      positionRef.current = 0
      isPlayingRef.current = false

      setState({
        isPlaying: false,
        position: 0,
        totalEvents: meaningful.length,
        speed: speedRef.current,
        isComplete: meaningful.length === 0,
        events: meaningful,
      })
    },
    [clearTimer, reset],
  )

  const loadInstant = useCallback(
    (events: StreamEvent[]) => {
      clearTimer()
      reset()

      const meaningful = events.filter((e) => e.type !== 'heartbeat')
      eventsRef.current = meaningful
      positionRef.current = meaningful.length
      isPlayingRef.current = false
      speedRef.current = 'instant'

      // Process all events at once
      for (const event of meaningful) {
        processEvent(event)
      }

      setState({
        isPlaying: false,
        position: meaningful.length,
        totalEvents: meaningful.length,
        speed: 'instant',
        isComplete: true,
        events: meaningful,
      })
    },
    [clearTimer, reset, processEvent],
  )

  const play = useCallback(() => {
    if (isPlayingRef.current) return
    if (positionRef.current >= eventsRef.current.length) return
    isPlayingRef.current = true
    setState((s) => ({ ...s, isPlaying: true }))
    playNextEvent()
  }, [playNextEvent])

  const pause = useCallback(() => {
    clearTimer()
    isPlayingRef.current = false
    setState((s) => ({ ...s, isPlaying: false }))
  }, [clearTimer])

  const stepForward = useCallback(() => {
    const events = eventsRef.current
    const pos = positionRef.current
    if (pos >= events.length) return

    pause()

    // Find next non-heartbeat event
    let nextPos = pos
    while (nextPos < events.length && events[nextPos].type === 'heartbeat') {
      nextPos++
    }
    if (nextPos < events.length) {
      processEvent(events[nextPos])
      positionRef.current = nextPos + 1
      setState((s) => ({
        ...s,
        position: nextPos + 1,
        isComplete: nextPos + 1 >= events.length,
      }))
    }
  }, [pause, processEvent])

  const stepBackward = useCallback(() => {
    const events = eventsRef.current
    const pos = positionRef.current
    if (pos <= 0) return

    pause()

    // Re-process all events up to pos - 1
    const targetPos = pos - 1
    reset()
    positionRef.current = 0

    for (let i = 0; i < targetPos; i++) {
      if (events[i].type !== 'heartbeat') {
        processEvent(events[i])
      }
    }

    positionRef.current = targetPos
    setState((s) => ({
      ...s,
      position: targetPos,
      isComplete: false,
    }))
  }, [pause, reset, processEvent])

  const seekTo = useCallback(
    (targetPosition: number) => {
      const events = eventsRef.current
      const clamped = Math.max(0, Math.min(targetPosition, events.length))

      pause()
      reset()
      positionRef.current = 0

      for (let i = 0; i < clamped; i++) {
        if (events[i].type !== 'heartbeat') {
          processEvent(events[i])
        }
      }

      positionRef.current = clamped
      setState((s) => ({
        ...s,
        position: clamped,
        isComplete: clamped >= events.length,
      }))
    },
    [pause, reset, processEvent],
  )

  const setSpeed = useCallback((speed: ReplaySpeed) => {
    speedRef.current = speed
    setState((s) => ({ ...s, speed }))
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      clearTimer()
    }
  }, [clearTimer])

  return {
    ...state,
    loadTrace,
    loadInstant,
    play,
    pause,
    stepForward,
    stepBackward,
    seekTo,
    setSpeed,
  }
}
