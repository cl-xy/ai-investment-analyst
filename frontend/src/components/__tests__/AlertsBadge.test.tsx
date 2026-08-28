import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { render } from '../../test/utils'
import { AlertsBadge } from '../AlertsBadge'
import { server } from '../../test/server'
import { http, HttpResponse } from 'msw'

describe('AlertsBadge', () => {
  it('renders a link to /alerts', async () => {
    server.use(
      http.get('/api/alerts/unread-count', () => HttpResponse.json({ unread_count: 0 }))
    )
    render(<AlertsBadge />)
    const link = screen.getByRole('link', { name: /signal alerts/i })
    expect(link).toHaveAttribute('href', '/alerts')
  })

  it('shows no badge when unread count is zero', async () => {
    server.use(
      http.get('/api/alerts/unread-count', () => HttpResponse.json({ unread_count: 0 }))
    )
    render(<AlertsBadge />)
    await waitFor(() => {
      expect(screen.getByRole('link')).toHaveAttribute('aria-label', 'Signal alerts')
    })
  })

  it('shows the unread count badge when greater than zero', async () => {
    server.use(
      http.get('/api/alerts/unread-count', () => HttpResponse.json({ unread_count: 3 }))
    )
    render(<AlertsBadge />)
    await waitFor(() => {
      expect(screen.getByText('3')).toBeInTheDocument()
    })
  })

  it('caps the displayed count at 9+', async () => {
    server.use(
      http.get('/api/alerts/unread-count', () => HttpResponse.json({ unread_count: 42 }))
    )
    render(<AlertsBadge />)
    await waitFor(() => {
      expect(screen.getByText('9+')).toBeInTheDocument()
    })
  })

  it('does not crash when the request fails', async () => {
    server.use(
      http.get('/api/alerts/unread-count', () => HttpResponse.error())
    )
    render(<AlertsBadge />)
    await waitFor(() => {
      expect(screen.getByRole('link')).toBeInTheDocument()
    })
  })
})
