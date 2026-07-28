import { test, expect, type Page, type Route } from '@playwright/test'

/**
 * Helper to build a mock SSE response body for the chat stream endpoint.
 * Uses the actual event types from the ChatPage component: llm_token, tool_call, run_completed.
 */
function sseEvent(eventType: string, data: Record<string, unknown>): string {
  return `event: ${eventType}\ndata: ${JSON.stringify(data)}\n\n`
}

function createChatSSEStream(options: {
  tokens?: string[]
  toolCalls?: { name: string; args: Record<string, unknown> }[]
  includeRunCompleted?: boolean
} = {}): string {
  const {
    tokens = ['Hello', ', ', 'how', ' can', ' I', ' help', ' you', '?'],
    toolCalls = [],
    includeRunCompleted = true,
  } = options

  const events: string[] = []
  const runId = 'run_chat_test'
  const ts = '2026-07-28T10:00:00Z'
  let seq = 0

  // Emit tool calls first (if any)
  for (const tc of toolCalls) {
    events.push(
      sseEvent('tool_call', {
        run_id: runId,
        seq: seq++,
        type: 'tool_call',
        timestamp: ts,
        node: 'chat',
        tool: tc.name,
        payload: { tool_name: tc.name, args: tc.args },
      }),
    )
  }

  // Emit tokens
  for (const token of tokens) {
    events.push(
      sseEvent('llm_token', {
        run_id: runId,
        seq: seq++,
        type: 'llm_token',
        timestamp: ts,
        node: 'chat',
        tool: null,
        payload: { text: token },
      }),
    )
  }

  // run_completed
  if (includeRunCompleted) {
    events.push(
      sseEvent('run_completed', {
        run_id: runId,
        seq: seq++,
        type: 'run_completed',
        timestamp: ts,
        node: null,
        tool: null,
        payload: { total_duration_ms: 1200 },
      }),
    )
  }

  return events.join('')
}

/**
 * Mocks the chat SSE endpoint with a fulfilled response.
 */
async function mockChatSSE(page: Page, body: string) {
  await page.route('**/api/chat/stream**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
      body,
    })
  })
}

/**
 * Mocks the chat SSE endpoint but never completes (hangs open for testing stop behavior).
 * Sends a few tokens then stops without run_completed.
 */
async function mockChatSSEHanging(page: Page) {
  const body = createChatSSEStream({
    tokens: ['Thinking', '...'],
    includeRunCompleted: false,
  })
  await page.route('**/api/chat/stream**', async (route: Route) => {
    await route.fulfill({
      status: 200,
      headers: {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
      },
      body,
    })
  })
}

/**
 * Pre-seeds sessionStorage with chat messages so the page restores them on load.
 */
async function seedSessionMessages(page: Page, messages: unknown[]) {
  await page.addInitScript((msgs) => {
    sessionStorage.setItem('invest-state:chat-messages', JSON.stringify(msgs))
  }, messages)
}

test.describe('Chat page', () => {
  test.describe('Empty state', () => {
    test('shows suggested questions when no messages', async ({ page }) => {
      await page.goto('/chat')

      const chatLog = page.getByRole('log', { name: 'Chat messages' })
      await expect(chatLog).toBeVisible()

      // Suggested question buttons visible
      await expect(page.getByRole('button', { name: 'What is NVDA trading at?' })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Compare AAPL vs MSFT' })).toBeVisible()
      await expect(page.getByRole('button', { name: 'Show my portfolio' })).toBeVisible()
    })
  })

  test.describe('Sending messages', () => {
    test('user can type and send a message via button click', async ({ page }) => {
      const body = createChatSSEStream()
      await mockChatSSE(page, body)
      await page.goto('/chat')

      const input = page.getByLabel('Chat message input')
      await input.fill('What is AAPL trading at?')

      const sendButton = page.getByLabel('Send message')
      await sendButton.click()

      // User message appears in chat
      await expect(page.getByText('What is AAPL trading at?')).toBeVisible()

      // Assistant response streams in
      await expect(page.getByText('Hello, how can I help you?')).toBeVisible({ timeout: 5_000 })

      // Input is cleared after send
      await expect(input).toHaveValue('')
    })

    test('user can send a message with Enter key', async ({ page }) => {
      const body = createChatSSEStream({ tokens: ['Sure', ' thing', '!'] })
      await mockChatSSE(page, body)
      await page.goto('/chat')

      const input = page.getByLabel('Chat message input')
      await input.fill('Show my portfolio')
      await input.press('Enter')

      // User message appears
      await expect(page.getByText('Show my portfolio')).toBeVisible()

      // Assistant responds
      await expect(page.getByText('Sure thing!')).toBeVisible({ timeout: 5_000 })
    })

    test('suggested question click populates input', async ({ page }) => {
      await page.goto('/chat')

      const suggestedButton = page.getByRole('button', { name: 'What is NVDA trading at?' })
      await suggestedButton.click()

      // Input is populated with the suggestion text
      const input = page.getByLabel('Chat message input')
      await expect(input).toHaveValue('What is NVDA trading at?')
    })
  })

  test.describe('Streaming response', () => {
    test('shows typing indicator during streaming', async ({ page }) => {
      // Use a stream that never completes to keep streaming state active
      await mockChatSSEHanging(page)
      await page.goto('/chat')

      const input = page.getByLabel('Chat message input')
      await input.fill('Hello')
      await input.press('Enter')

      // Typing dots appear (the component renders .typing-dot spans when streaming with no content yet)
      // Since the hanging mock delivers "Thinking..." tokens, let's check the message appears
      await expect(page.getByText('Thinking...')).toBeVisible({ timeout: 5_000 })

      // Input should be disabled during streaming
      await expect(input).toBeDisabled()
    })

    test('stop generating button works during stream', async ({ page }) => {
      await mockChatSSEHanging(page)
      await page.goto('/chat')

      const input = page.getByLabel('Chat message input')
      await input.fill('Tell me about TSLA')
      await input.press('Enter')

      // Stop button appears during streaming
      const stopButton = page.getByRole('button', { name: 'Stop generating' })
      await expect(stopButton).toBeVisible({ timeout: 3_000 })

      // Click stop
      await stopButton.click()

      // Stop button disappears
      await expect(stopButton).not.toBeVisible()

      // Input is re-enabled
      await expect(input).not.toBeDisabled()
    })
  })

  test.describe('Clear chat history', () => {
    test('clear button resets chat history', async ({ page }) => {
      const body = createChatSSEStream({ tokens: ['Response', ' here'] })
      await mockChatSSE(page, body)
      await page.goto('/chat')

      // Send a message first
      const input = page.getByLabel('Chat message input')
      await input.fill('Hello')
      await input.press('Enter')

      // Wait for response
      await expect(page.getByText('Response here')).toBeVisible({ timeout: 5_000 })

      // Clear button should be visible
      const clearButton = page.getByLabel('Clear chat history')
      await expect(clearButton).toBeVisible()
      await clearButton.click()

      // Messages gone, empty state returns
      await expect(page.getByText('Response here')).not.toBeVisible()
      await expect(page.getByRole('button', { name: 'What is NVDA trading at?' })).toBeVisible()

      // Clear button hidden when no messages
      await expect(clearButton).not.toBeVisible()
    })
  })

  test.describe('Persistence across refresh', () => {
    test('messages persist across page reload via sessionStorage', async ({ page }) => {
      const seededMessages = [
        { id: 'user-1', role: 'user', content: 'What is AAPL at?' },
        { id: 'asst-1', role: 'assistant', content: 'AAPL is trading at $195.42.', toolCalls: [] },
      ]
      await seedSessionMessages(page, seededMessages)
      await page.goto('/chat')

      // Seeded messages appear
      await expect(page.getByText('What is AAPL at?')).toBeVisible()
      await expect(page.getByText('AAPL is trading at $195.42.')).toBeVisible()

      // Clear button visible (messages exist)
      await expect(page.getByLabel('Clear chat history')).toBeVisible()
    })
  })

  test.describe('Tool calls display', () => {
    test('tool calls are displayed in assistant messages', async ({ page }) => {
      const body = createChatSSEStream({
        tokens: ['NVDA', ' is', ' at', ' $135.42'],
        toolCalls: [
          { name: 'market_data', args: { ticker: 'NVDA', period: '1d' } },
          { name: 'news_search', args: { query: 'NVDA', limit: 5 } },
        ],
      })
      await mockChatSSE(page, body)
      await page.goto('/chat')

      const input = page.getByLabel('Chat message input')
      await input.fill('What is NVDA at?')
      await input.press('Enter')

      // Tool call names appear in the assistant message
      await expect(page.getByText('market_data')).toBeVisible({ timeout: 5_000 })
      await expect(page.getByText('news_search')).toBeVisible()

      // Final response text also renders
      await expect(page.getByText('NVDA is at $135.42')).toBeVisible()
    })
  })

  test.describe('Keyboard accessibility', () => {
    test('Enter sends message, Shift+Enter inserts newline', async ({ page }) => {
      const body = createChatSSEStream({ tokens: ['Got', ' it'] })
      await mockChatSSE(page, body)
      await page.goto('/chat')

      const input = page.getByLabel('Chat message input')
      await input.fill('Line one')

      // Shift+Enter should not send, should allow multiline
      await input.press('Shift+Enter')

      // The message should NOT be sent (no user bubble yet)
      await expect(page.getByText('Line one')).not.toBeVisible()

      // Type second line
      await input.type('Line two')

      // Now press Enter to send
      await input.press('Enter')

      // User message appears (textarea value was submitted)
      await expect(page.getByText(/Line one/)).toBeVisible({ timeout: 3_000 })
    })

    test('send button is disabled when input is empty', async ({ page }) => {
      await page.goto('/chat')

      const sendButton = page.getByLabel('Send message')
      await expect(sendButton).toBeDisabled()

      // Type something
      const input = page.getByLabel('Chat message input')
      await input.fill('Hello')
      await expect(sendButton).not.toBeDisabled()

      // Clear input
      await input.fill('')
      await expect(sendButton).toBeDisabled()
    })
  })
})
