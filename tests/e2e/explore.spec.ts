import { test, expect, type Page, type Route } from '@playwright/test'

const MOCK_TRENDING_RESPONSE = {
  stocks: [
    {
      ticker: 'NVDA',
      name: 'NVIDIA Corporation',
      price: 125.5,
      change_pct: 4.2,
      volume: 85000000,
      industry: 'Semiconductors',
      description: 'Leading GPU and AI chip maker powering the artificial intelligence revolution.',
      trending_reasons: [
        'AI demand surge',
        'Record data center revenue',
        'New chip architecture',
      ],
      price_history: Array.from({ length: 30 }, (_, i) => ({
        date: `2026-${String(6 + Math.floor((28 + i) / 30)).padStart(2, '0')}-${String(((28 + i) % 30) + 1).padStart(2, '0')}`,
        close: 110 + i * 0.5,
      })),
    },
    {
      ticker: 'AAPL',
      name: 'Apple Inc.',
      price: 198.75,
      change_pct: -1.3,
      volume: 62000000,
      industry: 'Consumer Electronics',
      description: 'Consumer technology company known for iPhone, Mac, and services ecosystem.',
      trending_reasons: [
        'Vision Pro sales data',
        'Services revenue milestone',
      ],
      price_history: Array.from({ length: 30 }, (_, i) => ({
        date: `2026-${String(6 + Math.floor((28 + i) / 30)).padStart(2, '0')}-${String(((28 + i) % 30) + 1).padStart(2, '0')}`,
        close: 190 + i * 0.3,
      })),
    },
    {
      ticker: 'TSLA',
      name: 'Tesla, Inc.',
      price: 265.0,
      change_pct: 2.8,
      volume: 74000000,
      industry: 'Electric Vehicles',
      description: 'Electric vehicle and clean energy company.',
      trending_reasons: [
        'Robotaxi launch timeline',
        'Q2 delivery beat',
        'Energy storage growth',
      ],
      price_history: Array.from({ length: 30 }, (_, i) => ({
        date: `2026-${String(6 + Math.floor((28 + i) / 30)).padStart(2, '0')}-${String(((28 + i) % 30) + 1).padStart(2, '0')}`,
        close: 240 + i * 0.8,
      })),
    },
  ],
}

/**
 * Mocks the trending endpoint with a configurable delay to test loading states.
 */
async function mockTrendingEndpoint(
  page: Page,
  options: { delay?: number; error?: boolean } = {},
) {
  await page.route('**/api/explore/trending', async (route: Route) => {
    if (options.error) {
      await route.abort('connectionrefused')
      return
    }

    if (options.delay) {
      await new Promise((resolve) => setTimeout(resolve, options.delay))
    }

    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(MOCK_TRENDING_RESPONSE),
    })
  })
}

test.describe('Explore page', () => {
  test('loading skeleton shows while fetching', async ({ page }) => {
    await mockTrendingEndpoint(page, { delay: 2000 })
    await page.goto('/explore')

    // Skeleton placeholders should be visible during load
    const skeletons = page.locator('[data-testid="skeleton"], .animate-pulse')
    await expect(skeletons.first()).toBeVisible({ timeout: 3000 })

    // After data loads, skeletons should disappear
    await expect(skeletons.first()).not.toBeVisible({ timeout: 5000 })
  })

  test('trending stocks table renders with correct data', async ({ page }) => {
    await mockTrendingEndpoint(page)
    await page.goto('/explore')

    // Table should be visible
    const table = page.getByRole('table')
    await expect(table).toBeVisible({ timeout: 5000 })

    // Verify column headers
    await expect(page.getByRole('columnheader', { name: /rank/i })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: /ticker/i })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: /name/i })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: /price/i })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: /change/i })).toBeVisible()
    await expect(page.getByRole('columnheader', { name: /volume/i })).toBeVisible()

    // Verify first row data
    await expect(page.getByText('NVDA')).toBeVisible()
    await expect(page.getByText('NVIDIA Corporation')).toBeVisible()
    await expect(page.getByText('125.50')).toBeVisible()
    await expect(page.getByText('4.2')).toBeVisible()

    // Verify second row data
    await expect(page.getByText('AAPL')).toBeVisible()
    await expect(page.getByText('Apple Inc.')).toBeVisible()

    // Verify third row data
    await expect(page.getByText('TSLA')).toBeVisible()
    await expect(page.getByText('Tesla, Inc.')).toBeVisible()
  })

  test('click on row expands detail panel', async ({ page }) => {
    await mockTrendingEndpoint(page)
    await page.goto('/explore')

    // Wait for table to load
    await expect(page.getByText('NVDA')).toBeVisible({ timeout: 5000 })

    // Find the expandable row for NVDA
    const nvdaRow = page.getByRole('button', { name: /NVDA.*NVIDIA/i })
    await expect(nvdaRow).toHaveAttribute('aria-expanded', 'false')

    // Click to expand
    await nvdaRow.click()
    await expect(nvdaRow).toHaveAttribute('aria-expanded', 'true')
  })

  test('expanded detail shows chart, reasons, and analyze link', async ({ page }) => {
    await mockTrendingEndpoint(page)
    await page.goto('/explore')

    // Wait for data and expand NVDA row
    const nvdaRow = page.getByRole('button', { name: /NVDA.*NVIDIA/i })
    await expect(nvdaRow).toBeVisible({ timeout: 5000 })
    await nvdaRow.click()

    // Industry should be visible
    await expect(page.getByText('Semiconductors')).toBeVisible()

    // Description should be visible
    await expect(
      page.getByText(/Leading GPU and AI chip maker/),
    ).toBeVisible()

    // Price chart (svg or canvas element within the detail)
    const chart = page.locator('svg, canvas').first()
    await expect(chart).toBeVisible()

    // "Why It's Trending" reasons
    await expect(page.getByText('AI demand surge')).toBeVisible()
    await expect(page.getByText('Record data center revenue')).toBeVisible()
    await expect(page.getByText('New chip architecture')).toBeVisible()

    // "Analyze NVDA" link
    const analyzeLink = page.getByRole('link', { name: /Analyze NVDA/i })
    await expect(analyzeLink).toBeVisible()
  })

  test('click expanded row again collapses it', async ({ page }) => {
    await mockTrendingEndpoint(page)
    await page.goto('/explore')

    const nvdaRow = page.getByRole('button', { name: /NVDA.*NVIDIA/i })
    await expect(nvdaRow).toBeVisible({ timeout: 5000 })

    // Expand
    await nvdaRow.click()
    await expect(nvdaRow).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByText('Semiconductors')).toBeVisible()

    // Collapse
    await nvdaRow.click()
    await expect(nvdaRow).toHaveAttribute('aria-expanded', 'false')
    await expect(page.getByText('Semiconductors')).not.toBeVisible()
  })

  test('only one row expanded at a time', async ({ page }) => {
    await mockTrendingEndpoint(page)
    await page.goto('/explore')

    const nvdaRow = page.getByRole('button', { name: /NVDA.*NVIDIA/i })
    const aaplRow = page.getByRole('button', { name: /AAPL.*Apple/i })
    await expect(nvdaRow).toBeVisible({ timeout: 5000 })

    // Expand NVDA
    await nvdaRow.click()
    await expect(nvdaRow).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByText('Semiconductors')).toBeVisible()

    // Expand AAPL (should collapse NVDA)
    await aaplRow.click()
    await expect(aaplRow).toHaveAttribute('aria-expanded', 'true')
    await expect(nvdaRow).toHaveAttribute('aria-expanded', 'false')

    // AAPL detail visible, NVDA detail hidden
    await expect(page.getByText('Consumer Electronics')).toBeVisible()
    await expect(page.getByText('Semiconductors')).not.toBeVisible()
  })

  test('keyboard navigation: Enter and Space expand rows', async ({ page }) => {
    await mockTrendingEndpoint(page)
    await page.goto('/explore')

    const nvdaRow = page.getByRole('button', { name: /NVDA.*NVIDIA/i })
    await expect(nvdaRow).toBeVisible({ timeout: 5000 })

    // Focus the row
    await nvdaRow.focus()

    // Press Enter to expand
    await page.keyboard.press('Enter')
    await expect(nvdaRow).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByText('Semiconductors')).toBeVisible()

    // Press Enter again to collapse
    await page.keyboard.press('Enter')
    await expect(nvdaRow).toHaveAttribute('aria-expanded', 'false')

    // Press Space to expand
    await page.keyboard.press('Space')
    await expect(nvdaRow).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByText('Semiconductors')).toBeVisible()
  })

  test('"Analyze TICKER" link navigates to /analyze?tickers=TICKER', async ({ page }) => {
    await mockTrendingEndpoint(page)
    await page.goto('/explore')

    // Expand NVDA row
    const nvdaRow = page.getByRole('button', { name: /NVDA.*NVIDIA/i })
    await expect(nvdaRow).toBeVisible({ timeout: 5000 })
    await nvdaRow.click()

    // Click the analyze link
    const analyzeLink = page.getByRole('link', { name: /Analyze NVDA/i })
    await expect(analyzeLink).toBeVisible()
    await analyzeLink.click()

    // Should navigate to analyze page with the ticker
    await expect(page).toHaveURL(/\/analyze\?tickers=NVDA/)
  })

  test('error state shows retry button', async ({ page }) => {
    await mockTrendingEndpoint(page, { error: true })
    await page.goto('/explore')

    // Error message should appear
    await expect(
      page.getByText(/failed|error|couldn't load/i),
    ).toBeVisible({ timeout: 10_000 })

    // Retry button should be visible
    await expect(
      page.getByRole('button', { name: /Retry/i }),
    ).toBeVisible()
  })

  test('retry button fetches data again', async ({ page }) => {
    // First request fails, second succeeds
    let requestCount = 0
    await page.route('**/api/explore/trending', async (route: Route) => {
      requestCount++
      if (requestCount === 1) {
        await route.abort('connectionrefused')
      } else {
        await route.fulfill({
          status: 200,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(MOCK_TRENDING_RESPONSE),
        })
      }
    })

    await page.goto('/explore')

    // Wait for error state
    await expect(
      page.getByRole('button', { name: /Retry/i }),
    ).toBeVisible({ timeout: 10_000 })

    // Click retry
    await page.getByRole('button', { name: /Retry/i }).click()

    // Table should now render with data
    await expect(page.getByText('NVDA')).toBeVisible({ timeout: 5000 })
    await expect(page.getByText('NVIDIA Corporation')).toBeVisible()

    // Verify retry actually fired a second request
    expect(requestCount).toBe(2)
  })
})
