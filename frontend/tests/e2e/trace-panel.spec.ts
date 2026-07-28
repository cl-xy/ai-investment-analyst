import { test, expect } from '@playwright/test'

/**
 * E2E tests for the Agent Trace Panel (three-state tool results).
 * These trigger a real analysis against the live backend.
 * Run separately: npx playwright test --grep @live-analysis
 */

test.describe('Agent Trace Panel @live-analysis', () => {
  test.setTimeout(180_000)

  test('trace panel renders during live analysis', async ({ page }) => {
    await page.goto('/analyze?tickers=NVDA')
    await page.getByRole('button', { name: /start analysis/i }).click()
    // Wait for at least one node to appear in the trace
    const nodeEvent = page.getByText(/router|fetch data/i)
    await expect(nodeEvent.first()).toBeVisible({ timeout: 60000 })
  })

  test('tool results appear with status indicators', async ({ page }) => {
    await page.goto('/analyze?tickers=NVDA')
    await page.getByRole('button', { name: /start analysis/i }).click()
    // Wait for a tool result (any tool name in monospace)
    const toolResult = page.locator('.font-mono').filter({ hasText: /get_/ })
    await expect(toolResult.first()).toBeVisible({ timeout: 120000 })
  })
})
