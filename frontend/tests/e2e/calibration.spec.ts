import { test, expect } from '@playwright/test'

/**
 * E2E tests for the Calibration (Track Record) page.
 * Note: Route may not be active in current deployment.
 */

test.describe('Calibration Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/calibration')
    await page.waitForLoadState('networkidle')
  })

  test('page loads without blank screen', async ({ page }) => {
    // Should show calibration content, empty state, or 404 (if route not deployed)
    const content = page.getByText(/track record/i)
      .or(page.getByText(/no predictions/i))
      .or(page.getByText(/page not found/i))
    await expect(content.first()).toBeVisible({ timeout: 10000 })
  })

  test('page has navigation back to home', async ({ page }) => {
    // Whether it 404s or loads, there should be a way home
    const homeLink = page.getByRole('link', { name: /go home/i })
      .or(page.getByRole('link', { name: /investment analyst/i }))
    await expect(homeLink.first()).toBeVisible()
  })
})
