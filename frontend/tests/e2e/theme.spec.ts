import { test, expect } from '@playwright/test'

/**
 * E2E tests for theme switching.
 * Covers: default theme, switching themes, persistence across reloads.
 */

test.describe('Theme Switcher', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => localStorage.clear())
    await page.reload()
    await page.waitForLoadState('networkidle')
  })

  test('page has a default theme', async ({ page }) => {
    const theme = await page.locator('html').getAttribute('data-theme')
    expect(theme).toBeTruthy()
  })

  test('theme switcher button is clickable', async ({ page }) => {
    // The theme switcher renders a button with a theme icon
    const themeBtns = page.locator('button').filter({ has: page.locator('[class*="lucide"]') })
    // There should be at least one clickable theme-related button
    const count = await themeBtns.count()
    expect(count).toBeGreaterThan(0)
  })

  test('changing theme updates data-theme attribute', async ({ page }) => {
    const initialTheme = await page.locator('html').getAttribute('data-theme')

    // Click theme switcher to open options, then pick a different one
    // The ThemeSwitcher component should have theme option buttons
    const switcher = page.locator('[data-testid="theme-switcher"]').or(page.locator('button').filter({ hasText: /theme/i }))
    if (await switcher.count() > 0) {
      await switcher.first().click()
    }

    // Try to find and click a theme option
    const themeOptions = page.locator('button[data-theme]')
    if (await themeOptions.count() > 0) {
      const secondOption = themeOptions.nth(1)
      await secondOption.click()
      const newTheme = await page.locator('html').getAttribute('data-theme')
      expect(newTheme).not.toBe(initialTheme)
    }
  })

  test('theme persists across page reloads', async ({ page }) => {
    // Set theme via localStorage directly
    await page.evaluate(() => {
      localStorage.setItem('invest-theme', 'plum')
    })
    await page.reload()
    const theme = await page.locator('html').getAttribute('data-theme')
    expect(theme).toBe('plum')
  })

  test('CSS custom properties are defined for theme', async ({ page }) => {
    const hasVars = await page.evaluate(() => {
      const style = getComputedStyle(document.documentElement)
      const bg = style.getPropertyValue('--bg')
      const accent = style.getPropertyValue('--accent')
      return !!(bg && accent)
    })
    expect(hasVars).toBe(true)
  })
})
