import { describe, it, expect, vi, afterEach } from 'vitest'
import { act, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { render } from '../../test/utils'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { render as rtlRender } from '@testing-library/react'
import StreamingAnalysisPage from '../StreamingAnalysisPage'
import { useAnalysisStore } from '../../stores/analysisStore'

function renderWithRoute(search: string) {
  return rtlRender(
    <MemoryRouter initialEntries={[`/analyze${search}`]}>
      <Routes>
        <Route path="/analyze" element={<StreamingAnalysisPage />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('StreamingAnalysisPage', () => {
  it('shows empty state when no tickers are specified', () => {
    renderWithRoute('')
    expect(screen.getByText('No tickers specified.')).toBeInTheDocument()
  })

  it('shows a back button to return to watchlist', () => {
    renderWithRoute('')
    expect(screen.getByText('Go back to watchlist')).toBeInTheDocument()
  })

  it('shows a pre-flight confirmation before starting an analysis', () => {
    renderWithRoute('?tickers=AAPL,GOOGL')
    expect(screen.getByText('Ready to analyze')).toBeInTheDocument()
    expect(screen.getByText('AAPL')).toBeInTheDocument()
    expect(screen.getByText('GOOGL')).toBeInTheDocument()
  })

  it('renders ticker header once the analysis is started', async () => {
    const user = userEvent.setup()
    renderWithRoute('?tickers=AAPL,GOOGL')
    await user.click(screen.getByRole('button', { name: /start analysis/i }))
    expect(screen.getByText('Analyzing AAPL, GOOGL')).toBeInTheDocument()
  })

  it('shows skeleton cards for pending tickers', async () => {
    const user = userEvent.setup()
    renderWithRoute('?tickers=MSFT')
    await user.click(screen.getByRole('button', { name: /start analysis/i }))
    // Skeleton card should show the ticker name
    expect(screen.getAllByText('MSFT').length).toBeGreaterThan(0)
  })

  it('renders the agent trace panel', async () => {
    const user = userEvent.setup()
    renderWithRoute('?tickers=AAPL')
    await user.click(screen.getByRole('button', { name: /start analysis/i }))
    expect(screen.getAllByText('Agent Trace').length).toBeGreaterThan(0)
  })

  describe('retry after a fully-pending timeout', () => {
    afterEach(() => {
      useAnalysisStore.getState().reset()
    })

    it('reconnects instead of silently no-op navigating when incomplete_tickers matches the URL', async () => {
      const user = userEvent.setup()
      const esSpy = vi.spyOn(globalThis, 'fetch')

      renderWithRoute('?tickers=JNJ')
      await user.click(screen.getByRole('button', { name: /start analysis/i }))

      const streamCalls = () =>
        esSpy.mock.calls.filter(([url]) => String(url).includes('/api/analyze/stream')).length
      await waitFor(() => expect(streamCalls()).toBe(1))

      // Simulate the backend timing out with the single ticker still pending
      // (e.g. "Analysis timed out after 255s while in debate. Still pending: JNJ").
      act(() => {
        useAnalysisStore.setState({
          isStreaming: false,
          timeout: {
            completed_tickers: [],
            incomplete_tickers: ['JNJ'],
            stage: 'debate',
            elapsed_seconds: 255,
            retry_after_seconds: 0,
            message: 'Analysis timed out after 255s while in debate.',
          },
        })
      })

      expect(screen.getByText(/analysis timed out/i)).toBeInTheDocument()

      const retryButton = screen.getByRole('button', { name: /retry/i })
      expect(retryButton).toBeEnabled()
      await user.click(retryButton)

      // Before the fix, retrying a fully-pending timeout navigated to the
      // same URL, which is a no-op in React Router, so no new connection
      // was ever made. A real retry must open a fresh EventSource.
      await waitFor(() => expect(streamCalls()).toBe(2))
    })
  })

  it('keeps a completed analysis successful when only report synthesis times out', async () => {
    const user = userEvent.setup()
    renderWithRoute('?tickers=MDB')
    await user.click(screen.getByRole('button', { name: /start analysis/i }))

    act(() => {
      useAnalysisStore.setState({
        analyses: {
          MDB: {
            ticker: 'MDB', signal: 'hold', confidence: 'medium', sentiment_score: 0,
            risk_flags: [], price_data: {}, fundamentals: {}, sec_notes: '',
          },
        },
        isStreaming: false,
        events: [{
          run_id: 'run-1', seq: 1, type: 'warning', timestamp: new Date().toISOString(),
          node: null, tool: null, correlation_id: null,
          payload: { context: 'generate_report', message: 'Report synthesis timed out' },
        }],
      })
    })

    expect(screen.getByText('Analysis complete')).toBeInTheDocument()
    expect(screen.getAllByText(/report synthesis timed out/i).length).toBeGreaterThan(0)
    expect(screen.queryByText('Analysis partially timed out')).not.toBeInTheDocument()
  })
})


describe('StreamingAnalysisPage backup model note', () => {
  afterEach(() => {
    useAnalysisStore.getState().reset()
  })

  const baseAnalysis = {
    ticker: 'NVDA', signal: 'hold' as const, confidence: 'medium' as const, sentiment_score: 0,
    risk_flags: [], price_data: {}, fundamentals: {}, sec_notes: '',
  }

  async function renderWith(fallbackTurns?: { turn: string; model: string; reasoning_off: boolean }[]) {
    const user = userEvent.setup()
    renderWithRoute('?tickers=NVDA')
    await user.click(screen.getByRole('button', { name: /start analysis/i }))
    act(() => {
      useAnalysisStore.setState({
        analyses: { NVDA: { ...baseAnalysis, ...(fallbackTurns ? { fallback_turns: fallbackTurns } : {}) } },
        isStreaming: false,
      })
    })
  }

  it('shows which backup model answered, with reasoning state', async () => {
    await renderWith([
      { turn: 'moderator', model: 'nvidia/nemotron-3.5-super-vl:free', reasoning_off: true },
    ])
    expect(screen.getByText('Answered by a backup model')).toBeInTheDocument()
    expect(screen.getByText(/moderator turn: nemotron-3\.5-super-vl \(reasoning off\)/)).toBeInTheDocument()
  })

  it('says nothing when the primary model answered every turn', async () => {
    await renderWith([])
    expect(screen.queryByText('Answered by a backup model')).not.toBeInTheDocument()
  })

  it('says nothing for analyses that predate the field', async () => {
    await renderWith(undefined)
    expect(screen.queryByText('Answered by a backup model')).not.toBeInTheDocument()
  })
})
