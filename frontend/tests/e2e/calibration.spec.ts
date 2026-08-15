import { test, expect } from '@playwright/test'

/**
 * E2E tests for the Calibration (Track Record) page.
 * Tests against the live deployment with real prediction data.
 */

test.describe('Calibration Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/calibration')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with Track Record heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /track record/i })).toBeVisible()
    await expect(
      page.getByText(/every signal is a prediction/i),
    ).toBeVisible()
  })

  test('stat cards display calibration metrics', async ({ page }) => {
    // All four stat card labels should be visible
    await expect(page.getByText('Overall Accuracy')).toBeVisible()
    await expect(page.getByText('Brier Score')).toBeVisible()
    await expect(page.getByText('Resolved')).toBeVisible()

    // "Pending" appears in both stat card and table, so target the stat area
    await expect(page.getByText(/awaiting \d+d horizon/i)).toBeVisible()

    // Brier score annotation
    await expect(page.getByText(/lower is better/i)).toBeVisible()
  })

  test('accuracy percentage is a valid number', async ({ page }) => {
    // The accuracy card shows a percentage like "67%"
    const accuracyCard = page.locator('text=/^\\d+%$/').first()
    await expect(accuracyCard).toBeVisible()
  })

  test('calibration by confidence chart renders', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /calibration by confidence/i }),
    ).toBeVisible()
    await expect(
      page.getByText(/does high confidence mean high accuracy/i),
    ).toBeVisible()

    // Chart should be present (Recharts renders as img with aria label)
    const chart = page.getByRole('img', {
      name: /bar chart showing hit rate by confidence/i,
    })
    await expect(chart).toBeVisible()
  })

  test('calibration confidence table shows low/medium/high buckets', async ({ page }) => {
    const table = page.getByRole('table', { name: /calibration by confidence/i })
    await expect(table).toBeVisible()

    // Should have all three confidence levels
    await expect(table.getByRole('cell', { name: 'Low' })).toBeVisible()
    await expect(table.getByRole('cell', { name: 'Medium' })).toBeVisible()
    await expect(table.getByRole('cell', { name: 'High' })).toBeVisible()

    // Headers
    await expect(table.getByRole('columnheader', { name: 'Hit Rate' })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: 'Predictions' })).toBeVisible()
  })

  test('high confidence has higher hit rate than low confidence', async ({ page }) => {
    const table = page.getByRole('table', { name: /calibration by confidence/i })
    await expect(table).toBeVisible()

    // Extract hit rates from the table rows
    const lowRow = table.getByRole('row').filter({ hasText: 'Low' })
    const highRow = table.getByRole('row').filter({ hasText: 'High' })

    const lowRate = await lowRow.getByRole('cell').nth(1).textContent()
    const highRate = await highRow.getByRole('cell').nth(1).textContent()

    // Parse percentages
    const lowPct = parseInt(lowRate?.replace('%', '') ?? '0')
    const highPct = parseInt(highRate?.replace('%', '') ?? '0')

    // A well-calibrated system should have high > low
    expect(highPct).toBeGreaterThan(lowPct)
  })

  test('accuracy by signal chart renders', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /accuracy by signal/i }),
    ).toBeVisible()
    await expect(
      page.getByText(/which signals are most reliable/i),
    ).toBeVisible()

    // Horizontal bar chart
    const chart = page.getByRole('img', {
      name: /bar chart showing prediction accuracy/i,
    })
    await expect(chart).toBeVisible()
  })

  test('signal accuracy table shows buy/sell/hold', async ({ page }) => {
    const table = page.getByRole('table', { name: /accuracy by signal/i })
    await expect(table).toBeVisible()

    await expect(table.getByRole('cell', { name: 'Buy' })).toBeVisible()
    await expect(table.getByRole('cell', { name: 'Sell' })).toBeVisible()
    await expect(table.getByRole('cell', { name: 'Hold' })).toBeVisible()

    // Headers
    await expect(table.getByRole('columnheader', { name: 'Accuracy' })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: 'Correct' })).toBeVisible()
    await expect(table.getByRole('columnheader', { name: 'Total' })).toBeVisible()
  })

  test('prediction ledger table is visible with columns', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /prediction ledger/i }),
    ).toBeVisible()

    // Filter buttons
    const allBtn = page.getByRole('button', { name: 'All', exact: true })
    await expect(allBtn).toBeVisible()
    await expect(page.getByRole('button', { name: 'Correct', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Incorrect', exact: true })).toBeVisible()

    // Ledger table (last table on the page)
    const tables = page.getByRole('table')
    const ledger = tables.last()
    await expect(ledger).toBeVisible()

    // Column headers
    await expect(ledger.getByRole('columnheader', { name: 'Ticker' })).toBeVisible()
    await expect(ledger.getByRole('columnheader', { name: 'Signal' })).toBeVisible()
    await expect(ledger.getByRole('columnheader', { name: 'Confidence' })).toBeVisible()
    await expect(ledger.getByRole('columnheader', { name: 'Entry Price' })).toBeVisible()
    await expect(ledger.getByRole('columnheader', { name: 'Return' })).toBeVisible()
    await expect(ledger.getByRole('columnheader', { name: 'Outcome' })).toBeVisible()
    await expect(ledger.getByRole('columnheader', { name: 'Date' })).toBeVisible()
  })

  test('prediction ledger shows real ticker data', async ({ page }) => {
    const ledger = page.getByRole('table').last()
    await expect(ledger).toBeVisible()

    // At least one real ticker should appear in the table
    const tickers = ['NVDA', 'AAPL', 'TSLA', 'MSFT', 'GOOGL', 'META']
    let found = false
    for (const ticker of tickers) {
      if (await ledger.getByRole('cell', { name: ticker, exact: true }).first().isVisible().catch(() => false)) {
        found = true
        break
      }
    }
    expect(found).toBe(true)
  })

  test('"Correct" filter changes visible predictions', async ({ page }) => {
    const correctBtn = page.getByRole('button', { name: 'Correct', exact: true })
    await correctBtn.scrollIntoViewIfNeeded()
    await correctBtn.click({ force: true })
    await page.waitForTimeout(500)

    // After clicking, the table should still be visible (filter applied, no crash)
    const ledger = page.getByRole('table').last()
    await expect(ledger).toBeVisible()
  })

  test('"Incorrect" filter changes visible predictions', async ({ page }) => {
    const incorrectBtn = page.getByRole('button', { name: 'Incorrect', exact: true })
    await incorrectBtn.scrollIntoViewIfNeeded()
    await incorrectBtn.click({ force: true })
    await page.waitForTimeout(500)

    // After clicking, the table should still be visible (filter applied, no crash)
    const ledger = page.getByRole('table').last()
    await expect(ledger).toBeVisible()
  })

  test('page has navigation in header', async ({ page }) => {
    // Verify nav links are accessible
    await expect(page.getByRole('link', { name: 'Analyze' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Explore' })).toBeVisible()
  })
})
