import { test, expect } from '@playwright/test'

/**
 * E2E tests for the Dashboard (Past Analyses) page against live deployment.
 */

test.describe('Dashboard Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000) // Allow API call to complete
  })

  test('page loads and shows content', async ({ page }) => {
    // Should show either empty state or the ticker sidebar
    const content = page.getByRole('heading', { name: /no analyses yet/i })
      .or(page.getByText(/stocks/i))
    await expect(content.first()).toBeVisible({ timeout: 10000 })
  })

  test('shows ticker list in sidebar when analyses exist', async ({ page }) => {
    const stocksHeading = page.getByText(/^stocks$/i)
    if (await stocksHeading.isVisible({ timeout: 3000 }).catch(() => false)) {
      // At least one ticker button should exist
      const tickerBtn = page.locator('aside button, ul button').first()
      await expect(tickerBtn).toBeVisible()
    }
  })

  test('ticker buttons are clickable', async ({ page }) => {
    const tickerBtn = page.locator('aside button, ul button').first()
    if (await tickerBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
      await tickerBtn.click()
      // After clicking, the main area should update
      await page.waitForTimeout(1000)
      const mainContent = page.locator('.flex-1')
      await expect(mainContent.first()).toBeVisible()
    }
  })

  test('empty state has link back to watchlist', async ({ page }) => {
    const emptyState = page.getByRole('heading', { name: /no analyses yet/i })
    if (await emptyState.isVisible({ timeout: 3000 }).catch(() => false)) {
      await expect(page.getByText(/watchlist/i)).toBeVisible()
    }
  })
})
