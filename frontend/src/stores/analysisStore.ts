import { create } from 'zustand'
import type {
  AnalysisOutput,
  DebateTurnPayload,
  DebateVerdictPayload,
  PeerComparisonPayload,
  RunCompletedPayload,
  StreamEvent,
} from '../types/stream'

interface DebateTurn {
  role: 'bull' | 'bear' | 'moderator'
  thesis: string
  confidence: 'high' | 'medium' | 'low'
  key_arguments: string[]
  turn_index: number
  duration_ms: number
}

interface DebateState {
  ticker: string
  turns: DebateTurn[]
  verdict: DebateVerdictPayload | null
  isActive: boolean
}

const emptyDebate = (ticker: string): DebateState => ({
  ticker,
  turns: [],
  verdict: null,
  isActive: true,
})

interface AnalysisStore {
  // Stream state
  events: StreamEvent[]
  currentNode: string | null
  isStreaming: boolean
  error: string | null

  // Analysis results (progressive rendering)
  analyses: Record<string, AnalysisOutput>
  runMeta: {
    run_id: string
    startedAt: string
    correlationId?: string | null
    totalDurationMs?: number
    totalTokens?: number
    costUsd?: number
  } | null

  // Debate state
  debates: Record<string, DebateState>

  // Auto sector-peer comparison (single-ticker analyses only)
  peerComparison: PeerComparisonPayload | null

  // Actions
  startStream: (runId: string, correlationId?: string | null) => void
  addEvent: (event: StreamEvent) => void
  setAnalysis: (ticker: string, analysis: AnalysisOutput) => void
  setComplete: (meta: RunCompletedPayload) => void
  setError: (error: string) => void
  addDebateTurn: (ticker: string, turn: DebateTurnPayload) => void
  setDebateVerdict: (ticker: string, verdict: DebateVerdictPayload) => void
  setPeerComparison: (peerComparison: PeerComparisonPayload) => void
  reset: () => void
}

const MAX_EVENTS = 500

export const useAnalysisStore = create<AnalysisStore>((set) => ({
  events: [],
  currentNode: null,
  isStreaming: false,
  error: null,
  analyses: {},
  runMeta: null,
  debates: {},
  peerComparison: null,

  startStream: (runId: string, correlationId?: string | null) =>
    set({
      events: [],
      currentNode: null,
      isStreaming: true,
      error: null,
      analyses: {},
      runMeta: { run_id: runId, startedAt: new Date().toISOString(), correlationId },
      debates: {},
      peerComparison: null,
    }),

  addEvent: (event: StreamEvent) =>
    set((state) => {
      const newEvents = [...state.events, event]
      const updates: Partial<AnalysisStore> = {
        events: newEvents.length > MAX_EVENTS ? newEvents.slice(-MAX_EVENTS) : newEvents,
      }

      if (event.type === 'node_started') {
        updates.currentNode = event.node
      } else if (event.type === 'node_completed' && event.node === state.currentNode) {
        updates.currentNode = null
      }

      // Track debate started (idempotent: preserve existing turns if replayed)
      if (event.type === 'debate_started') {
        const ticker = event.payload.ticker as string
        if (!state.debates[ticker]) {
          updates.debates = {
            ...state.debates,
            [ticker]: { ticker, turns: [], verdict: null, isActive: true },
          }
        }
      }

      return updates
    }),

  setAnalysis: (ticker: string, analysis: AnalysisOutput) =>
    set((state) => ({
      analyses: { ...state.analyses, [ticker]: analysis },
    })),

  setComplete: (meta: RunCompletedPayload) =>
    set((state) => ({
      isStreaming: false,
      currentNode: null,
      runMeta: state.runMeta
        ? {
            ...state.runMeta,
            totalDurationMs: meta.total_duration_ms,
            totalTokens: meta.total_tokens,
            costUsd: meta.cost_usd,
          }
        : null,
    })),

  setError: (error: string) =>
    set({ error, isStreaming: false, currentNode: null }),

  addDebateTurn: (ticker: string, turn: DebateTurnPayload) =>
    set((state) => {
      const existing = state.debates[ticker] || emptyDebate(ticker)
      // Deduplicate by turn_index (SSE reconnect can replay events)
      if (existing.turns.some((t) => t.turn_index === turn.turn_index)) {
        return state
      }
      return {
        debates: {
          ...state.debates,
          [ticker]: {
            ...existing,
            turns: [...existing.turns, {
              role: turn.role,
              thesis: turn.thesis,
              confidence: turn.confidence,
              key_arguments: turn.key_arguments,
              turn_index: turn.turn_index,
              duration_ms: turn.duration_ms,
            }],
          },
        },
      }
    }),

  setDebateVerdict: (ticker: string, verdict: DebateVerdictPayload) =>
    set((state) => {
      const existing = state.debates[ticker] || emptyDebate(ticker)
      return {
        debates: {
          ...state.debates,
          [ticker]: { ...existing, verdict, isActive: false },
        },
      }
    }),

  setPeerComparison: (peerComparison: PeerComparisonPayload) => set({ peerComparison }),

  reset: () =>
    set({
      events: [],
      currentNode: null,
      isStreaming: false,
      error: null,
      analyses: {},
      runMeta: null,
      debates: {},
      peerComparison: null,
    }),
}))
