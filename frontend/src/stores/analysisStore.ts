import { create } from 'zustand'
import type {
  AnalysisOutput,
  DebateTurnPayload,
  DebateVerdictPayload,
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
    totalDurationMs?: number
    totalTokens?: number
    costUsd?: number
  } | null

  // Debate state
  debates: Record<string, DebateState>

  // Actions
  startStream: (runId: string) => void
  addEvent: (event: StreamEvent) => void
  setAnalysis: (ticker: string, analysis: AnalysisOutput) => void
  setComplete: (meta: RunCompletedPayload) => void
  setError: (error: string) => void
  addDebateTurn: (ticker: string, turn: DebateTurnPayload) => void
  setDebateVerdict: (ticker: string, verdict: DebateVerdictPayload) => void
  reset: () => void
}

export const useAnalysisStore = create<AnalysisStore>((set) => ({
  events: [],
  currentNode: null,
  isStreaming: false,
  error: null,
  analyses: {},
  runMeta: null,
  debates: {},

  startStream: (runId: string) =>
    set({
      events: [],
      currentNode: null,
      isStreaming: true,
      error: null,
      analyses: {},
      runMeta: { run_id: runId, startedAt: new Date().toISOString() },
      debates: {},
    }),

  addEvent: (event: StreamEvent) =>
    set((state) => {
      const updates: Partial<AnalysisStore> = {
        events: [...state.events, event],
      }

      if (event.type === 'node_started') {
        updates.currentNode = event.node
      } else if (event.type === 'node_completed' && event.node === state.currentNode) {
        updates.currentNode = null
      }

      // Track debate started
      if (event.type === 'debate_started') {
        const ticker = event.payload.ticker as string
        updates.debates = {
          ...state.debates,
          [ticker]: { ticker, turns: [], verdict: null, isActive: true },
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
    set({ error, isStreaming: false }),

  addDebateTurn: (ticker: string, turn: DebateTurnPayload) =>
    set((state) => {
      const existing = state.debates[ticker] || emptyDebate(ticker)
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

  reset: () =>
    set({
      events: [],
      currentNode: null,
      isStreaming: false,
      error: null,
      analyses: {},
      runMeta: null,
      debates: {},
    }),
}))
