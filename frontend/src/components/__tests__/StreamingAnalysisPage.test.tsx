import { describe, it, expect, vi, afterEach } from 'vitest'
import { act, screen } from '@testing-library/react'
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

  it('renders ticker header when tickers are provided', () => {
    renderWithRoute('?tickers=AAPL,GOOGL')
    expect(screen.getByText('Analyzing AAPL, GOOGL')).toBeInTheDocument()
  })

  it('shows skeleton cards for pending tickers', () => {
    renderWithRoute('?tickers=MSFT')
    // Skeleton card should show the ticker name
    expect(screen.getByText('MSFT')).toBeInTheDocument()
  })

  it('renders the agent trace panel', () => {
    renderWithRoute('?tickers=AAPL')
    expect(screen.getByText('Agent Trace')).toBeInTheDocument()
  })

  describe('retry after a fully-pending timeout', () => {
    afterEach(() => {
      useAnalysisStore.getState().reset()
    })

    it('reconnects instead of silently no-op navigating when incomplete_tickers matches the URL', async () => {
      const user = userEvent.setup()
      const esSpy = vi.spyOn(globalThis, 'EventSource')

      renderWithRoute('?tickers=JNJ')
      await user.click(screen.getByRole('button', { name: /start analysis/i }))

      expect(esSpy).toHaveBeenCalledTimes(1)

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
      expect(esSpy).toHaveBeenCalledTimes(2)
    })
  })
})
