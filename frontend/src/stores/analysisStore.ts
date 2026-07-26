import { create } from 'zustand'
import type {
  AnalysisOutput,
  RunCompletedPayload,
  StreamEvent,
} from '../types/stream'

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

  // Actions
  startStream: (runId: string) => void
  addEvent: (event: StreamEvent) => void
  setAnalysis: (ticker: string, analysis: AnalysisOutput) => void
  setComplete: (meta: RunCompletedPayload) => void
  setError: (error: string) => void
  reset: () => void
}

export const useAnalysisStore = create<AnalysisStore>((set) => ({
  events: [],
  currentNode: null,
  isStreaming: false,
  error: null,
  analyses: {},
  runMeta: null,

  startStream: (runId: string) =>
    set({
      events: [],
      currentNode: null,
      isStreaming: true,
      error: null,
      analyses: {},
      runMeta: { run_id: runId, startedAt: new Date().toISOString() },
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

  reset: () =>
    set({
      events: [],
      currentNode: null,
      isStreaming: false,
      error: null,
      analyses: {},
      runMeta: null,
    }),
}))
