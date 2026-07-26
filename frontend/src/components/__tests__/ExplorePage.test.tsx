import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { render } from '../../test/utils'
import ExplorePage from '../ExplorePage'
import { axe } from 'vitest-axe'
import { server } from '../../test/server'
import { http, HttpResponse } from 'msw'

describe('ExplorePage', () => {
  it('renders the page heading', async () => {
    render(<ExplorePage />)
    expect(screen.getByText('Trending Stocks')).toBeInTheDocument()
  })

  it('shows loading skeletons initially', () => {
    render(<ExplorePage />)
    // Skeleton rows have rank numbers
    expect(screen.getByText('1')).toBeInTheDocument()
  })

  it('renders stock list after loading', async () => {
    render(<ExplorePage />)
    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument()
    })
    expect(screen.getByText('Apple Inc.')).toBeInTheDocument()
    expect(screen.getByText('TSLA')).toBeInTheDocument()
    expect(screen.getByText('NVDA')).toBeInTheDocument()
  })

  it('handles empty stock list', async () => {
    server.use(
      http.get('/api/explore', () => {
        return HttpResponse.json({ stocks: [], updated_at: '2026-07-26T12:00:00Z' })
      })
    )
    render(<ExplorePage />)
    await waitFor(() => {
      // No skeleton rows should remain, and no stock rows either
      expect(screen.queryByText('AAPL')).not.toBeInTheDocument()
    })
  })

  it('shows error state on API failure', async () => {
    server.use(
      http.get('/api/explore', () => {
        return HttpResponse.json(
          { detail: 'Server error' },
          { status: 500 }
        )
      })
    )
    render(<ExplorePage />)
    await waitFor(() => {
      expect(screen.getByText(/Request failed with status code 500/)).toBeInTheDocument()
    })
  })

  it('has no accessibility violations', async () => {
    const { container } = render(<ExplorePage />)
    await waitFor(() => {
      expect(screen.getByText('AAPL')).toBeInTheDocument()
    })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
