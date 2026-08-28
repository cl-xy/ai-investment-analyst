import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { render } from '../../test/utils'
import AlertsPage from '../AlertsPage'
import { server } from '../../test/server'
import { http, HttpResponse } from 'msw'

const SAMPLE_ALERT = {
  id: 'alert-1',
  ticker: 'NVDA',
  alert_type: 'sentiment',
  severity: 'critical',
  drift_score: 0.72,
  old_signal: 'buy',
  new_signal: 'hold',
  reasoning_diff: {
    llm_judgment: {
      changed: true,
      new_signal: 'hold',
      reasoning: 'Sentiment collapsed and a new 8-K raised concerns.',
      key_shifts: ['sentiment reversal', 'new material filing'],
    },
    triggered_events: [{ type: 'sentiment', summary: 'Retail sentiment deteriorated' }],
  },
  triggered_by: ['sentiment', 'sec_filing'],
  llm_judged: true,
  dispatched_telegram: true,
  created_at: '2026-08-20T12:00:00Z',
  acknowledged_at: null,
}

describe('AlertsPage', () => {
  it('shows loading state initially', () => {
    render(<AlertsPage />)
    // Loading skeleton renders before data resolves
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('renders empty state when there are no alerts', async () => {
    server.use(
      http.get('/api/alerts', () => HttpResponse.json({ alerts: [], total: 0 }))
    )
    render(<AlertsPage />)
    await waitFor(() => {
      expect(screen.getByText('No alerts yet')).toBeInTheDocument()
    })
  })

  it('renders alert history with severity and signal transition', async () => {
    server.use(
      http.get('/api/alerts', () =>
        HttpResponse.json({ alerts: [SAMPLE_ALERT], total: 1 })
      )
    )
    render(<AlertsPage />)
    await waitFor(() => {
      expect(screen.getByText('NVDA')).toBeInTheDocument()
    })
    expect(screen.getByText('Critical')).toBeInTheDocument()
    expect(screen.getByText('BUY')).toBeInTheDocument()
    expect(screen.getByText('HOLD')).toBeInTheDocument()
    expect(screen.getByText(/Sentiment collapsed/)).toBeInTheDocument()
  })

  it('shows error state on API failure', async () => {
    server.use(
      http.get('/api/alerts', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 })
      )
    )
    render(<AlertsPage />)
    await waitFor(() => {
      expect(screen.getByText('Unable to load alerts')).toBeInTheDocument()
    })
  })

  it('expands to show key shifts when "What changed" is clicked', async () => {
    server.use(
      http.get('/api/alerts', () =>
        HttpResponse.json({ alerts: [SAMPLE_ALERT], total: 1 })
      )
    )
    render(<AlertsPage />)
    await waitFor(() => {
      expect(screen.getByText('NVDA')).toBeInTheDocument()
    })
    screen.getByText('What changed').click()
    await waitFor(() => {
      expect(screen.getByText('sentiment reversal')).toBeInTheDocument()
    })
  })

  it('acknowledges an unread alert', async () => {
    server.use(
      http.get('/api/alerts', () =>
        HttpResponse.json({ alerts: [SAMPLE_ALERT], total: 1 })
      ),
      http.post('/api/alerts/:id/acknowledge', () =>
        HttpResponse.json({ ...SAMPLE_ALERT, acknowledged_at: '2026-08-20T13:00:00Z' })
      )
    )
    render(<AlertsPage />)
    await waitFor(() => {
      expect(screen.getByText('Mark read')).toBeInTheDocument()
    })
    screen.getByText('Mark read').click()
    await waitFor(() => {
      expect(screen.queryByText('Mark read')).not.toBeInTheDocument()
    })
  })

  it('shows Telegram bot not configured message when no bot username is set', async () => {
    server.use(
      http.get('/api/alerts', () => HttpResponse.json({ alerts: [], total: 0 }))
    )
    render(<AlertsPage />)
    await waitFor(() => {
      expect(screen.getByText('Telegram bot not configured')).toBeInTheDocument()
    })
  })
})
