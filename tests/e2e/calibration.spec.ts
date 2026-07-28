import { test, expect, type Page, type Route } from '@playwright/test'

const mockCalibrationResponse = {
  stats: {
    accuracy: 0.72,
    brier_score: 0.18,
    resolved: 25,
    pending: 8,
  },
  by_confidence: [
    { level: 'high', correct: 12, total: 15, accuracy: 0.8 },
    { level: 'medium', correct: 5, total: 8, accuracy: 0.625 },
    { level: 'low', correct: 1, total: 2, accuracy: 0.5 },
  ],
  by_signal: [
    { signal: 'buy', correct: 10, total: 14, accuracy: 0.714 },
    { signal: 'hold', correct: 6, total: 8, accuracy: 0.75 },
    { signal: 'sell', correct: 2, total: 3, accuracy: 0.667 },
  ],
  predictions: [
    { id: '1', ticker: 'NVDA', signal: 'buy', confidence: 'high', predicted_at: '2026-06-01', resolved_at: '2026-07-01', correct: true, actual_return: 0.15 },
    { id: '2', ticker: 'AAPL', signal: 'hold', confidence: 'medium', predicted_at: '2026-06-15', resolved_at: '2026-07-15', correct: true, actual_return: 0.02 },
    { id: '3', ticker: 'TSLA', signal: 'buy', confidence: 'high', predicted_at: '2026-06-20', resolved_at: '2026-07-20', correct: false, actual_return: -0.08 },
    { id: '4', ticker: 'META', signal: 'sell', confidence: 'medium', predicted_at: '2026-07-01', resolved_at: null, correct: null, actual_return: null },
  ],
}

const emptyCalibrationResponse = {
  stats: {
    accuracy: 0,
    brier_score: 0,
    resolved: 0,
    pending: 0,
  },
  by_confidence: [],
  by_signal: [],
  predictions: [],
}

async function mockCalibrationEndpoint(page: Page, response = mockCalibrationResponse) {
  await page.route('**/api/calibration', async (route: Route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(response),
    })
  })
}

test.describe('Calibration page', () => {
  test.beforeEach(async ({ page }) => {
    await mockCalibrationEndpoint(page)
  })

  test('stat cards display correct values', async ({ page }) => {
    await page.goto('/calibration')

    await expect(page.getByText('72%')).toBeVisible()
    await expect(page.getByText('0.18')).toBeVisible()
    await expect(page.getByText('25')).toBeVisible()
    await expect(page.getByText('8')).toBeVisible()

    await expect(page.getByText('Overall Accuracy')).toBeVisible()
    await expect(page.getByText('Brier Score')).toBeVisible()
    await expect(page.getByText('Resolved')).toBeVisible()
    await expect(page.getByText('Pending')).toBeVisible()
  })

  test('calibration chart renders', async ({ page }) => {
    await page.goto('/calibration')

    // Chart container or SVG element for the calibration bar chart
    const chartContainer = page.locator('[data-testid="calibration-chart"], .recharts-wrapper, svg').first()
    await expect(chartContainer).toBeVisible()
  })

  test('signal accuracy chart renders', async ({ page }) => {
    await page.goto('/calibration')

    // Signal accuracy horizontal bar chart
    const signalChart = page.locator('[data-testid="signal-accuracy-chart"], .recharts-wrapper, svg').nth(1)
    await expect(signalChart).toBeVisible()
  })

  test('prediction ledger shows all predictions', async ({ page }) => {
    await page.goto('/calibration')

    const table = page.getByRole('table')
    await expect(table).toBeVisible()

    // All 4 predictions should be visible
    await expect(table.getByText('NVDA')).toBeVisible()
    await expect(table.getByText('AAPL')).toBeVisible()
    await expect(table.getByText('TSLA')).toBeVisible()
    await expect(table.getByText('META')).toBeVisible()
  })

  test('"All" filter shows all predictions', async ({ page }) => {
    await page.goto('/calibration')

    const allButton = page.getByRole('button', { name: /All/i })
    await allButton.click()

    const table = page.getByRole('table')
    await expect(table.getByText('NVDA')).toBeVisible()
    await expect(table.getByText('AAPL')).toBeVisible()
    await expect(table.getByText('TSLA')).toBeVisible()
    await expect(table.getByText('META')).toBeVisible()
  })

  test('"Correct" filter shows only correct predictions', async ({ page }) => {
    await page.goto('/calibration')

    const correctButton = page.getByRole('button', { name: /Correct/i })
    await correctButton.click()

    const table = page.getByRole('table')
    await expect(table.getByText('NVDA')).toBeVisible()
    await expect(table.getByText('AAPL')).toBeVisible()
    await expect(table.getByText('TSLA')).not.toBeVisible()
    await expect(table.getByText('META')).not.toBeVisible()
  })

  test('"Incorrect" filter shows only incorrect predictions', async ({ page }) => {
    await page.goto('/calibration')

    const incorrectButton = page.getByRole('button', { name: /Incorrect/i })
    await incorrectButton.click()

    const table = page.getByRole('table')
    await expect(table.getByText('TSLA')).toBeVisible()
    await expect(table.getByText('NVDA')).not.toBeVisible()
    await expect(table.getByText('AAPL')).not.toBeVisible()
    await expect(table.getByText('META')).not.toBeVisible()
  })

  test('pending predictions show "Pending" status', async ({ page }) => {
    await page.goto('/calibration')

    const table = page.getByRole('table')
    const metaRow = table.locator('tr', { hasText: 'META' })
    await expect(metaRow).toBeVisible()
    await expect(metaRow.getByText(/Pending/i)).toBeVisible()
  })
})

test.describe('Calibration page - empty state', () => {
  test('shows empty state when no predictions exist', async ({ page }) => {
    await mockCalibrationEndpoint(page, emptyCalibrationResponse)
    await page.goto('/calibration')

    // Empty state message should be visible
    await expect(
      page.getByText(/no predictions|no data|no calibration/i),
    ).toBeVisible()
  })
})
