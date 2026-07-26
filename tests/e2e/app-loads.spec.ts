import { test, expect } from '@playwright/test'

test.describe('App loads correctly', () => {
  test('renders without errors', async ({ page }) => {
    await page.goto('/')
    await expect(page).toHaveTitle(/AI Investment Analyst/i)
    await expect(page.locator('body')).toBeVisible()
  })

  test('header is visible with correct title', async ({ page }) => {
    await page.goto('/')
    const header = page.locator('header')
    await expect(header).toBeVisible()
    await expect(header.getByText('Investment Analyst')).toBeVisible()
    await expect(
      header.getByText('Multi-agent analysis with LangGraph + MCP'),
    ).toBeVisible()
  })

  test('theme switcher toggles theme', async ({ page }) => {
    await page.goto('/')

    // Open theme switcher
    const themeButton = page.getByRole('button', { name: 'Change theme' })
    await expect(themeButton).toBeVisible()
    await themeButton.click()

    // Theme dropdown appears
    const themeList = page.getByRole('listbox', { name: 'Theme selection' })
    await expect(themeList).toBeVisible()

    // Select a different theme (Plum)
    await themeList.getByRole('option', { name: /Plum/i }).click()

    // Verify the theme attribute changed on the root element
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'plum')

    // Dropdown closes after selection
    await expect(themeList).not.toBeVisible()
  })

  test('navigation between pages works', async ({ page }) => {
    await page.goto('/')

    // Navigate to History
    await page.getByRole('link', { name: 'History' }).click()
    await expect(page).toHaveURL(/\/dashboard/)

    // Navigate to Explore
    await page.getByRole('link', { name: 'Explore' }).click()
    await expect(page).toHaveURL(/\/explore/)

    // Navigate to Evals
    await page.getByRole('link', { name: 'Evals' }).click()
    await expect(page).toHaveURL(/\/evals/)

    // Navigate back to Analyze
    await page.getByRole('link', { name: 'Analyze' }).click()
    await expect(page).toHaveURL(/^\/$/)
  })

  test('footer renders with disclaimer text', async ({ page }) => {
    await page.goto('/')
    const footer = page.locator('footer')
    await expect(footer).toBeVisible()
    await expect(
      footer.getByText('For educational purposes only. Not investment advice.'),
    ).toBeVisible()
    await expect(
      footer.getByText('Data may be delayed. Sources: yfinance, NewsAPI, SEC EDGAR.'),
    ).toBeVisible()
  })
})
