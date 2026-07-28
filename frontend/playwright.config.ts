import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright E2E tests run against the deployed frontend.
 * Set BASE_URL env var to target a specific deployment:
 *   BASE_URL=https://your-app.vercel.app npx playwright test
 *
 * Falls back to localhost:5173 for local dev.
 */
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? 'github' : 'html',
  use: {
    baseURL: process.env.BASE_URL || 'https://ai-investment-analyst-iota.vercel.app',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // Only start local dev server if no BASE_URL is set
  ...(!process.env.BASE_URL && {
    webServer: {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: true,
      timeout: 30_000,
    },
  }),
})
