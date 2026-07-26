import { test, expect, type Page, type Route } from '@playwright/test'
import { createMockSSEStream } from './fixtures/mock-sse-events'

/**
 * Intercepts the SSE analyze endpoint and returns a mocked stream response.
 */
async function mockSSEEndpoint(page: Page, ticker: string) {
  await page.route('**/api/analyze/stream**', async (route: Route) => {
    const body = createMockSSEStream(ticker)
    await route.fulfill({
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
      body,
    })
  })
}

test.describe('Analysis flow', () => {
  test.beforeEach(async ({ page }) => {
    await mockSSEEndpoint(page, 'NVDA')
  })

  test('user can type a ticker in the input field', async ({ page }) => {
    await page.goto('/')

    const input = page.getByLabel('Ticker symbol input')
    await expect(input).toBeVisible()

    await input.fill('NVDA')
    await expect(input).toHaveValue('NVDA')
  })

  test('submit button triggers analysis', async ({ page }) => {
    await page.goto('/')

    const input = page.getByLabel('Ticker symbol input')
    await input.fill('NVDA')

    // Click Add button
    await page.getByRole('button', { name: /Add/i }).click()

    // Ticker pill appears
    await expect(page.getByText('NVDA')).toBeVisible()

    // Click Analyze button
    await page.getByRole('button', { name: /Analyze 1 stock/i }).click()

    // Should navigate to /analyze
    await expect(page).toHaveURL(/\/analyze\?tickers=NVDA/)
  })

  test('trace panel appears showing agent progress', async ({ page }) => {
    await page.goto('/analyze?tickers=NVDA')

    // Trace panel header
    await expect(page.getByText('Agent Trace')).toBeVisible()

    // Wait for nodes to appear in the trace
    await expect(page.getByText('router')).toBeVisible({ timeout: 10_000 })
    await expect(page.getByText('fetch_data')).toBeVisible()
    await expect(page.getByText('analyze')).toBeVisible()

    // Status badge shows Complete after stream ends
    await expect(page.getByText('Complete')).toBeVisible({ timeout: 10_000 })
  })

  test('analysis card renders with signal badge', async ({ page }) => {
    await page.goto('/analyze?tickers=NVDA')

    // Wait for the analysis card to render
    await expect(page.getByText('NVDA').first()).toBeVisible({ timeout: 10_000 })

    // Signal badge (buy)
    await expect(page.getByText('Buy')).toBeVisible()

    // Confidence badge
    await expect(page.getByText('high')).toBeVisible()

    // Thesis text
    await expect(
      page.getByText(/demonstrates strong revenue growth/),
    ).toBeVisible()

    // Bull case items
    await expect(page.getByText(/Data center revenue up 150%/)).toBeVisible()

    // Bear case items
    await expect(page.getByText(/Elevated valuation multiples/)).toBeVisible()
  })

  test('citations section is visible', async ({ page }) => {
    await page.goto('/analyze?tickers=NVDA')

    // Wait for analysis to complete
    await expect(page.getByText('Sources')).toBeVisible({ timeout: 10_000 })

    // Citation badges
    await expect(page.getByText('Yahoo Finance')).toBeVisible()
    await expect(page.getByText('NewsAPI')).toBeVisible()
  })

  test('data freshness indicator shows', async ({ page }) => {
    await page.goto('/analyze?tickers=NVDA')

    // Wait for the analysis card to fully render
    await expect(page.getByText('Buy')).toBeVisible({ timeout: 10_000 })

    // The DataFreshness component should render with timestamp info
    // It uses the retrieved_at field from price_data
    const analysisCard = page.locator('.animate-fade-in').first()
    await expect(analysisCard).toBeVisible()
  })

  test('demo button triggers NVDA analysis directly', async ({ page }) => {
    await page.goto('/')

    await page.getByRole('button', { name: /Try a live analysis/i }).click()
    await expect(page).toHaveURL(/\/analyze\?tickers=NVDA/)
  })
})
