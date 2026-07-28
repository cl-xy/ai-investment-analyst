import { test, expect, type Page, type Route } from '@playwright/test'

const mockAnalyses = [
  {
    id: 'abc123',
    tickers: ['NVDA'],
    created_at: '2026-07-28T10:00:00Z',
  },
  {
    id: 'def456',
    tickers: ['AAPL'],
    created_at: '2026-07-27T14:00:00Z',
  },
]

const mockNvdaDetail = {
  id: 'abc123',
  tickers: ['NVDA'],
  report_markdown: '',
  created_at: '2026-07-28T10:00:00Z',
  analyses: {
    NVDA: {
      ticker: 'NVDA',
      signal: 'buy',
      confidence: 'high',
      sentiment_score: 0.72,
      news_summary: 'Strong AI demand driving revenue growth',
      risk_flags: ['Concentration risk'],
      price_data: {},
      fundamentals: {},
      sec_notes: '',
    },
  },
}

const mockAaplDetail = {
  id: 'def456',
  tickers: ['AAPL'],
  report_markdown: '',
  created_at: '2026-07-27T14:00:00Z',
  analyses: {
    AAPL: {
      ticker: 'AAPL',
      signal: 'hold',
      confidence: 'medium',
      sentiment_score: 0.35,
      news_summary: 'Stable but slowing growth in key markets',
      risk_flags: [],
      price_data: {},
      fundamentals: {},
      sec_notes: '',
    },
  },
}

/**
 * Mocks the dashboard list and detail endpoints with standard test data.
 */
async function mockDashboardEndpoints(page: Page) {
  await page.route('**/api/dashboard', async (route: Route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockAnalyses),
      })
    } else {
      await route.continue()
    }
  })

  await page.route('**/api/dashboard/abc123', async (route: Route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 204, body: '' })
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockNvdaDetail),
      })
    }
  })

  await page.route('**/api/dashboard/def456', async (route: Route) => {
    if (route.request().method() === 'DELETE') {
      await route.fulfill({ status: 204, body: '' })
    } else {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockAaplDetail),
      })
    }
  })
}

/**
 * Mocks the dashboard list endpoint with an empty response (no analyses).
 */
async function mockEmptyDashboard(page: Page) {
  await page.route('**/api/dashboard', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })
}

test.describe('Dashboard page', () => {
  test('sidebar shows list of analyzed tickers', async ({ page }) => {
    await mockDashboardEndpoints(page)
    await page.goto('/dashboard')

    // Both tickers appear in the sidebar
    await expect(page.getByRole('button', { name: 'AAPL' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'NVDA' })).toBeVisible()
  })

  test('first ticker is selected by default on load', async ({ page }) => {
    await mockDashboardEndpoints(page)
    await page.goto('/dashboard')

    // Tickers are sorted alphabetically, so AAPL is first
    const aaplButton = page.getByRole('button', { name: 'AAPL' })
    await expect(aaplButton).toBeVisible()

    // The main panel should show AAPL's analysis
    await expect(page.getByRole('heading', { name: /AAPL/ })).toBeVisible()
  })

  test('clicking a ticker shows its analysis in the main panel', async ({ page }) => {
    await mockDashboardEndpoints(page)
    await page.goto('/dashboard')

    // Wait for initial load
    await expect(page.getByRole('button', { name: 'NVDA' })).toBeVisible()

    // Click NVDA in the sidebar
    await page.getByRole('button', { name: 'NVDA' }).click()

    // Main panel updates to show NVDA analysis
    await expect(page.getByRole('heading', { name: /NVDA/ })).toBeVisible()
  })

  test('search input filters the sidebar list', async ({ page }) => {
    await mockDashboardEndpoints(page)
    await page.goto('/dashboard')

    // Wait for list to load
    await expect(page.getByRole('button', { name: 'AAPL' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'NVDA' })).toBeVisible()

    // Type in the filter input
    const searchInput = page.getByLabel('Filter analyzed tickers')
    await searchInput.fill('NV')

    // Only NVDA should remain visible
    await expect(page.getByRole('button', { name: 'NVDA' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'AAPL' })).not.toBeVisible()
  })

  test('search with no results shows empty message', async ({ page }) => {
    await mockDashboardEndpoints(page)
    await page.goto('/dashboard')

    // Wait for list to load
    await expect(page.getByRole('button', { name: 'AAPL' })).toBeVisible()

    // Type a query that matches nothing
    const searchInput = page.getByLabel('Filter analyzed tickers')
    await searchInput.fill('ZZZZZ')

    // Empty state message appears
    await expect(page.getByText('No matches')).toBeVisible()

    // Neither ticker is visible
    await expect(page.getByRole('button', { name: 'AAPL' })).not.toBeVisible()
    await expect(page.getByRole('button', { name: 'NVDA' })).not.toBeVisible()
  })

  test('delete shows undo toast, clicking undo cancels deletion', async ({ page }) => {
    await mockDashboardEndpoints(page)
    await page.goto('/dashboard')

    // Wait for AAPL to be selected by default
    await expect(page.getByRole('heading', { name: /AAPL/ })).toBeVisible()

    // Click delete
    await page.getByRole('button', { name: /Delete/ }).click()

    // Undo toast appears
    await expect(page.getByText(/Deleted analysis for AAPL/)).toBeVisible()

    // Click undo
    await page.getByRole('button', { name: 'Undo' }).click()

    // Analysis is restored in the main panel
    await expect(page.getByRole('heading', { name: /AAPL/ })).toBeVisible()

    // Ticker is back in the sidebar
    await expect(page.getByRole('button', { name: 'AAPL' })).toBeVisible()
  })

  test('delete without undo removes the analysis after timeout', async ({ page }) => {
    let deleteRequested = false

    await page.route('**/api/dashboard', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockAnalyses),
      })
    })

    await page.route('**/api/dashboard/abc123', async (route: Route) => {
      if (route.request().method() === 'DELETE') {
        deleteRequested = true
        await route.fulfill({ status: 204, body: '' })
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(mockNvdaDetail),
        })
      }
    })

    await page.route('**/api/dashboard/def456', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockAaplDetail),
      })
    })

    await page.goto('/dashboard')

    // Select NVDA
    await expect(page.getByRole('button', { name: 'NVDA' })).toBeVisible()
    await page.getByRole('button', { name: 'NVDA' }).click()
    await expect(page.getByRole('heading', { name: /NVDA/ })).toBeVisible()

    // Click delete
    await page.getByRole('button', { name: /Delete/ }).click()

    // Toast appears
    await expect(page.getByText(/Deleted analysis for NVDA/)).toBeVisible()

    // NVDA is optimistically removed from sidebar
    await expect(page.getByRole('button', { name: 'NVDA' })).not.toBeVisible()

    // Wait for the 5.2s timer to fire the actual delete
    await page.waitForTimeout(5500)

    // The DELETE request was sent
    expect(deleteRequested).toBe(true)

    // Success toast appears
    await expect(page.getByText('Analysis deleted')).toBeVisible()
  })

  test('re-analyze link navigates to /analyze with ticker', async ({ page }) => {
    await mockDashboardEndpoints(page)
    await page.goto('/dashboard')

    // Wait for first ticker to be selected
    await expect(page.getByRole('heading', { name: /AAPL/ })).toBeVisible()

    // Click re-analyze link
    await page.getByRole('link', { name: /Re-analyze/ }).click()

    // Should navigate to analyze page with the ticker
    await expect(page).toHaveURL(/\/analyze\?tickers=AAPL/)
  })

  test('empty state shows link to watchlist when no analyses exist', async ({ page }) => {
    await mockEmptyDashboard(page)
    await page.goto('/dashboard')

    // Empty state messaging
    await expect(page.getByText('No analyses yet')).toBeVisible()

    // Watchlist link
    const watchlistLink = page.getByRole('button', { name: 'Watchlist' })
    await expect(watchlistLink).toBeVisible()

    // Click navigates to home
    await watchlistLink.click()
    await expect(page).toHaveURL(/^\/$/)
  })
})
