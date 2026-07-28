import { test, expect } from '@playwright/test'

/**
 * E2E tests for the Streaming Analysis page.
 * Covers: pre-flight confirmation, navigation, ticker display, error states, skeleton loading.
 * Note: actual SSE streaming requires a running backend; these test the UI states.
 */

test.describe('Streaming Analysis Page', () => {
  test.describe('No Tickers', () => {
    test('shows error when no tickers in URL', async ({ page }) => {
      await page.goto('/analyze')
      await expect(page.getByText(/no tickers specified/i)).toBeVisible()
    })

    test('shows "go back to watchlist" link', async ({ page }) => {
      await page.goto('/analyze')
      await expect(page.getByRole('button', { name: /go back to watchlist/i })).toBeVisible()
    })

    test('go back button navigates to home', async ({ page }) => {
      await page.goto('/analyze')
      await page.getByRole('button', { name: /go back to watchlist/i }).click()
      await expect(page).toHaveURL('/')
    })
  })

  test.describe('Pre-flight Confirmation', () => {
    test('shows confirmation screen with ticker pills', async ({ page }) => {
      await page.goto('/analyze?tickers=NVDA')
      await expect(page.getByRole('heading', { name: /ready to analyze/i })).toBeVisible()
      await expect(page.getByText('NVDA')).toBeVisible()
    })

    test('shows multiple tickers in confirmation', async ({ page }) => {
      await page.goto('/analyze?tickers=NVDA,AAPL')
      await expect(page.getByText('NVDA')).toBeVisible()
      await expect(page.getByText('AAPL')).toBeVisible()
    })

    test('shows time estimate', async ({ page }) => {
      await page.goto('/analyze?tickers=NVDA')
      await expect(page.getByText(/seconds per ticker/i)).toBeVisible()
    })

    test('shows Start Analysis button', async ({ page }) => {
      await page.goto('/analyze?tickers=NVDA')
      await expect(page.getByRole('button', { name: /start analysis/i })).toBeVisible()
    })

    test('shows Back to watchlist link', async ({ page }) => {
      await page.goto('/analyze?tickers=NVDA')
      await expect(page.getByRole('link', { name: /back to watchlist/i })).toBeVisible()
    })

    test('back link navigates to home', async ({ page }) => {
      await page.goto('/analyze?tickers=NVDA')
      await page.getByRole('link', { name: /back to watchlist/i }).click()
      await expect(page).toHaveURL('/')
    })
  })

  test.describe('After Confirmation (Streaming UI)', () => {
    test('clicking Start Analysis shows streaming layout', async ({ page }) => {
      await page.goto('/analyze?tickers=NVDA')
      await page.getByRole('button', { name: /start analysis/i }).click()
      // Should show the main analysis layout (back button, heading, trace panel)
      await expect(page.getByRole('heading', { name: /analyzing nvda/i })).toBeVisible()
    })

    test('shows Back button during analysis', async ({ page }) => {
      await page.goto('/analyze?tickers=NVDA')
      await page.getByRole('button', { name: /start analysis/i }).click()
      await expect(page.getByRole('button', { name: /back/i })).toBeVisible()
    })

    test('shows skeleton cards for pending tickers', async ({ page }) => {
      await page.goto('/analyze?tickers=NVDA,AAPL')
      await page.getByRole('button', { name: /start analysis/i }).click()
      // Skeleton cards should be visible for both tickers
      const skeletons = page.locator('.animate-shimmer')
      await expect(skeletons.first()).toBeVisible()
    })

    test('shows analyzing heading after start', async ({ page }) => {
      await page.goto('/analyze?tickers=NVDA')
      await page.getByRole('button', { name: /start analysis/i }).click()
      await expect(page.getByRole('heading', { name: /analyzing nvda/i })).toBeVisible()
    })

    test('sets document title during analysis', async ({ page }) => {
      await page.goto('/analyze?tickers=NVDA')
      await page.getByRole('button', { name: /start analysis/i }).click()
      await expect(page).toHaveTitle(/analyzing nvda/i)
    })
  })
})
