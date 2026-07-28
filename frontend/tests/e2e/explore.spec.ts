import { test, expect } from '@playwright/test'

/**
 * E2E tests for the Explore (Trending Stocks) page against live deployment.
 */

test.describe('Explore Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/explore')
  })

  test('renders page heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /trending stocks/i })).toBeVisible()
  })

  test('renders description text', async ({ page }) => {
    await expect(page.getByText(/most-watched us stocks/i)).toBeVisible()
  })

  test('renders table header row', async ({ page }) => {
    await expect(page.getByText('Ticker')).toBeVisible()
    await expect(page.getByText('Price')).toBeVisible()
    await expect(page.getByText('Change')).toBeVisible()
  })

  test('shows stock rows, empty message, or error', async ({ page }) => {
    const content = page.locator('[role="button"][aria-expanded]')
      .or(page.getByText(/no trending stocks available/i))
      .or(page.getByText(/failed to load/i))
    await expect(content.first()).toBeVisible({ timeout: 15000 })
  })

  test('stock rows are expandable', async ({ page }) => {
    const row = page.locator('[role="button"][aria-expanded]').first()
    if (await row.isVisible()) {
      await expect(row).toHaveAttribute('aria-expanded', 'false')
      await row.click()
      await expect(row).toHaveAttribute('aria-expanded', 'true')
    }
  })

  test('expanded row shows detail panel', async ({ page }) => {
    const row = page.locator('[role="button"][aria-expanded]').first()
    if (await row.isVisible()) {
      await row.click()
      // Detail panel should appear with analyze link or industry info
      await expect(page.getByRole('link', { name: /analyze/i }).first()).toBeVisible({ timeout: 10000 })
    }
  })

  test('clicking same row collapses it', async ({ page }) => {
    const row = page.locator('[role="button"][aria-expanded]').first()
    if (await row.isVisible()) {
      await row.click()
      await expect(row).toHaveAttribute('aria-expanded', 'true')
      await row.click()
      await expect(row).toHaveAttribute('aria-expanded', 'false')
    }
  })

  test('rows are keyboard accessible', async ({ page }) => {
    const row = page.locator('[role="button"][aria-expanded]').first()
    if (await row.isVisible()) {
      await expect(row).toHaveAttribute('tabindex', '0')
    }
  })
})
