import { test, expect } from '@playwright/test'

/**
 * E2E tests for the Eval (Quality Metrics) page against live deployment.
 */

test.describe('Eval Page', () => {
  test('page loads without crash', async ({ page }) => {
    await page.goto('/evals')
    await page.waitForLoadState('networkidle')
    // Page should render something (not blank)
    await expect(page.locator('body')).not.toBeEmpty()
  })

  test('page is accessible from History dropdown', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /history/i }).click()
    await page.getByRole('link', { name: /quality metrics/i }).click()
    await expect(page).toHaveURL(/\/evals/)
  })
})
