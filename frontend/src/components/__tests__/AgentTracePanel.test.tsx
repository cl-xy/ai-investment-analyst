import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { render } from '../../test/utils'
import AgentTracePanel from '../AgentTracePanel'
import { useAnalysisStore } from '../../stores/analysisStore'
import { axe } from 'vitest-axe'

describe('AgentTracePanel', () => {
  it('renders the panel header', () => {
    render(<AgentTracePanel />)
    expect(screen.getByText('Agent Trace')).toBeInTheDocument()
  })

  it('renders empty state when no events and not streaming', () => {
    render(<AgentTracePanel />)
    // No trace events listed, no status badge visible
    const log = screen.getByRole('log')
    expect(log).toBeInTheDocument()
    expect(log.children).toHaveLength(0)
  })

  it('shows initializing message when streaming with no events', () => {
    useAnalysisStore.setState({ isStreaming: true, events: [] })
    render(<AgentTracePanel />)
    expect(screen.getByText('Initializing agent...')).toBeInTheDocument()
  })

  it('shows streaming badge when streaming', () => {
    useAnalysisStore.setState({ isStreaming: true, events: [] })
    render(<AgentTracePanel />)
    expect(screen.getByText('Streaming')).toBeInTheDocument()
  })

  it('shows complete badge when run is done', () => {
    useAnalysisStore.setState({
      isStreaming: false,
      events: [
        {
          run_id: 'test-run',
          seq: 1,
          type: 'run_completed',
          timestamp: '2026-07-26T10:00:00Z',
          node: null,
          tool: null,
          payload: { total_duration_ms: 5000, total_tokens: 1200, cost_usd: 0 },
        },
      ],
      runMeta: { run_id: 'test-run', startedAt: '2026-07-26T09:59:55Z', totalDurationMs: 5000, totalTokens: 1200, costUsd: 0 },
    })
    render(<AgentTracePanel />)
    expect(screen.getByText('Complete')).toBeInTheDocument()
  })

  it('shows failed badge on unrecoverable error', () => {
    useAnalysisStore.setState({
      isStreaming: false,
      events: [
        {
          run_id: 'test-run',
          seq: 1,
          type: 'error',
          timestamp: '2026-07-26T10:00:00Z',
          node: null,
          tool: null,
          payload: { message: 'Something failed', recoverable: false },
        },
      ],
    })
    render(<AgentTracePanel />)
    expect(screen.getByText('Failed')).toBeInTheDocument()
  })

  it('has proper aria attributes for accessibility', () => {
    render(<AgentTracePanel />)
    const log = screen.getByRole('log')
    expect(log).toHaveAttribute('aria-label', 'Agent execution trace')
    expect(log).toHaveAttribute('aria-live', 'polite')
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<AgentTracePanel />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
