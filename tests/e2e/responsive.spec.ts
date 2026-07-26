import { test, expect } from '@playwright/test'
import { createMockSSEStream } from './fixtures/mock-sse-events'

test.describe('Responsive layout', () => {
  test.describe('mobile viewport', () => {
    test.use({ viewport: { width: 375, height: 667 } })

    test('navigation collapses for small screens', async ({ page }) => {
      await page.goto('/')

      // On mobile, the nav should still be present (it uses overflow-x-auto)
      // but the subtitle should be hidden (hidden sm:block)
      const subtitle = page.getByText('Multi-agent analysis with LangGraph + MCP')
      await expect(subtitle).not.toBeVisible()

      // Header title still visible
      await expect(page.getByText('Investment Analyst')).toBeVisible()
    })

    test('analysis cards stack vertically on mobile', async ({ page }) => {
      await page.route('**/api/analyze/stream**', async (route) => {
        const body = createMockSSEStream('NVDA')
        await route.fulfill({
          status: 200,
          headers: {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
          },
          body,
        })
      })

      await page.goto('/analyze?tickers=NVDA')

      // Wait for the layout to render
      await expect(page.getByText('Agent Trace')).toBeVisible({ timeout: 10_000 })

      // On mobile, the grid should be single-column (grid-cols-1)
      // Verify the trace panel and analysis card are stacked (both visible, not side-by-side)
      const tracePanel = page.getByText('Agent Trace')
      const analysisCard = page.getByText('Buy')

      await expect(tracePanel).toBeVisible()
      await expect(analysisCard).toBeVisible({ timeout: 10_000 })

      // Trace panel bounding box should be above the analysis card
      const traceBounds = await tracePanel.boundingBox()
      const cardBounds = await analysisCard.boundingBox()

      if (traceBounds && cardBounds) {
        expect(traceBounds.y).toBeLessThan(cardBounds.y)
      }
    })

    test('input field is usable on mobile', async ({ page }) => {
      await page.goto('/')

      const input = page.getByLabel('Ticker symbol input')
      await expect(input).toBeVisible()

      await input.fill('TSLA')
      await page.getByRole('button', { name: /Add/i }).click()
      await expect(page.getByText('TSLA')).toBeVisible()
    })
  })

  test.describe('desktop viewport', () => {
    test.use({ viewport: { width: 1280, height: 800 } })

    test('trace and analysis show side-by-side', async ({ page }) => {
      await page.route('**/api/analyze/stream**', async (route) => {
        const body = createMockSSEStream('NVDA')
        await route.fulfill({
          status: 200,
          headers: {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
          },
          body,
        })
      })

      await page.goto('/analyze?tickers=NVDA')

      // Wait for content to load
      await expect(page.getByText('Buy')).toBeVisible({ timeout: 10_000 })

      // On desktop with lg breakpoint, the grid uses grid-cols-[380px_1fr]
      // The trace panel and analysis card should be at roughly the same Y position
      const tracePanel = page.getByText('Agent Trace')
      const analysisCard = page.getByText('Buy')

      const traceBounds = await tracePanel.boundingBox()
      const cardBounds = await analysisCard.boundingBox()

      if (traceBounds && cardBounds) {
        // They should be on roughly the same horizontal row (within 200px tolerance)
        expect(Math.abs(traceBounds.y - cardBounds.y)).toBeLessThan(200)
        // Trace should be to the left of the analysis card
        expect(traceBounds.x).toBeLessThan(cardBounds.x)
      }
    })

    test('subtitle is visible on desktop', async ({ page }) => {
      await page.goto('/')
      await expect(
        page.getByText('Multi-agent analysis with LangGraph + MCP'),
      ).toBeVisible()
    })
  })
})
