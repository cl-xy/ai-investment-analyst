import { test, expect } from '@playwright/test'

/**
 * E2E tests for the 404 Not Found page.
 * Covers: rendering, navigation back to home.
 */

test.describe('404 Not Found', () => {
  test('shows 404 page for unknown routes', async ({ page }) => {
    await page.goto('/this-page-does-not-exist')
    await expect(page.getByRole('heading', { name: /page not found/i })).toBeVisible()
  })

  test('shows descriptive text', async ({ page }) => {
    await page.goto('/unknown-route')
    await expect(page.getByText(/doesn't exist or has been moved/i)).toBeVisible()
  })

  test('shows Go Home link', async ({ page }) => {
    await page.goto('/random')
    await expect(page.getByRole('link', { name: /go home/i })).toBeVisible()
  })

  test('Go Home link navigates to /', async ({ page }) => {
    await page.goto('/nope')
    await page.getByRole('link', { name: /go home/i }).click()
    await expect(page).toHaveURL('/')
  })
})
