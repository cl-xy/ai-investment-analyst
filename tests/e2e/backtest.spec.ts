import { test, expect, type Page, type Route } from '@playwright/test'

const MOCK_SIGNALS = {
  signals: [
    { id: '1', ticker: 'NVDA', signal: 'buy', confidence: 'high', created_at: '2026-07-28T10:00:00Z' },
    { id: '2', ticker: 'AAPL', signal: 'hold', confidence: 'medium', created_at: '2026-07-27T14:00:00Z' },
    { id: '3', ticker: 'TSLA', signal: 'sell', confidence: 'high', created_at: '2026-07-26T09:00:00Z' },
    { id: '4', ticker: 'MSFT', signal: 'buy', confidence: 'high', created_at: '2026-07-25T11:00:00Z' },
    { id: '5', ticker: 'GOOGL', signal: 'hold', confidence: 'low', created_at: '2026-07-24T16:00:00Z' },
  ],
}

async function mockSignalsEndpoint(page: Page) {
  await page.route('**/api/signals/history', async (route: Route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(MOCK_SIGNALS),
    })
  })
}

test.describe('Backtest / Signal History page', () => {
  test.beforeEach(async ({ page }) => {
    await mockSignalsEndpoint(page)
    await page.goto('/backtest')
  })

  test.describe('Summary cards', () => {
    test('display correct counts', async ({ page }) => {
      const totalCard = page.getByRole('button', { name: 'Show all signals' })
      const buyCard = page.getByRole('button', { name: 'Filter by buy signals' })
      const holdCard = page.getByRole('button', { name: 'Filter by hold signals' })
      const sellCard = page.getByRole('button', { name: 'Filter by sell signals' })

      await expect(totalCard).toBeVisible()
      await expect(buyCard).toBeVisible()
      await expect(holdCard).toBeVisible()
      await expect(sellCard).toBeVisible()

      await expect(totalCard).toContainText('5')
      await expect(buyCard).toContainText('2')
      await expect(holdCard).toContainText('2')
      await expect(sellCard).toContainText('1')
    })
  })

  test.describe('Table rendering', () => {
    test('renders all signals with correct data', async ({ page }) => {
      const rows = page.locator('tbody tr')
      await expect(rows).toHaveCount(5)

      // Verify each ticker appears
      await expect(page.getByRole('cell', { name: 'NVDA' })).toBeVisible()
      await expect(page.getByRole('cell', { name: 'AAPL' })).toBeVisible()
      await expect(page.getByRole('cell', { name: 'TSLA' })).toBeVisible()
      await expect(page.getByRole('cell', { name: 'MSFT' })).toBeVisible()
      await expect(page.getByRole('cell', { name: 'GOOGL' })).toBeVisible()
    })
  })

  test.describe('Summary card filtering', () => {
    test('clicking Buy card filters to buy signals only', async ({ page }) => {
      const buyCard = page.getByRole('button', { name: 'Filter by buy signals' })
      await buyCard.click()

      await expect(buyCard).toHaveAttribute('aria-pressed', 'true')

      const rows = page.locator('tbody tr')
      await expect(rows).toHaveCount(2)

      await expect(page.getByRole('cell', { name: 'NVDA' })).toBeVisible()
      await expect(page.getByRole('cell', { name: 'MSFT' })).toBeVisible()
      await expect(page.getByRole('cell', { name: 'AAPL' })).not.toBeVisible()
      await expect(page.getByRole('cell', { name: 'TSLA' })).not.toBeVisible()
      await expect(page.getByRole('cell', { name: 'GOOGL' })).not.toBeVisible()
    })

    test('clicking Buy card again deactivates the filter', async ({ page }) => {
      const buyCard = page.getByRole('button', { name: 'Filter by buy signals' })

      // Activate
      await buyCard.click()
      await expect(buyCard).toHaveAttribute('aria-pressed', 'true')
      await expect(page.locator('tbody tr')).toHaveCount(2)

      // Deactivate
      await buyCard.click()
      await expect(buyCard).toHaveAttribute('aria-pressed', 'false')
      await expect(page.locator('tbody tr')).toHaveCount(5)
    })
  })

  test.describe('Search', () => {
    test('search input filters by ticker name', async ({ page }) => {
      const searchInput = page.getByLabel('Search signals by ticker')
      await searchInput.fill('NV')

      const rows = page.locator('tbody tr')
      await expect(rows).toHaveCount(1)
      await expect(page.getByRole('cell', { name: 'NVDA' })).toBeVisible()
    })

    test('search is case-insensitive', async ({ page }) => {
      const searchInput = page.getByLabel('Search signals by ticker')
      await searchInput.fill('aapl')

      const rows = page.locator('tbody tr')
      await expect(rows).toHaveCount(1)
      await expect(page.getByRole('cell', { name: 'AAPL' })).toBeVisible()
    })
  })

  test.describe('Column sorting', () => {
    test('clicking Ticker column header sorts ascending then descending', async ({ page }) => {
      const tickerHeader = page.getByRole('columnheader', { name: /Ticker/i })
      await tickerHeader.click()

      // First click: ascending
      const firstCells = page.locator('tbody tr td:first-child')
      const ascValues = await firstCells.allTextContents()
      const sortedAsc = [...ascValues].sort((a, b) => a.localeCompare(b))
      expect(ascValues).toEqual(sortedAsc)

      // Second click: descending
      await tickerHeader.click()
      const descValues = await firstCells.allTextContents()
      const sortedDesc = [...descValues].sort((a, b) => b.localeCompare(a))
      expect(descValues).toEqual(sortedDesc)
    })

    test('clicking Date column header sorts by date', async ({ page }) => {
      const dateHeader = page.getByRole('columnheader', { name: /Date/i })
      await dateHeader.click()

      // Table should reorder (ascending by date means oldest first)
      const rows = page.locator('tbody tr')
      await expect(rows).toHaveCount(5)

      // Second click: descending (newest first)
      await dateHeader.click()
      const firstRow = rows.first()
      await expect(firstRow).toContainText('NVDA')
    })
  })

  test.describe('Inline signal badge filter', () => {
    test('clicking signal badge in a row activates that signal filter', async ({ page }) => {
      // Click the inline buy badge in NVDA's row
      const nvdaRow = page.locator('tbody tr').filter({ hasText: 'NVDA' })
      const inlineBadge = nvdaRow.getByLabel('Filter by buy signals')
      await inlineBadge.click()

      // Only buy signals remain
      const rows = page.locator('tbody tr')
      await expect(rows).toHaveCount(2)
      await expect(page.getByRole('cell', { name: 'NVDA' })).toBeVisible()
      await expect(page.getByRole('cell', { name: 'MSFT' })).toBeVisible()
    })
  })

  test.describe('Filter pill', () => {
    test('filter pill appears when filtered and clear button removes it', async ({ page }) => {
      const sellCard = page.getByRole('button', { name: 'Filter by sell signals' })
      await sellCard.click()

      // Filter pill should be visible
      const clearButton = page.getByLabel('Clear signal filter')
      await expect(clearButton).toBeVisible()

      // Click clear to remove filter
      await clearButton.click()

      // All signals should be back
      await expect(page.locator('tbody tr')).toHaveCount(5)
      await expect(clearButton).not.toBeVisible()
    })
  })

  test.describe('Re-run link', () => {
    test('navigates to /analyze?tickers={TICKER}', async ({ page }) => {
      const nvdaRow = page.locator('tbody tr').filter({ hasText: 'NVDA' })
      const rerunLink = nvdaRow.getByRole('link', { name: /Re-run/i })
      await expect(rerunLink).toHaveAttribute('href', '/analyze?tickers=NVDA')

      await rerunLink.click()
      await expect(page).toHaveURL(/\/analyze\?tickers=NVDA/)
    })
  })

  test.describe('Combined filters', () => {
    test('search + signal filter work together', async ({ page }) => {
      // Filter by buy
      const buyCard = page.getByRole('button', { name: 'Filter by buy signals' })
      await buyCard.click()
      await expect(page.locator('tbody tr')).toHaveCount(2)

      // Then search within buy results
      const searchInput = page.getByLabel('Search signals by ticker')
      await searchInput.fill('MS')

      const rows = page.locator('tbody tr')
      await expect(rows).toHaveCount(1)
      await expect(page.getByRole('cell', { name: 'MSFT' })).toBeVisible()
    })
  })

  test.describe('Empty state', () => {
    test('shows empty state when search yields no results', async ({ page }) => {
      const searchInput = page.getByLabel('Search signals by ticker')
      await searchInput.fill('ZZZZZ')

      await expect(page.locator('tbody tr')).toHaveCount(0)
      await expect(page.getByText(/no signals/i)).toBeVisible()
    })

    test('shows empty state when filter + search yields no results', async ({ page }) => {
      // Filter by sell (only TSLA)
      const sellCard = page.getByRole('button', { name: 'Filter by sell signals' })
      await sellCard.click()

      // Search for something not in sell
      const searchInput = page.getByLabel('Search signals by ticker')
      await searchInput.fill('NVDA')

      await expect(page.locator('tbody tr')).toHaveCount(0)
      await expect(page.getByText(/no signals/i)).toBeVisible()
    })
  })
})
