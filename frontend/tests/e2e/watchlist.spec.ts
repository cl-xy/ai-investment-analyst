import { test, expect, type Page } from '@playwright/test'

/**
 * E2E tests for the Watchlist page (home page).
 * Covers: ticker input, validation, add/remove, demo CTA, analyze flow, suggestions, welcome banner.
 */

test.describe('Watchlist Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    // Clear localStorage to get fresh state each test
    await page.evaluate(() => localStorage.clear())
    await page.reload()
    await page.waitForLoadState('networkidle')
  })

  test.describe('Page Load', () => {
    test('renders hero heading', async ({ page }) => {
      await expect(page.getByRole('heading', { name: /what stocks are you watching/i })).toBeVisible()
    })

    test('renders ticker input with correct placeholder', async ({ page }) => {
      await expect(page.getByLabel('Ticker symbol input')).toBeVisible()
      await expect(page.getByLabel('Ticker symbol input')).toHaveAttribute('placeholder', /enter ticker symbol/i)
    })

    test('renders Add button', async ({ page }) => {
      await expect(page.getByRole('button', { name: /add/i })).toBeVisible()
    })

    test('renders demo CTA button', async ({ page }) => {
      await expect(page.getByRole('button', { name: /try a live analysis/i })).toBeVisible()
    })

    test('shows popular tickers when watchlist is empty', async ({ page }) => {
      await expect(page.getByText(/popular tickers/i)).toBeVisible()
    })

    test('input is auto-focused on load', async ({ page }) => {
      await expect(page.getByLabel('Ticker symbol input')).toBeFocused()
    })
  })

  test.describe('Welcome Banner', () => {
    test('shows welcome banner on first visit', async ({ page }) => {
      await expect(page.getByText(/welcome to investment analyst/i)).toBeVisible()
    })

    test('dismiss welcome banner hides it', async ({ page }) => {
      await page.getByRole('button', { name: /dismiss welcome/i }).click()
      await expect(page.getByText(/welcome to investment analyst/i)).not.toBeVisible()
    })

    test('dismissed banner stays hidden on reload', async ({ page }) => {
      await page.getByRole('button', { name: /dismiss welcome/i }).click()
      await page.reload()
      await expect(page.getByText(/welcome to investment analyst/i)).not.toBeVisible()
    })
  })

  test.describe('Adding Tickers', () => {
    test('adds a valid ticker via button click', async ({ page }) => {
      await page.getByLabel('Ticker symbol input').fill('AAPL')
      await page.getByRole('button', { name: /^add$/i }).click()
      await expect(page.getByText('AAPL')).toBeVisible()
      await expect(page.getByText(/watchlist ·/i)).toBeVisible()
    })

    test('adds a valid ticker via Enter key', async ({ page }) => {
      await page.getByLabel('Ticker symbol input').fill('MSFT')
      await page.getByLabel('Ticker symbol input').press('Enter')
      await expect(page.getByText('MSFT')).toBeVisible()
    })

    test('normalizes lowercase input to uppercase', async ({ page }) => {
      await page.getByLabel('Ticker symbol input').fill('nvda')
      await page.getByLabel('Ticker symbol input').press('Enter')
      // Should appear as a watchlist pill
      await expect(page.locator('.inline-flex', { hasText: 'NVDA' }).filter({ has: page.locator('button[aria-label*="Remove"]') })).toHaveCount(1)
    })

    test('clears input after successful add', async ({ page }) => {
      await page.getByLabel('Ticker symbol input').fill('TSLA')
      await page.getByLabel('Ticker symbol input').press('Enter')
      await expect(page.getByLabel('Ticker symbol input')).toHaveValue('')
    })

    test('does not add duplicate tickers', async ({ page }) => {
      await page.getByLabel('Ticker symbol input').fill('AAPL')
      await page.getByLabel('Ticker symbol input').press('Enter')
      await page.getByLabel('Ticker symbol input').fill('AAPL')
      await page.getByLabel('Ticker symbol input').press('Enter')
      // Should only appear once in watchlist (exclude suggestion buttons)
      const pills = page.locator('.inline-flex', { hasText: 'AAPL' }).filter({ has: page.locator('button[aria-label*="Remove"]') })
      await expect(pills).toHaveCount(1)
    })

    test('supports dot-notation tickers like BRK.B', async ({ page }) => {
      await page.getByLabel('Ticker symbol input').fill('BRK.B')
      await page.getByLabel('Ticker symbol input').press('Enter')
      await expect(page.getByText('BRK.B')).toBeVisible()
    })
  })

  test.describe('Ticker Validation', () => {
    test('empty submit does nothing (no error, no add)', async ({ page }) => {
      // getTickerError returns null for empty - no error shown, ticker not added
      await page.getByRole('button', { name: /^add$/i }).click()
      // Watchlist section should not appear
      await expect(page.getByText(/watchlist ·/i)).not.toBeVisible()
    })

    test('shows error for invalid characters', async ({ page }) => {
      await page.getByLabel('Ticker symbol input').fill('$$$')
      await page.getByLabel('Ticker symbol input').press('Enter')
      await expect(page.getByRole('alert')).toBeVisible()
    })

    test('shows error for ticker starting with number', async ({ page }) => {
      await page.getByLabel('Ticker symbol input').fill('123')
      await page.getByLabel('Ticker symbol input').press('Enter')
      await expect(page.getByRole('alert')).toBeVisible()
    })

    test('clears error when user types again', async ({ page }) => {
      await page.getByLabel('Ticker symbol input').fill('$$$')
      await page.getByLabel('Ticker symbol input').press('Enter')
      await expect(page.getByRole('alert')).toBeVisible()
      await page.getByLabel('Ticker symbol input').fill('A')
      await expect(page.getByRole('alert')).not.toBeVisible()
    })

    test('respects max length of 10 characters', async ({ page }) => {
      await page.getByLabel('Ticker symbol input').fill('ABCDEFGHIJK')
      const value = await page.getByLabel('Ticker symbol input').inputValue()
      expect(value.length).toBeLessThanOrEqual(10)
    })
  })

  test.describe('Removing Tickers', () => {
    test('removes a ticker from watchlist', async ({ page }) => {
      await page.getByLabel('Ticker symbol input').fill('AAPL')
      await page.getByLabel('Ticker symbol input').press('Enter')
      await expect(page.getByText('AAPL')).toBeVisible()
      await page.getByRole('button', { name: /remove aapl/i }).click()
      // The ticker pill should be gone
      await expect(page.locator('.inline-flex', { hasText: 'AAPL' }).filter({ has: page.locator('button[aria-label*="Remove"]') })).toHaveCount(0)
    })
  })

  test.describe('Analyze Button', () => {
    test('analyze button appears when tickers are added', async ({ page }) => {
      await page.getByLabel('Ticker symbol input').fill('NVDA')
      await page.getByLabel('Ticker symbol input').press('Enter')
      await expect(page.getByRole('button', { name: /analyze 1 stock/i })).toBeVisible()
    })

    test('analyze button shows correct plural count', async ({ page }) => {
      await page.getByLabel('Ticker symbol input').fill('NVDA')
      await page.getByLabel('Ticker symbol input').press('Enter')
      await page.getByLabel('Ticker symbol input').fill('AAPL')
      await page.getByLabel('Ticker symbol input').press('Enter')
      await expect(page.getByRole('button', { name: /analyze 2 stocks/i })).toBeVisible()
    })

    test('clicking analyze navigates to /analyze with tickers param', async ({ page }) => {
      await page.getByLabel('Ticker symbol input').fill('NVDA')
      await page.getByLabel('Ticker symbol input').press('Enter')
      await page.getByRole('button', { name: /analyze 1 stock/i }).click()
      await expect(page).toHaveURL(/\/analyze\?tickers=NVDA/)
    })
  })

  test.describe('Demo CTA', () => {
    test('demo button navigates to analyze NVDA', async ({ page }) => {
      await page.getByRole('button', { name: /try a live analysis/i }).click()
      await expect(page).toHaveURL(/\/analyze\?tickers=NVDA/)
    })
  })

  test.describe('Quick Add Suggestions', () => {
    test('clicking a suggestion adds it to watchlist', async ({ page }) => {
      // Click the first suggestion button (popular ticker)
      const suggestions = page.locator('button.text-xs.font-mono')
      const firstSuggestion = suggestions.first()
      const text = await firstSuggestion.textContent()
      await firstSuggestion.click()
      await expect(page.locator('.inline-flex', { hasText: text! })).toBeVisible()
    })

    test('suggestions disappear when watchlist has items', async ({ page }) => {
      await page.getByLabel('Ticker symbol input').fill('AAPL')
      await page.getByLabel('Ticker symbol input').press('Enter')
      await expect(page.getByText(/popular tickers/i)).not.toBeVisible()
    })
  })
})
