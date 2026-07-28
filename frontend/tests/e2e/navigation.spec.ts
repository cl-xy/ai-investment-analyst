import { test, expect } from '@playwright/test'

/**
 * E2E tests for the Header/Navigation.
 * Covers: logo, nav links, active states, dropdown menu, mobile hamburger, theme switcher.
 */

test.describe('Header & Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
  })

  test.describe('Desktop Navigation', () => {
    test('renders app logo and title', async ({ page }) => {
      await expect(page.getByRole('heading', { name: /investment analyst/i }).first()).toBeVisible()
    })

    test('logo links to home', async ({ page }) => {
      await page.goto('/explore')
      await page.getByRole('link', { name: /investment analyst/i }).click()
      await expect(page).toHaveURL('/')
    })

    test('renders primary nav links', async ({ page }) => {
      await expect(page.getByRole('link', { name: /^analyze$/i })).toBeVisible()
      await expect(page.getByRole('link', { name: /^explore$/i })).toBeVisible()
      await expect(page.getByRole('link', { name: /^compare$/i })).toBeVisible()
      await expect(page.getByRole('link', { name: /^chat$/i })).toBeVisible()
    })

    test('renders History dropdown button', async ({ page }) => {
      await expect(page.getByRole('button', { name: /history/i })).toBeVisible()
    })

    test('History dropdown opens on click', async ({ page }) => {
      await page.getByRole('button', { name: /history/i }).click()
      await expect(page.getByRole('link', { name: /past analyses/i })).toBeVisible()
      await expect(page.getByRole('link', { name: /signal history/i })).toBeVisible()
    })

    test('History dropdown closes on Escape', async ({ page }) => {
      await page.getByRole('button', { name: /history/i }).click()
      await expect(page.getByRole('link', { name: /past analyses/i })).toBeVisible()
      await page.keyboard.press('Escape')
      await expect(page.getByRole('link', { name: /past analyses/i })).not.toBeVisible()
    })

    test('clicking a dropdown link navigates and closes dropdown', async ({ page }) => {
      await page.getByRole('button', { name: /history/i }).click()
      await page.getByRole('link', { name: /past analyses/i }).click()
      await expect(page).toHaveURL('/dashboard')
      await expect(page.getByRole('link', { name: /track record/i })).not.toBeVisible()
    })

    test('active nav link is highlighted', async ({ page }) => {
      const analyzeLink = page.getByRole('navigation', { name: /main/i }).getByRole('link', { name: /^analyze$/i })
      await expect(analyzeLink).toHaveAttribute('aria-current', 'page')
    })

    test('non-active nav links do not have aria-current', async ({ page }) => {
      const exploreLink = page.getByRole('navigation', { name: /main/i }).getByRole('link', { name: /^explore$/i })
      await expect(exploreLink).not.toHaveAttribute('aria-current')
    })
  })

  test.describe('Navigation Routing', () => {
    test('Explore link navigates to /explore', async ({ page }) => {
      await page.getByRole('link', { name: /^explore$/i }).click()
      await expect(page).toHaveURL('/explore')
    })

    test('Compare link navigates to /compare', async ({ page }) => {
      await page.getByRole('link', { name: /^compare$/i }).click()
      await expect(page).toHaveURL('/compare')
    })

    test('Chat link navigates to /chat', async ({ page }) => {
      await page.getByRole('link', { name: /^chat$/i }).click()
      await expect(page).toHaveURL('/chat')
    })
  })

  test.describe('Theme Switcher', () => {
    test('theme switcher button is visible', async ({ page }) => {
      // ThemeSwitcher renders a button
      await expect(page.locator('[data-theme]')).toBeVisible()
    })
  })
})

test.describe('Header - Mobile Navigation', () => {
  test.use({ viewport: { width: 375, height: 812 } })

  test('hamburger button is visible on mobile', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('button', { name: /open menu/i })).toBeVisible()
  })

  test('primary nav links hidden on mobile', async ({ page }) => {
    await page.goto('/')
    // Desktop nav should be hidden
    const desktopNav = page.locator('nav.hidden.md\\:flex')
    await expect(desktopNav).not.toBeVisible()
  })

  test('hamburger opens mobile drawer', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /open menu/i }).click()
    // Mobile nav should now be visible
    await expect(page.getByRole('link', { name: /^analyze$/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /^explore$/i })).toBeVisible()
  })

  test('close button appears when menu is open', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /open menu/i }).click()
    await expect(page.getByRole('button', { name: /close menu/i })).toBeVisible()
  })

  test('clicking mobile link navigates and closes menu', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /open menu/i }).click()
    await page.getByRole('link', { name: /^explore$/i }).click()
    await expect(page).toHaveURL('/explore')
    // Menu should be closed
    await expect(page.getByRole('button', { name: /open menu/i })).toBeVisible()
  })

  test('mobile drawer shows history section', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: /open menu/i }).click()
    await expect(page.getByRole('link', { name: /past analyses/i })).toBeVisible()
    await expect(page.getByRole('link', { name: /signal history/i })).toBeVisible()
  })
})
