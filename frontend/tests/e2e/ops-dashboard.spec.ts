import { test, expect } from '@playwright/test'

/**
 * E2E tests for the Operations Dashboard page.
 * Tests against the live deployment with real ops data.
 */

test.describe('Ops Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/ops')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with correct heading', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /operations dashboard/i }),
    ).toBeVisible()
    await expect(
      page.getByText(/live system health/i),
    ).toBeVisible()
  })

  test('refresh button is present', async ({ page }) => {
    await expect(
      page.getByRole('button', { name: /refresh/i }),
    ).toBeVisible()
  })

  test('system health section shows status', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /system health/i }),
    ).toBeVisible()

    // Status badge (healthy/degraded/unhealthy)
    const statusBadge = page.getByText(/^(healthy|degraded|unhealthy)$/)
    await expect(statusBadge.first()).toBeVisible()

    // Individual health checks (use exact: true to avoid substring matches)
    await expect(page.getByText('api', { exact: true })).toBeVisible()
    await expect(page.getByText('database', { exact: true })).toBeVisible()
    await expect(page.getByText('llm provider', { exact: true })).toBeVisible()
    await expect(page.getByText('mcp servers', { exact: true })).toBeVisible()
  })

  test('SLO section shows availability and latency', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /service level objectives/i }),
    ).toBeVisible()

    // SLO metrics
    await expect(page.getByText('Availability')).toBeVisible()
    await expect(page.getByText('P95 Latency')).toBeVisible()
    await expect(page.getByText(/Error Budget/i)).toBeVisible()

    // Target values
    await expect(page.getByText('99.50%')).toBeVisible()
    await expect(page.getByText('120.0s')).toBeVisible()

    // Remaining budget percentage
    await expect(page.getByText(/remaining/i)).toBeVisible()
  })

  test('circuit breaker section shows state', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /circuit breakers/i }),
    ).toBeVisible()

    // At least one circuit breaker entry
    await expect(page.getByText('llm_api')).toBeVisible()

    // State should be one of: Closed, Open, Half-Open
    const state = page.getByText(/^(Closed|Open|Half-Open)$/)
    await expect(state.first()).toBeVisible()
  })

  test('rate limits section shows budget', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /rate limits/i }),
    ).toBeVisible()

    // Per minute and daily limits
    await expect(page.getByText(/Per Minute/i)).toBeVisible()
    await expect(page.getByText(/Daily/i)).toBeVisible()

    // Shows format like "0 / 5" or "N / M"
    const ratioText = page.getByText(/\d+ \/ \d+/)
    await expect(ratioText.first()).toBeVisible()
  })

  test('chaos mode section shows injection controls', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /chaos mode/i }),
    ).toBeVisible()
    await expect(
      page.getByText(/inject failures/i),
    ).toBeVisible()

    // Four chaos scenarios
    await expect(page.getByText(/Llm Timeout/i)).toBeVisible()
    await expect(page.getByText(/Mcp Failure/i)).toBeVisible()
    await expect(page.getByText(/Rate Limit Exhausted/i)).toBeVisible()
    await expect(page.getByText(/Slow Response/i)).toBeVisible()

    // Each has an enable button
    const enableButtons = page.getByRole('button', { name: /enable/i })
    await expect(enableButtons).toHaveCount(4)
  })

  test('recent errors section exists', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /recent errors/i }),
    ).toBeVisible()

    // Either shows errors or "No recent errors"
    await expect(page.getByText(/no recent errors/i).or(
      page.locator('[class*="error"]'),
    ).first()).toBeVisible()
  })

  test('cost attribution section shows data', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /cost attribution/i }),
    ).toBeVisible()

    // Table column headers for cost table
    await expect(page.getByText('Ticker', { exact: true })).toBeVisible()
    await expect(page.getByText('Analyses', { exact: true })).toBeVisible()
    await expect(page.getByText('Tokens', { exact: true })).toBeVisible()
  })

  test('refresh button does not crash the page', async ({ page }) => {
    const refreshBtn = page.getByRole('button', { name: /refresh/i })
    await refreshBtn.click({ force: true })

    // Wait for any loading to complete
    await page.waitForTimeout(2000)

    // Should still show healthy data after refresh (no crash)
    await expect(
      page.getByRole('heading', { name: /system health/i }),
    ).toBeVisible()
  })
})
