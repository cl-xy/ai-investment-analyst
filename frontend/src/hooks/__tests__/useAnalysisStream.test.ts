import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useAnalysisStream } from '../../hooks/useAnalysisStream'
import { useAnalysisStore } from '../../stores/analysisStore'

describe('useAnalysisStream', () => {
  beforeEach(() => {
    useAnalysisStore.getState().reset()
  })

  it('returns connect and disconnect functions', () => {
    const { result } = renderHook(() => useAnalysisStream())
    expect(typeof result.current.connect).toBe('function')
    expect(typeof result.current.disconnect).toBe('function')
  })

  it('initializes with idle state (not streaming)', () => {
    renderHook(() => useAnalysisStream())
    const state = useAnalysisStore.getState()
    expect(state.isStreaming).toBe(false)
    expect(state.events).toEqual([])
    expect(state.error).toBeNull()
  })

  it('disconnect is safe to call when not connected', () => {
    const { result } = renderHook(() => useAnalysisStream())
    // Should not throw
    expect(() => result.current.disconnect()).not.toThrow()
  })
})
