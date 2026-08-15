import { test, expect } from '@playwright/test'

/**
 * E2E tests for the Trace Replay page.
 * Tests against the live deployment with real durable traces.
 */

test.describe('Trace Replay Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/replay')
    await page.waitForLoadState('networkidle')
  })

  test('page loads with correct heading', async ({ page }) => {
    await expect(
      page.getByRole('heading', { name: /trace replay/i }),
    ).toBeVisible()
    await expect(
      page.getByText(/step through recorded analyses/i),
    ).toBeVisible()
  })

  test('featured demo button is present', async ({ page }) => {
    await expect(page.getByText(/featured demo/i)).toBeVisible()
    await expect(
      page.getByText(/pre-cached analysis/i),
    ).toBeVisible()
  })

  test('trace list shows recorded analyses', async ({ page }) => {
    // Should have at least one trace entry with a ticker name
    const traceEntry = page.locator('button', { hasText: /NVDA|AAPL|TSLA|GOOGL|SE|MSFT/i })
    await expect(traceEntry.first()).toBeVisible({ timeout: 10000 })
  })

  test('trace entries show metadata (date, duration, signal)', async ({ page }) => {
    // Each trace entry shows duration in seconds
    const durationPattern = page.getByText(/\d+\.\d+s/)
    await expect(durationPattern.first()).toBeVisible()

    // Signal badges (buy/sell/hold)
    const signal = page.getByText(/^(buy|sell|hold|insufficient_data)$/)
    await expect(signal.first()).toBeVisible()
  })

  test('trace entries show status (success/failed/degraded)', async ({ page }) => {
    const status = page.getByText(/^(success|failed|degraded)$/)
    await expect(status.first()).toBeVisible()
  })

  test('filter input is present', async ({ page }) => {
    await expect(
      page.getByPlaceholder(/filter by ticker/i),
    ).toBeVisible()
  })

  test('filter narrows trace list by ticker', async ({ page }) => {
    const filterInput = page.getByPlaceholder(/filter by ticker/i)

    // Count total entries before filter
    const entriesBefore = page.locator('button', { hasText: /\d+\.\d+s/ })
    const countBefore = await entriesBefore.count()

    await filterInput.fill('NVDA')

    // Wait for filter to apply
    await page.waitForTimeout(500)

    // Remaining entries should be fewer than or equal to before
    const entriesAfter = page.locator('button', { hasText: /\d+\.\d+s/ })
    const countAfter = await entriesAfter.count()

    // Filter should have narrowed the list (or same if all are NVDA)
    expect(countAfter).toBeLessThanOrEqual(countBefore)
    expect(countAfter).toBeGreaterThan(0)
  })

  test('clicking a trace opens replay view with controls', async ({ page }) => {
    // Use dispatchEvent to bypass body pointer-events interception
    const firstTrace = page.locator('button', { hasText: /\d+\.\d+s/ }).first()
    await firstTrace.dispatchEvent('click')

    // Replay view should appear with "Replaying" header
    await expect(page.getByText(/replaying/i)).toBeVisible({ timeout: 10000 })

    // Playback controls should be visible
    await expect(page.getByRole('button', { name: /play/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /step forward/i })).toBeVisible()

    // Event counter
    await expect(page.getByText(/event \d+ \/ \d+/i)).toBeVisible()

    // Speed controls
    await expect(page.getByRole('button', { name: '1x' })).toBeVisible()
    await expect(page.getByRole('button', { name: '2x' })).toBeVisible()
    await expect(page.getByRole('button', { name: '4x' })).toBeVisible()

    // Replay slider
    await expect(page.getByRole('slider', { name: /replay position/i })).toBeVisible()
  })

  test('replay view shows original duration', async ({ page }) => {
    const firstTrace = page.locator('button', { hasText: /\d+\.\d+s/ }).first()
    await firstTrace.dispatchEvent('click')

    await expect(page.getByText(/original duration/i)).toBeVisible({ timeout: 10000 })
  })

  test('back button returns to trace list', async ({ page }) => {
    const firstTrace = page.locator('button', { hasText: /\d+\.\d+s/ }).first()
    await firstTrace.dispatchEvent('click')

    // Wait for replay view
    await expect(page.getByText(/replaying/i)).toBeVisible({ timeout: 10000 })

    // Click back
    await page.getByRole('button', { name: /back to traces/i }).dispatchEvent('click')

    // Should be back at trace list
    await expect(
      page.getByRole('heading', { name: /trace replay/i }),
    ).toBeVisible()
  })

  test('step forward advances replay position', async ({ page }) => {
    const firstTrace = page.locator('button', { hasText: /\d+\.\d+s/ }).first()
    await firstTrace.dispatchEvent('click')

    // Wait for replay view
    await expect(
      page.getByRole('button', { name: /step forward/i }),
    ).toBeVisible({ timeout: 10000 })

    // Step forward
    await page.getByRole('button', { name: /step forward/i }).dispatchEvent('click')

    // Event counter should show position > 0
    await expect(page.getByText(/event [1-9]\d* \//i)).toBeVisible()
  })
})
