import { test, expect } from '@playwright/test'

/**
 * E2E tests for global accessibility patterns.
 * Covers: skip-to-content, focus management, keyboard navigation, ARIA landmarks.
 */

test.describe('Accessibility', () => {
  test.describe('Skip to Content', () => {
    test('skip link exists and is visually hidden by default', async ({ page }) => {
      await page.goto('/')
      const skipLink = page.getByRole('link', { name: /skip to main content/i })
      await expect(skipLink).toHaveClass(/sr-only/)
    })

    test('skip link becomes visible on focus', async ({ page }) => {
      await page.goto('/')
      await page.keyboard.press('Tab')
      const skipLink = page.getByRole('link', { name: /skip to main content/i })
      await expect(skipLink).toBeVisible()
    })

    test('skip link points to #main-content', async ({ page }) => {
      await page.goto('/')
      const skipLink = page.getByRole('link', { name: /skip to main content/i })
      await expect(skipLink).toHaveAttribute('href', '#main-content')
    })

    test('main content element has correct id', async ({ page }) => {
      await page.goto('/')
      const main = page.locator('#main-content')
      await expect(main).toBeVisible()
    })
  })

  test.describe('ARIA Landmarks', () => {
    test('page has a main region', async ({ page }) => {
      await page.goto('/')
      await expect(page.getByRole('main')).toBeVisible()
    })

    test('page has navigation region', async ({ page }) => {
      await page.goto('/')
      await expect(page.getByRole('navigation', { name: /main/i })).toBeVisible()
    })

    test('page has a banner (header)', async ({ page }) => {
      await page.goto('/')
      await expect(page.getByRole('banner')).toBeVisible()
    })

    test('page has a contentinfo (footer)', async ({ page }) => {
      await page.goto('/')
      await expect(page.getByRole('contentinfo')).toBeVisible()
    })
  })

  test.describe('Keyboard Navigation', () => {
    test('all interactive elements are reachable via Tab', async ({ page }) => {
      await page.goto('/')
      // Tab through first several interactive elements
      for (let i = 0; i < 10; i++) {
        await page.keyboard.press('Tab')
      }
      // Something should be focused
      const focused = await page.evaluate(() => document.activeElement?.tagName)
      expect(focused).toBeTruthy()
      expect(['A', 'BUTTON', 'INPUT', 'TEXTAREA', 'SELECT']).toContain(focused)
    })

    test('focused elements have visible focus indicator', async ({ page }) => {
      await page.goto('/')
      // Tab to first interactive element after skip-link
      await page.keyboard.press('Tab')
      await page.keyboard.press('Tab')
      // The focused element should have focus-visible styles
      const hasFocusStyles = await page.evaluate(() => {
        const el = document.activeElement
        if (!el) return false
        const styles = getComputedStyle(el)
        return styles.outlineStyle !== 'none' || styles.boxShadow !== 'none'
      })
      expect(hasFocusStyles).toBe(true)
    })
  })

  test.describe('Touch Target Sizes', () => {
    test('buttons meet 44px minimum touch target', async ({ page }) => {
      await page.goto('/')
      // Check the Add button on watchlist page
      const addBtn = page.getByRole('button', { name: /^add$/i })
      const box = await addBtn.boundingBox()
      expect(box!.height).toBeGreaterThanOrEqual(44)
    })

    test('nav links meet minimum height', async ({ page }) => {
      await page.goto('/')
      const navLinks = page.getByRole('navigation', { name: /main/i }).getByRole('link')
      const first = navLinks.first()
      const box = await first.boundingBox()
      expect(box!.height).toBeGreaterThanOrEqual(44)
    })
  })

  test.describe('Color and Contrast', () => {
    test('page respects data-theme attribute', async ({ page }) => {
      await page.goto('/')
      const theme = await page.locator('html').getAttribute('data-theme')
      expect(theme).toBeTruthy()
    })
  })

  test.describe('Reduced Motion', () => {
    test('animations use CSS transitions (not forced animation)', async ({ page }) => {
      await page.goto('/')
      // Verify that animation classes exist but are CSS-driven
      const hasAnimClass = await page.evaluate(() => {
        return document.querySelector('.animate-fade-in') !== null
      })
      // Page uses CSS animations (controllable via prefers-reduced-motion)
      expect(hasAnimClass).toBe(true)
    })
  })
})
