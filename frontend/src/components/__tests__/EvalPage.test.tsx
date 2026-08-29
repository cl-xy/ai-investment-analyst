import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { render } from '../../test/utils'
import EvalPage from '../EvalPage'
import { server } from '../../test/server'
import { http, HttpResponse } from 'msw'

const EVAL_SUMMARY = {
  total_runs: 42,
  schema_validation_rate: 98.5,
  avg_latency_ms: 5000,
  p95_latency_ms: 9000,
  citation_coverage: 3.2,
  tool_success_rate: 95.0,
  cache_hit_rate: 60.0,
  last_run_at: '2026-08-20T12:00:00Z',
}

function mockEvalSummary() {
  server.use(http.get('/api/eval/summary', () => HttpResponse.json(EVAL_SUMMARY)))
}

describe('EvalPage — Production Learning Loop', () => {
  it('renders empty state when no predictions have resolved yet', async () => {
    mockEvalSummary()
    server.use(
      http.get('/api/eval-flywheel/funnel', () =>
        HttpResponse.json({
          resolved_predictions: 0,
          classified_cases: 0,
          promoted_cases: 0,
          replay_ready_cases: 0,
          promotion_reasons: [],
        })
      ),
      http.get('/api/eval-flywheel/runs', () => HttpResponse.json({ runs: [] }))
    )
    render(<EvalPage />)
    await waitFor(() => {
      expect(screen.getByText('No resolved predictions yet')).toBeInTheDocument()
    })
  })

  it('renders funnel counts and promotion reasons when data is present', async () => {
    mockEvalSummary()
    server.use(
      http.get('/api/eval-flywheel/funnel', () =>
        HttpResponse.json({
          resolved_predictions: 50,
          classified_cases: 12,
          promoted_cases: 8,
          replay_ready_cases: 6,
          promotion_reasons: [{ reason: 'high_confidence_incorrect', count: 5 }],
        })
      ),
      http.get('/api/eval-flywheel/runs', () => HttpResponse.json({ runs: [] }))
    )
    render(<EvalPage />)
    await waitFor(() => {
      expect(screen.getByText('Production Learning Loop')).toBeInTheDocument()
    })
    expect(screen.getByText('50')).toBeInTheDocument()
    expect(screen.getByText('8')).toBeInTheDocument()
    expect(screen.getByText('high_confidence_incorrect')).toBeInTheDocument()
    expect(screen.getByText('No evaluation run has been triggered yet.')).toBeInTheDocument()
  })

  it('renders the latest run decision badge', async () => {
    mockEvalSummary()
    server.use(
      http.get('/api/eval-flywheel/funnel', () =>
        HttpResponse.json({
          resolved_predictions: 50,
          classified_cases: 12,
          promoted_cases: 8,
          replay_ready_cases: 6,
          promotion_reasons: [],
        })
      ),
      http.get('/api/eval-flywheel/runs', () =>
        HttpResponse.json({
          runs: [
            {
              id: 'run-1',
              candidate_config: 'baseline-replay-v1',
              case_count: 10,
              status: 'completed',
              decision: 'investigate',
              started_at: '2026-08-20T10:00:00Z',
              completed_at: '2026-08-20T10:05:00Z',
            },
          ],
        })
      )
    )
    render(<EvalPage />)
    await waitFor(() => {
      expect(screen.getByText('Investigate')).toBeInTheDocument()
    })
    expect(screen.getByText('baseline-replay-v1')).toBeInTheDocument()
  })

  it('shows a scoped error state for the learning loop section without blocking eval metrics', async () => {
    mockEvalSummary()
    server.use(
      http.get('/api/eval-flywheel/funnel', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 })
      ),
      http.get('/api/eval-flywheel/runs', () => HttpResponse.json({ runs: [] }))
    )
    render(<EvalPage />)
    await waitFor(() => {
      expect(screen.getByText('Failed to load learning loop data')).toBeInTheDocument()
    })
    // Existing eval metrics section still rendered despite the flywheel error.
    expect(screen.getByText('Evaluation Metrics')).toBeInTheDocument()
  })
})
