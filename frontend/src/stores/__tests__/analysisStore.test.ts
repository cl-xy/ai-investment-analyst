import { describe, it, expect, beforeEach } from 'vitest'
import { useAnalysisStore } from '../../stores/analysisStore'
import type { AnalysisOutput, StreamEvent } from '../../types/stream'

describe('analysisStore', () => {
  beforeEach(() => {
    useAnalysisStore.getState().reset()
  })

  it('has correct initial state', () => {
    const state = useAnalysisStore.getState()
    expect(state.events).toEqual([])
    expect(state.currentNode).toBeNull()
    expect(state.isStreaming).toBe(false)
    expect(state.error).toBeNull()
    expect(state.analyses).toEqual({})
    expect(state.runMeta).toBeNull()
  })

  it('startStream resets state and sets streaming', () => {
    const store = useAnalysisStore.getState()
    store.setError('old error')
    store.startStream('run-123')

    const state = useAnalysisStore.getState()
    expect(state.isStreaming).toBe(true)
    expect(state.error).toBeNull()
    expect(state.events).toEqual([])
    expect(state.analyses).toEqual({})
    expect(state.runMeta).toEqual({
      run_id: 'run-123',
      startedAt: expect.any(String),
    })
  })

  it('addEvent appends events to the list', () => {
    const store = useAnalysisStore.getState()
    const event: StreamEvent = {
      run_id: 'run-1',
      seq: 1,
      type: 'node_started',
      timestamp: '2026-07-26T10:00:00Z',
      node: 'router',
      tool: null,
      payload: {},
    }
    store.addEvent(event)

    const state = useAnalysisStore.getState()
    expect(state.events).toHaveLength(1)
    expect(state.events[0]).toEqual(event)
  })

  it('addEvent sets currentNode on node_started', () => {
    const store = useAnalysisStore.getState()
    store.addEvent({
      run_id: 'run-1',
      seq: 1,
      type: 'node_started',
      timestamp: '2026-07-26T10:00:00Z',
      node: 'fetch_data',
      tool: null,
      payload: {},
    })

    expect(useAnalysisStore.getState().currentNode).toBe('fetch_data')
  })

  it('addEvent clears currentNode on node_completed for matching node', () => {
    const store = useAnalysisStore.getState()
    store.addEvent({
      run_id: 'run-1',
      seq: 1,
      type: 'node_started',
      timestamp: '2026-07-26T10:00:00Z',
      node: 'analyze',
      tool: null,
      payload: {},
    })
    store.addEvent({
      run_id: 'run-1',
      seq: 2,
      type: 'node_completed',
      timestamp: '2026-07-26T10:00:01Z',
      node: 'analyze',
      tool: null,
      payload: {},
    })

    expect(useAnalysisStore.getState().currentNode).toBeNull()
  })

  it('setAnalysis adds an analysis result', () => {
    const store = useAnalysisStore.getState()
    const analysis: AnalysisOutput = {
      ticker: 'AAPL',
      signal: 'buy',
      confidence: 'high',
      sentiment_score: 0.75,
      thesis: 'Strong fundamentals',
      risk_flags: ['Valuation premium'],
      price_data: {},
      fundamentals: {},
      sec_notes: '',
    }
    store.setAnalysis('AAPL', analysis)

    const state = useAnalysisStore.getState()
    expect(state.analyses['AAPL']).toEqual(analysis)
  })

  it('setComplete stops streaming and updates runMeta', () => {
    const store = useAnalysisStore.getState()
    store.startStream('run-1')
    store.setComplete({
      tickers: ['AAPL'],
      total_duration_ms: 4500,
      total_tokens: 800,
      cost_usd: 0.002,
    })

    const state = useAnalysisStore.getState()
    expect(state.isStreaming).toBe(false)
    expect(state.runMeta?.totalDurationMs).toBe(4500)
    expect(state.runMeta?.totalTokens).toBe(800)
    expect(state.runMeta?.costUsd).toBe(0.002)
  })

  it('setError sets error message and stops streaming', () => {
    const store = useAnalysisStore.getState()
    store.startStream('run-1')
    store.setError('Connection lost')

    const state = useAnalysisStore.getState()
    expect(state.error).toBe('Connection lost')
    expect(state.isStreaming).toBe(false)
  })

  it('reset restores initial state', () => {
    const store = useAnalysisStore.getState()
    store.startStream('run-1')
    store.addEvent({
      run_id: 'run-1',
      seq: 1,
      type: 'node_started',
      timestamp: '2026-07-26T10:00:00Z',
      node: 'router',
      tool: null,
      payload: {},
    })
    store.setAnalysis('AAPL', {
      ticker: 'AAPL',
      signal: 'hold',
      confidence: 'medium',
      sentiment_score: 0.1,
      risk_flags: [],
      price_data: {},
      fundamentals: {},
      sec_notes: '',
    })

    store.reset()

    const state = useAnalysisStore.getState()
    expect(state.events).toEqual([])
    expect(state.currentNode).toBeNull()
    expect(state.isStreaming).toBe(false)
    expect(state.error).toBeNull()
    expect(state.analyses).toEqual({})
    expect(state.runMeta).toBeNull()
  })
})
