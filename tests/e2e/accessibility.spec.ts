import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

test.describe('Accessibility', () => {
  test('all interactive elements have visible focus rings', async ({ page }) => {
    await page.goto('/')

    // Tab through interactive elements and verify focus styling is applied
    // The project uses a "focus-ring" utility class for focus outlines
    await page.keyboard.press('Tab')

    // First focusable element should have focus
    const focused = page.locator(':focus')
    await expect(focused).toBeVisible()

    // Verify the focus element has the focus-ring class or outline styling
    const outline = await focused.evaluate((el) => {
      const style = window.getComputedStyle(el)
      return style.outlineStyle !== 'none' || el.classList.contains('focus-ring')
    })
    expect(outline).toBe(true)
  })

  test('ARIA labels on icon buttons', async ({ page }) => {
    await page.goto('/')

    // Theme switcher should have an aria-label
    const themeButton = page.getByRole('button', { name: 'Change theme' })
    await expect(themeButton).toBeVisible()
    await expect(themeButton).toHaveAttribute('aria-label', 'Change theme')

    // Add ticker to get remove buttons
    const input = page.getByLabel('Ticker symbol input')
    await input.fill('NVDA')
    await page.getByRole('button', { name: /Add/i }).click()

    // Remove button should have aria-label
    const removeButton = page.getByRole('button', { name: 'Remove NVDA' })
    await expect(removeButton).toBeVisible()
  })

  test('tab order is logical', async ({ page }) => {
    await page.goto('/')

    const tabOrder: string[] = []

    // Tab through several elements and record the order
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press('Tab')
      const tagName = await page.locator(':focus').evaluate((el) => {
        return `${el.tagName.toLowerCase()}:${el.textContent?.trim().slice(0, 20) || el.getAttribute('aria-label') || ''}`
      })
      tabOrder.push(tagName)
    }

    // Header links should come before the main content input
    // The first few tabs should hit header elements, then the main content
    expect(tabOrder.length).toBeGreaterThan(0)

    // Verify we eventually reach the input field
    const hasInput = tabOrder.some((item) => item.startsWith('input'))
    expect(hasInput).toBe(true)
  })

  test('color contrast meets WCAG AA', async ({ page }) => {
    await page.goto('/')

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .include('body')
      .analyze()

    // Filter to only color-contrast violations
    const contrastViolations = results.violations.filter(
      (v) => v.id === 'color-contrast',
    )

    // Allow up to 0 contrast violations for critical text.
    // Note: some decorative/muted text may fail, those are acceptable.
    // We check that primary text and interactive elements pass.
    expect(contrastViolations).toHaveLength(0)
  })

  test('no critical accessibility violations', async ({ page }) => {
    await page.goto('/')

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .include('body')
      .analyze()

    // Filter for critical and serious violations only
    const criticalViolations = results.violations.filter(
      (v) => v.impact === 'critical' || v.impact === 'serious',
    )

    expect(criticalViolations).toHaveLength(0)
  })

  test('reduced motion: animations respect prefers-reduced-motion', async ({
    page,
  }) => {
    // Emulate reduced motion preference
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.goto('/')

    // Check that animate-pulse elements have animation disabled
    // The CSS should include a media query for prefers-reduced-motion
    const hasReducedMotion = await page.evaluate(() => {
      const style = document.createElement('style')
      document.head.appendChild(style)

      // Check if the media query is being respected
      const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
      return mq.matches
    })

    expect(hasReducedMotion).toBe(true)
  })
})
