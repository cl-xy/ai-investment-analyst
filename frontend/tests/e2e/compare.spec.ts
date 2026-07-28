import { test, expect } from '@playwright/test'

/**
 * E2E tests for the Compare page.
 * Covers: combobox inputs, autocomplete, slot management, validation, results table.
 */

test.describe('Compare Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/compare')
    await page.waitForLoadState('networkidle')
  })

  test.describe('Page Load', () => {
    test('renders page heading', async ({ page }) => {
      await expect(page.getByRole('heading', { name: /compare stocks/i })).toBeVisible()
    })

    test('renders description text', async ({ page }) => {
      await expect(page.getByText(/enter 2-3 tickers/i)).toBeVisible()
    })

    test('renders two default ticker inputs', async ({ page }) => {
      const inputs = page.getByRole('combobox')
      await expect(inputs).toHaveCount(2)
    })

    test('renders compare button', async ({ page }) => {
      await expect(page.getByRole('button', { name: /compare/i })).toBeVisible()
    })

    test('compare button is disabled with empty inputs', async ({ page }) => {
      await expect(page.getByRole('button', { name: /compare/i })).toBeDisabled()
    })
  })

  test.describe('Ticker Input', () => {
    test('can type in first ticker input', async ({ page }) => {
      const input = page.getByRole('combobox').first()
      await input.fill('AAPL')
      await expect(input).toHaveValue('AAPL')
    })

    test('input converts to uppercase', async ({ page }) => {
      const input = page.getByRole('combobox').first()
      await input.fill('aapl')
      await expect(input).toHaveValue('AAPL')
    })

    test('shows autocomplete suggestions on focus', async ({ page }) => {
      const input = page.getByRole('combobox').first()
      await input.fill('A')
      await input.focus()
      // Should show listbox with suggestions
      const listbox = page.getByRole('listbox')
      await expect(listbox).toBeVisible()
    })

    test('suggestions filter by typed text', async ({ page }) => {
      const input = page.getByRole('combobox').first()
      await input.fill('NV')
      // NVDA should appear in suggestions
      await expect(page.getByRole('option', { name: 'NVDA' })).toBeVisible()
    })

    test('clicking suggestion fills input', async ({ page }) => {
      const input = page.getByRole('combobox').first()
      await input.fill('A')
      await input.focus()
      const option = page.getByRole('option').first()
      await option.click()
      const value = await input.inputValue()
      expect(value.length).toBeGreaterThan(0)
    })

    test('keyboard navigation works in suggestions', async ({ page }) => {
      const input = page.getByRole('combobox').first()
      await input.fill('A')
      await input.press('ArrowDown')
      // Active descendant should be set
      const ariaActive = await input.getAttribute('aria-activedescendant')
      expect(ariaActive).toBeTruthy()
    })

    test('Escape closes suggestions', async ({ page }) => {
      const input = page.getByRole('combobox').first()
      await input.fill('A')
      await expect(page.getByRole('listbox')).toBeVisible()
      await input.press('Escape')
      await expect(page.getByRole('listbox')).not.toBeVisible()
    })
  })

  test.describe('Slot Management', () => {
    test('shows add slot button when fewer than 3 inputs', async ({ page }) => {
      // Find the dashed-border add button
      const addBtn = page.locator('button', { has: page.locator('.lucide-plus') }).filter({ hasNot: page.locator('text=Add') })
      await expect(addBtn.first()).toBeVisible()
    })

    test('clicking add slot creates third input', async ({ page }) => {
      // Click the add-slot button (has Plus icon, dashed border)
      const addSlotBtn = page.locator('button.border-dashed')
      await addSlotBtn.click()
      const inputs = page.getByRole('combobox')
      await expect(inputs).toHaveCount(3)
    })

    test('cannot add more than 3 slots', async ({ page }) => {
      const addSlotBtn = page.locator('button.border-dashed')
      await addSlotBtn.click()
      // After adding third, the dashed button should disappear
      await expect(page.locator('button.border-dashed')).not.toBeVisible()
    })

    test('remove button appears on third slot', async ({ page }) => {
      const addSlotBtn = page.locator('button.border-dashed')
      await addSlotBtn.click()
      // Remove buttons should be visible (X buttons near inputs)
      const removeButtons = page.getByRole('button', { name: /remove ticker/i })
      await expect(removeButtons.first()).toBeVisible()
    })

    test('remove slot reduces input count', async ({ page }) => {
      const addSlotBtn = page.locator('button.border-dashed')
      await addSlotBtn.click()
      await expect(page.getByRole('combobox')).toHaveCount(3)
      await page.getByRole('button', { name: /remove ticker 1/i }).click()
      await expect(page.getByRole('combobox')).toHaveCount(2)
    })
  })

  test.describe('Compare Action', () => {
    test('compare button enables with 2 valid tickers', async ({ page }) => {
      const inputs = page.getByRole('combobox')
      await inputs.nth(0).fill('AAPL')
      await inputs.nth(1).fill('MSFT')
      await expect(page.getByRole('button', { name: /compare/i })).toBeEnabled()
    })

    test('compare button disabled with only 1 ticker', async ({ page }) => {
      const inputs = page.getByRole('combobox')
      await inputs.nth(0).fill('AAPL')
      await expect(page.getByRole('button', { name: /compare/i })).toBeDisabled()
    })

    test('shows loading state when comparing', async ({ page }) => {
      // Mock the API to delay
      await page.route('**/api/compare*', async (route) => {
        await new Promise((r) => setTimeout(r, 500))
        await route.fulfill({ status: 200, body: JSON.stringify({ tickers: ['AAPL', 'MSFT'], analyses: {} }) })
      })

      const inputs = page.getByRole('combobox')
      await inputs.nth(0).fill('AAPL')
      await inputs.nth(1).fill('MSFT')
      await page.getByRole('button', { name: /compare/i }).click()
      await expect(page.getByText(/comparing/i)).toBeVisible()
    })

    test('shows error message on API failure', async ({ page }) => {
      await page.route('**/api/compare*', (route) => {
        route.fulfill({ status: 500, body: JSON.stringify({ detail: 'Service unavailable' }) })
      })

      const inputs = page.getByRole('combobox')
      await inputs.nth(0).fill('AAPL')
      await inputs.nth(1).fill('MSFT')
      await page.getByRole('button', { name: /compare/i }).click()
      await expect(page.getByText(/service unavailable|comparison failed/i)).toBeVisible()
    })

    test('shows results table on success', async ({ page }) => {
      await page.route('**/api/compare*', (route) => {
        route.fulfill({
          status: 200,
          body: JSON.stringify({
            tickers: ['AAPL', 'MSFT'],
            analyses: {
              AAPL: { ticker: 'AAPL', signal: 'buy', confidence: 'high', sentiment_score: 0.6, risk_flags: ['valuation'] },
              MSFT: { ticker: 'MSFT', signal: 'hold', confidence: 'medium', sentiment_score: 0.3, risk_flags: [] },
            },
          }),
        })
      })

      const inputs = page.getByRole('combobox')
      await inputs.nth(0).fill('AAPL')
      await inputs.nth(1).fill('MSFT')
      await page.getByRole('button', { name: /compare/i }).click()

      await expect(page.getByRole('table')).toBeVisible()
      await expect(page.getByText('buy')).toBeVisible()
      await expect(page.getByText('hold')).toBeVisible()
    })

    test('results table shows analyze links per ticker', async ({ page }) => {
      await page.route('**/api/compare*', (route) => {
        route.fulfill({
          status: 200,
          body: JSON.stringify({
            tickers: ['AAPL', 'MSFT'],
            analyses: {
              AAPL: { ticker: 'AAPL', signal: 'buy', confidence: 'high', sentiment_score: 0.5, risk_flags: [] },
              MSFT: { ticker: 'MSFT', signal: 'hold', confidence: 'medium', sentiment_score: 0.2, risk_flags: [] },
            },
          }),
        })
      })

      const inputs = page.getByRole('combobox')
      await inputs.nth(0).fill('AAPL')
      await inputs.nth(1).fill('MSFT')
      await page.getByRole('button', { name: /compare/i }).click()

      await expect(page.getByRole('link', { name: /analyze aapl/i })).toBeVisible()
      await expect(page.getByRole('link', { name: /analyze msft/i })).toBeVisible()
    })
  })
})
