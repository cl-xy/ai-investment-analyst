/**
 * Record demo GIF and walkthrough video using Playwright video capture.
 *
 * Strategy:
 *   - GIF: Capture the "wow" moments — input, add ticker, start analysis, watch trace light up
 *     with tool calls. The fast data-fetch phase (100ms-13s per tool) is visually impressive.
 *     Polls for "Running investment debate..." text and cuts just before it appears,
 *     so the GIF never stalls on the 90-120s debate spinner.
 *   - Video: Show breadth — home, input, streaming start, then jump to completed results,
 *     compare page, chat, command palette, theme toggle. Pre-seed by running a real analysis
 *     first (already cached on backend).
 *
 * Smart pauses:
 *   - Hold 1.5s on key reveals (streaming trace appearing, results card)
 *   - Use slowMo for typing (looks human)
 *   - Brief pause after each click (natural rhythm)
 *
 * Post-processing:
 *   ffmpeg -i docs/assets/demo-raw.webm -vf "fps=12,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=192[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3" -loop 0 docs/assets/demo.gif
 *   ffmpeg -i docs/assets/walkthrough-raw.webm -c:v libx264 -preset slow -crf 22 -pix_fmt yuv420p -movflags +faststart docs/assets/walkthrough.mp4
 *
 * Optimization (if GIF > 5MB):
 *   gifsicle -O3 --lossy=40 docs/assets/demo.gif -o docs/assets/demo.gif
 *
 * Usage:
 *   node scripts/record-demo.mjs
 */

import { chromium } from 'playwright'
import { rename, unlink } from 'fs/promises'

const BASE_URL = 'https://ai-investment-analyst-iota.vercel.app'
const ASSETS_DIR = new URL('../docs/assets/', import.meta.url).pathname

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms))
}

/** Remove overlays that block clicks (tour spotlight, contextual hints) */
async function cleanOverlays(page) {
  await page.evaluate(() => {
    // Remove tour portal overlay
    const tour = document.getElementById('tour-portal')
    if (tour) tour.remove()
    // Remove contextual hints
    document.querySelectorAll('[role="tooltip"]').forEach((el) => el.remove())
    // Mark tour as completed so it doesn't reappear
    localStorage.setItem('invest-state:tour-completed', 'true')
    // Dismiss all hints
    ;['watchlist-input', 'trace-panel', 'ops-nav', 'dashboard-card'].forEach((id) => {
      localStorage.setItem(`invest-hint-dismissed:${id}`, 'true')
    })
  })
  await sleep(200)
}

// ──────────────────────────────────────────────────────────────────────
// DEMO GIF: 15s, 960x540
// Flow: Home → type NVDA → add → click Analyze → Start → streaming trace
// ──────────────────────────────────────────────────────────────────────
async function recordDemoGif() {
  console.log('🎬 Recording demo GIF source...')
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({
    viewport: { width: 960, height: 540 },
    recordVideo: { dir: ASSETS_DIR, size: { width: 960, height: 540 } },
    colorScheme: 'dark',
  })

  const page = await context.newPage()

  // Pre-seed localStorage to suppress onboarding
  await page.addInitScript(() => {
    localStorage.setItem('invest-state:tour-completed', 'true')
    localStorage.setItem('invest-hint-dismissed:watchlist-input', 'true')
    localStorage.setItem('invest-hint-dismissed:trace-panel', 'true')
    localStorage.setItem('invest-hint-dismissed:ops-nav', 'true')
    localStorage.setItem('invest-hint-dismissed:dashboard-card', 'true')
  })

  await page.goto(BASE_URL)
  await page.waitForLoadState('networkidle')
  await cleanOverlays(page)

  // Dismiss welcome banner
  const welcome = page.getByRole('button', { name: 'Dismiss welcome message' })
  if (await welcome.isVisible({ timeout: 1000 }).catch(() => false)) {
    await welcome.click({ force: true })
  }
  await sleep(800)

  // Type ticker (human-like speed)
  const input = page.getByRole('textbox', { name: 'Ticker symbol input' })
  await input.click()
  await sleep(300)
  await input.pressSequentially('NVDA', { delay: 140 })
  await sleep(400)

  // Add ticker
  await input.press('Enter')
  await sleep(600)

  // Click Analyze
  const analyzeBtn = page.getByRole('button', { name: 'Analyze 1 stock' })
  await analyzeBtn.click()
  await sleep(800)

  // Start Analysis (confirmation screen)
  const startBtn = page.getByRole('button', { name: 'Start Analysis' })
  await startBtn.click()
  await sleep(1500)

  // Wait for tool calls to stream in, but cut BEFORE debate step appears.
  // The data-fetch phase (5-14s) is visually rich with tool calls firing.
  // Once "Running investment debate..." shows up, the UI stalls on a spinner
  // for 90-120s which looks terrible in a looping GIF.
  const debateOrTimeout = await Promise.race([
    page.locator('text=Running investment debate').waitFor({ timeout: 30000 }),
    sleep(18000), // safety cap: if debate never appears, stop after 18s
  ]).catch(() => null)

  // If debate text appeared, we caught it just in time. Either way,
  // hold 1.5s so the last completed tool calls are visible before cut.
  await sleep(1500)

  // Finalize
  const videoPath = await page.video()?.path()
  await context.close()
  await browser.close()

  if (videoPath) {
    const dest = `${ASSETS_DIR}demo-raw.webm`
    await unlink(dest).catch(() => {})
    await rename(videoPath, dest)
    console.log('  ✓ Saved: docs/assets/demo-raw.webm')
  }
}

// ──────────────────────────────────────────────────────────────────────
// WALKTHROUGH VIDEO: 45s, 1920x1080
// Flow: Home → add ticker → streaming start → jump to completed results
//       → compare → chat → command palette → theme toggle
// ──────────────────────────────────────────────────────────────────────
async function recordWalkthrough() {
  console.log('🎬 Recording walkthrough video...')
  const browser = await chromium.launch({ headless: true })
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    recordVideo: { dir: ASSETS_DIR, size: { width: 1920, height: 1080 } },
    colorScheme: 'dark',
  })

  const page = await context.newPage()

  // Pre-seed localStorage
  await page.addInitScript(() => {
    localStorage.setItem('invest-state:tour-completed', 'true')
    localStorage.setItem('invest-hint-dismissed:watchlist-input', 'true')
    localStorage.setItem('invest-hint-dismissed:trace-panel', 'true')
    localStorage.setItem('invest-hint-dismissed:ops-nav', 'true')
    localStorage.setItem('invest-hint-dismissed:dashboard-card', 'true')
  })

  // Scene 1: Home page (2s)
  await page.goto(BASE_URL)
  await page.waitForLoadState('networkidle')
  await cleanOverlays(page)
  const welcome = page.getByRole('button', { name: 'Dismiss welcome message' })
  if (await welcome.isVisible({ timeout: 1000 }).catch(() => false)) {
    await welcome.click({ force: true })
  }
  await sleep(1500)

  // Scene 2: Add ticker and start analysis (4s)
  const input = page.getByRole('textbox', { name: 'Ticker symbol input' })
  await input.click()
  await sleep(300)
  await input.pressSequentially('AAPL', { delay: 120 })
  await input.press('Enter')
  await sleep(500)

  await page.getByRole('button', { name: 'Analyze 1 stock' }).click()
  await sleep(700)
  await page.getByRole('button', { name: 'Start Analysis' }).click()
  await sleep(2000)

  // Scene 3: Streaming trace (show data fetch completing)
  // Cut before debate spinner, same logic as GIF recording
  await Promise.race([
    page.locator('text=Running investment debate').waitFor({ timeout: 25000 }),
    sleep(16000),
  ]).catch(() => null)
  await sleep(1000)

  // Scene 4: Jump to completed results (use dashboard link to show past analysis)
  // Navigate to dashboard to show completed analyses
  await page.goto(`${BASE_URL}/dashboard`)
  await page.waitForLoadState('networkidle')
  await cleanOverlays(page)
  await sleep(2500)

  // Scene 5: Compare page with pre-analyzed tickers (4s)
  await page.goto(`${BASE_URL}/compare?tickers=TSLA,AAPL`)
  await page.waitForLoadState('networkidle')
  await cleanOverlays(page)
  await sleep(3000)

  // Scene 6: Chat page (3s)
  await page.goto(`${BASE_URL}/chat`)
  await page.waitForLoadState('networkidle')
  await cleanOverlays(page)
  await sleep(2500)

  // Scene 7: Command palette (3s)
  await page.keyboard.press('Meta+k')
  await sleep(2000)
  await page.keyboard.press('Escape')
  await sleep(500)

  // Scene 8: Theme toggle (2s)
  await page.getByRole('button', { name: 'Change theme' }).click()
  await sleep(1500)
  await page.getByRole('button', { name: 'Change theme' }).click()
  await sleep(1000)

  // Scene 9: Explore page (3s)
  await page.goto(`${BASE_URL}/explore`)
  await page.waitForLoadState('networkidle')
  await cleanOverlays(page)
  await sleep(3000)

  // Finalize
  const videoPath = await page.video()?.path()
  await context.close()
  await browser.close()

  if (videoPath) {
    const dest = `${ASSETS_DIR}walkthrough-raw.webm`
    await unlink(dest).catch(() => {})
    await rename(videoPath, dest)
    console.log('  ✓ Saved: docs/assets/walkthrough-raw.webm')
  }
}

// ──────────────────────────────────────────────────────────────────────
// Main
// ──────────────────────────────────────────────────────────────────────
console.log('')
console.log('╔═══════════════════════════════════════════════════════════╗')
console.log('║  Demo Recording Script — AI Investment Analyst           ║')
console.log('╚═══════════════════════════════════════════════════════════╝')
console.log('')

await recordDemoGif()
console.log('')
await recordWalkthrough()

console.log('')
console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
console.log('Post-processing commands:')
console.log('')
console.log('  # GIF (target <5MB for GitHub README)')
console.log('  ffmpeg -y -i docs/assets/demo-raw.webm \\')
console.log('    -vf "fps=12,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=192[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3" \\')
console.log('    -loop 0 docs/assets/demo.gif')
console.log('')
console.log('  # MP4 (h264, web-optimized)')
console.log('  ffmpeg -y -i docs/assets/walkthrough-raw.webm \\')
console.log('    -c:v libx264 -preset slow -crf 22 -pix_fmt yuv420p \\')
console.log('    -movflags +faststart docs/assets/walkthrough.mp4')
console.log('')
console.log('  # If GIF > 5MB, optimize:')
console.log('  gifsicle -O3 --lossy=40 docs/assets/demo.gif -o docs/assets/demo.gif')
console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
