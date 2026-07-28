import { test, expect } from '@playwright/test'

/**
 * E2E tests for the Chat page against live deployment.
 */

test.describe('Chat Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/chat')
  })

  test('renders page heading', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /^chat$/i })).toBeVisible()
  })

  test('renders description text', async ({ page }) => {
    await expect(page.getByText(/ask questions about stocks/i)).toBeVisible()
  })

  test('renders message input', async ({ page }) => {
    await expect(page.getByLabel('Chat message input')).toBeVisible()
  })

  test('renders send button', async ({ page }) => {
    await expect(page.getByRole('button', { name: /send message/i })).toBeVisible()
  })

  test('send button disabled when input empty', async ({ page }) => {
    await expect(page.getByRole('button', { name: /send message/i })).toBeDisabled()
  })

  test('send button enables when input has text', async ({ page }) => {
    await page.getByLabel('Chat message input').fill('Hello')
    await expect(page.getByRole('button', { name: /send message/i })).toBeEnabled()
  })

  test('shows empty state with quick prompts', async ({ page }) => {
    await expect(page.getByText(/ask me anything about stocks/i)).toBeVisible()
    await expect(page.getByRole('button', { name: /what is nvda trading at/i })).toBeVisible()
    await expect(page.getByRole('button', { name: /compare aapl vs msft/i })).toBeVisible()
  })

  test('clicking quick prompt fills input', async ({ page }) => {
    await page.getByRole('button', { name: /what is nvda trading at/i }).click()
    await expect(page.getByLabel('Chat message input')).toHaveValue('What is NVDA trading at?')
  })

  test('sending a message shows user bubble', async ({ page }) => {
    await page.getByLabel('Chat message input').fill('Test message')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(page.getByText('Test message')).toBeVisible()
  })

  test('Enter key sends message', async ({ page }) => {
    await page.getByLabel('Chat message input').fill('Hello world')
    await page.getByLabel('Chat message input').press('Enter')
    await expect(page.getByText('Hello world')).toBeVisible()
  })

  test('input clears after sending', async ({ page }) => {
    await page.getByLabel('Chat message input').fill('Test')
    await page.getByLabel('Chat message input').press('Enter')
    await expect(page.getByLabel('Chat message input')).toHaveValue('')
  })

  test('clear button appears after messages', async ({ page }) => {
    await page.getByLabel('Chat message input').fill('Hello')
    await page.getByLabel('Chat message input').press('Enter')
    await expect(page.getByRole('button', { name: /clear chat history/i })).toBeVisible()
  })

  test('clear button removes messages', async ({ page }) => {
    await page.getByLabel('Chat message input').fill('Hello')
    await page.getByLabel('Chat message input').press('Enter')
    await page.getByRole('button', { name: /clear chat history/i }).click()
    await expect(page.getByText(/ask me anything about stocks/i)).toBeVisible()
  })

  test('messages region has aria-live', async ({ page }) => {
    const region = page.getByRole('log', { name: /chat messages/i })
    await expect(region).toHaveAttribute('aria-live', 'polite')
  })
})
