import { test, expect, type Page, type Route } from '@playwright/test'
import {
  createErrorSSEStream,
  createMockSSEStream,
  createDisconnectSSEStream,
} from './fixtures/mock-sse-events'

test.describe('Error states', () => {
  test('network error shows error message with retry button', async ({ page }) => {
    // Mock the endpoint to return a network error
    await page.route('**/api/analyze/stream**', async (route: Route) => {
      await route.abort('connectionrefused')
    })

    await page.goto('/analyze?tickers=NVDA')

    // Error message should appear after retries are exhausted
    await expect(
      page.getByText(/Connection lost|Analysis failed/),
    ).toBeVisible({ timeout: 15_000 })

    // Retry button should be visible
    await expect(
      page.getByRole('button', { name: /Retry/i }),
    ).toBeVisible()
  })

  test('invalid ticker shows validation error from backend', async ({ page }) => {
    await page.route('**/api/analyze/stream**', async (route: Route) => {
      const body = createErrorSSEStream('INVALID', 'Invalid ticker symbol: INVALID')
      await route.fulfill({
        status: 200,
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
        },
        body,
      })
    })

    await page.goto('/analyze?tickers=INVALID')

    await expect(
      page.getByText('Invalid ticker symbol: INVALID'),
    ).toBeVisible({ timeout: 10_000 })
  })

  test('stream disconnect shows connection lost message', async ({ page }) => {
    // First request returns a partial stream (simulates disconnect)
    await page.route('**/api/analyze/stream**', async (route: Route) => {
      const body = createDisconnectSSEStream('NVDA')
      await route.fulfill({
        status: 200,
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
        },
        body,
      })
    })

    await page.goto('/analyze?tickers=NVDA')

    // After the stream closes without run_completed, the EventSource will
    // error and retries will be exhausted, showing the connection lost message
    await expect(
      page.getByText(/Connection lost/),
    ).toBeVisible({ timeout: 20_000 })
  })

  test('partial failure (tool error) still shows analysis with data_gaps', async ({ page }) => {
    await page.route('**/api/analyze/stream**', async (route: Route) => {
      const body = createMockSSEStream('NVDA', {
        includeDataGaps: true,
        failAtNode: 'fetch_data',
      })
      await route.fulfill({
        status: 200,
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
        },
        body,
      })
    })

    await page.goto('/analyze?tickers=NVDA')

    // Analysis card should still render with signal
    await expect(page.getByText('Buy')).toBeVisible({ timeout: 10_000 })

    // Data gaps warning should show
    await expect(
      page.getByText(/Based on partial data/),
    ).toBeVisible()
    await expect(page.getByText(/sec_filings/)).toBeVisible()
  })
})
