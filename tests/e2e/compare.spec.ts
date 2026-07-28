import { test, expect, type Page, type Route } from '@playwright/test'

const COMPARE_RESPONSE = {
  comparisons: [
    {
      ticker: 'AAPL',
      signal: 'hold',
      confidence: 'medium',
      sentiment_score: 0.35,
      risk_flags: ['Slowing iPhone growth'],
    },
    {
      ticker: 'NVDA',
      signal: 'buy',
      confidence: 'high',
      sentiment_score: 0.72,
      risk_flags: ['High valuation'],
    },
  ],
}

const SEARCH_RESPONSE_A = {
  results: [
    { ticker: 'AAPL', name: 'Apple Inc.' },
    { ticker: 'AMZN', name: 'Amazon.com Inc.' },
  ],
}

const SEARCH_RESPONSE_N = {
  results: [
    { ticker: 'NVDA', name: 'NVIDIA Corporation' },
    { ticker: 'NFLX', name: 'Netflix Inc.' },
  ],
}

async function mockTickerSearch(page: Page) {
  await page.route('**/api/tickers/search**', async (route: Route) => {
    const url = new URL(route.request().url())
    const query = url.searchParams.get('q')?.toLowerCase() ?? ''

    let response = { results: [] as { ticker: string; name: string }[] }
    if (query.startsWith('a')) {
      response = SEARCH_RESPONSE_A
    } else if (query.startsWith('n')) {
      response = SEARCH_RESPONSE_N
    }

    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(response),
    })
  })
}

async function mockCompareEndpoint(page: Page) {
  await page.route('**/api/compare**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(COMPARE_RESPONSE),
    })
  })
}

test.describe('Compare page', () => {
  test.beforeEach(async ({ page }) => {
    await mockTickerSearch(page)
    await mockCompareEndpoint(page)
    await page.goto('/compare')
  })

  test('two input slots visible by default', async ({ page }) => {
    const slot1 = page.getByRole('combobox', { name: 'Ticker 1' })
    const slot2 = page.getByRole('combobox', { name: 'Ticker 2' })

    await expect(slot1).toBeVisible()
    await expect(slot2).toBeVisible()

    // Third slot should not exist yet
    await expect(
      page.getByRole('combobox', { name: 'Ticker 3' }),
    ).not.toBeVisible()
  })

  test('typing shows autocomplete suggestions', async ({ page }) => {
    const slot1 = page.getByRole('combobox', { name: 'Ticker 1' })

    await slot1.fill('aa')

    // Combobox should indicate expanded state
    await expect(slot1).toHaveAttribute('aria-expanded', 'true')

    // Listbox with suggestions should appear
    const listbox = page.getByRole('listbox')
    await expect(listbox).toBeVisible()

    // Options should match the mock response
    await expect(listbox.getByRole('option', { name: /AAPL/ })).toBeVisible()
    await expect(listbox.getByRole('option', { name: /AMZN/ })).toBeVisible()
  })

  test('arrow keys navigate suggestions, Enter selects', async ({ page }) => {
    const slot1 = page.getByRole('combobox', { name: 'Ticker 1' })

    await slot1.fill('aa')
    await expect(page.getByRole('listbox')).toBeVisible()

    // Arrow down to first option
    await slot1.press('ArrowDown')

    // First option should be active
    const firstOption = page.getByRole('option').first()
    await expect(firstOption).toHaveAttribute('aria-selected', 'true')

    // Arrow down to second option
    await slot1.press('ArrowDown')

    const secondOption = page.getByRole('option').nth(1)
    await expect(secondOption).toHaveAttribute('aria-selected', 'true')

    // Press Enter to select
    await slot1.press('Enter')

    // Listbox should close and input should have the selected ticker
    await expect(page.getByRole('listbox')).not.toBeVisible()
    await expect(slot1).toHaveValue('AMZN')
  })

  test('Escape closes suggestion dropdown', async ({ page }) => {
    const slot1 = page.getByRole('combobox', { name: 'Ticker 1' })

    await slot1.fill('aa')
    await expect(page.getByRole('listbox')).toBeVisible()

    await slot1.press('Escape')

    await expect(page.getByRole('listbox')).not.toBeVisible()
    await expect(slot1).toHaveAttribute('aria-expanded', 'false')
  })

  test('"+" adds a third slot', async ({ page }) => {
    const addButton = page.getByRole('button', { name: /\+|Add ticker/i })
    await expect(addButton).toBeVisible()

    await addButton.click()

    const slot3 = page.getByRole('combobox', { name: 'Ticker 3' })
    await expect(slot3).toBeVisible()
  })

  test('X removes a slot but minimum 2 remain', async ({ page }) => {
    // Add third slot first
    await page.getByRole('button', { name: /\+|Add ticker/i }).click()
    await expect(page.getByRole('combobox', { name: 'Ticker 3' })).toBeVisible()

    // Remove the third slot
    const removeButton = page.getByRole('button', { name: 'Remove ticker 3' })
    await expect(removeButton).toBeVisible()
    await removeButton.click()

    // Third slot should be gone
    await expect(
      page.getByRole('combobox', { name: 'Ticker 3' }),
    ).not.toBeVisible()

    // Two slots still remain
    await expect(page.getByRole('combobox', { name: 'Ticker 1' })).toBeVisible()
    await expect(page.getByRole('combobox', { name: 'Ticker 2' })).toBeVisible()

    // Remove buttons for the remaining two should not be available (minimum 2)
    await expect(
      page.getByRole('button', { name: 'Remove ticker 1' }),
    ).not.toBeVisible()
    await expect(
      page.getByRole('button', { name: 'Remove ticker 2' }),
    ).not.toBeVisible()
  })

  test('Compare button triggers API call and shows results', async ({ page }) => {
    const slot1 = page.getByRole('combobox', { name: 'Ticker 1' })
    const slot2 = page.getByRole('combobox', { name: 'Ticker 2' })

    // Fill in tickers via autocomplete selection
    await slot1.fill('aa')
    await expect(page.getByRole('listbox')).toBeVisible()
    await page.getByRole('option', { name: /AAPL/ }).click()

    await slot2.fill('nv')
    await expect(page.getByRole('listbox')).toBeVisible()
    await page.getByRole('option', { name: /NVDA/ }).click()

    // Click Compare
    const compareButton = page.getByRole('button', { name: /Compare/i })
    await compareButton.click()

    // Results table should appear with data for both tickers
    await expect(page.getByText('AAPL')).toBeVisible({ timeout: 5_000 })
    await expect(page.getByText('NVDA')).toBeVisible()
  })

  test('results table displays signal, confidence, sentiment for each ticker', async ({ page }) => {
    const slot1 = page.getByRole('combobox', { name: 'Ticker 1' })
    const slot2 = page.getByRole('combobox', { name: 'Ticker 2' })

    await slot1.fill('aa')
    await expect(page.getByRole('listbox')).toBeVisible()
    await page.getByRole('option', { name: /AAPL/ }).click()

    await slot2.fill('nv')
    await expect(page.getByRole('listbox')).toBeVisible()
    await page.getByRole('option', { name: /NVDA/ }).click()

    await page.getByRole('button', { name: /Compare/i }).click()

    // Wait for results
    await expect(page.getByText('hold')).toBeVisible({ timeout: 5_000 })

    // AAPL row: signal=hold, confidence=medium, sentiment=0.35
    await expect(page.getByText('hold')).toBeVisible()
    await expect(page.getByText('medium')).toBeVisible()
    await expect(page.getByText('0.35')).toBeVisible()
    await expect(page.getByText('Slowing iPhone growth')).toBeVisible()

    // NVDA row: signal=buy, confidence=high, sentiment=0.72
    await expect(page.getByText('buy')).toBeVisible()
    await expect(page.getByText('high')).toBeVisible()
    await expect(page.getByText('0.72')).toBeVisible()
    await expect(page.getByText('High valuation')).toBeVisible()
  })

  test('"Analyze {TICKER}" link navigates correctly', async ({ page }) => {
    const slot1 = page.getByRole('combobox', { name: 'Ticker 1' })
    const slot2 = page.getByRole('combobox', { name: 'Ticker 2' })

    await slot1.fill('aa')
    await expect(page.getByRole('listbox')).toBeVisible()
    await page.getByRole('option', { name: /AAPL/ }).click()

    await slot2.fill('nv')
    await expect(page.getByRole('listbox')).toBeVisible()
    await page.getByRole('option', { name: /NVDA/ }).click()

    await page.getByRole('button', { name: /Compare/i }).click()

    // Wait for results
    await expect(page.getByText('hold')).toBeVisible({ timeout: 5_000 })

    // Click "Analyze AAPL" link
    const analyzeLink = page.getByRole('link', { name: 'Analyze AAPL' })
    await expect(analyzeLink).toBeVisible()
    await analyzeLink.click()

    await expect(page).toHaveURL(/\/analyze\?tickers=AAPL/)
  })

  test('Compare button disabled when fewer than 2 tickers entered', async ({ page }) => {
    const compareButton = page.getByRole('button', { name: /Compare/i })

    // With no tickers filled, button should be disabled
    await expect(compareButton).toBeDisabled()

    // Fill only the first slot
    const slot1 = page.getByRole('combobox', { name: 'Ticker 1' })
    await slot1.fill('aa')
    await expect(page.getByRole('listbox')).toBeVisible()
    await page.getByRole('option', { name: /AAPL/ }).click()

    // Still disabled with only 1 ticker
    await expect(compareButton).toBeDisabled()

    // Fill the second slot
    const slot2 = page.getByRole('combobox', { name: 'Ticker 2' })
    await slot2.fill('nv')
    await expect(page.getByRole('listbox')).toBeVisible()
    await page.getByRole('option', { name: /NVDA/ }).click()

    // Now enabled with 2 tickers
    await expect(compareButton).toBeEnabled()
  })
})
