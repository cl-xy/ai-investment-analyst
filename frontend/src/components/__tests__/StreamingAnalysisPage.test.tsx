import { describe, it, expect } from 'vitest'
import { screen } from '@testing-library/react'
import { render } from '../../test/utils'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { render as rtlRender } from '@testing-library/react'
import StreamingAnalysisPage from '../StreamingAnalysisPage'

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
})
