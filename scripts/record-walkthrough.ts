import { chromium } from '@playwright/test';
import path from 'path';
import fs from 'fs';

/**
 * Records a 60-90s walkthrough video showing:
 * 1. Instant trace replay (Featured Demo)
 * 2. Ops dashboard (SLOs, circuit breakers)
 * 3. Chaos mode (failure injection + graceful degradation)
 * 4. Recovery
 *
 * Prerequisites:
 * - Live demo deployed with featured trace + ops endpoints
 * - npx playwright install chromium
 *
 * Usage: npx tsx scripts/record-walkthrough.ts
 * Output: docs/assets/walkthrough.mp4
 */

const DEMO_URL = process.env.DEMO_URL || 'https://ai-investment-analyst-iota.vercel.app';
const DEMO_PASSWORD = process.env.DEMO_PASSWORD || 'investor2026';
const OUTPUT_DIR = path.resolve(__dirname, '../docs/assets');

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  console.log('Launching browser for walkthrough...');
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    colorScheme: 'dark',
    recordVideo: {
      dir: OUTPUT_DIR,
      size: { width: 1920, height: 1080 },
    },
  });

  const page = await context.newPage();

  // --- Scene 1: Authenticate ---
  console.log('[0s] Authenticating...');
  await page.goto(DEMO_URL);
  await page.waitForTimeout(1000);

  const passwordInput = page.locator('input[type="password"]');
  if (await passwordInput.isVisible({ timeout: 3000 }).catch(() => false)) {
    await passwordInput.fill(DEMO_PASSWORD);
    await page.locator('button[type="submit"], button:has-text("Enter")').click();
    await page.waitForTimeout(2000);
  }

  // --- Scene 2: Watchlist overview (5s) ---
  console.log('[5s] Showing watchlist...');
  await page.waitForTimeout(3000);

  // --- Scene 3: Trace Replay - Featured Demo (15s) ---
  console.log('[10s] Opening Trace Replay...');
  await page.goto(`${DEMO_URL}/replay`);
  await page.waitForTimeout(2000);

  const featuredBtn = page.locator('button:has-text("Featured Demo"), button:has-text("featured")').first();
  if (await featuredBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
    console.log('[12s] Loading featured trace...');
    await featuredBtn.click();
    await page.waitForTimeout(2000);

    // Set instant speed to show everything quickly
    const instantBtn = page.locator('button:has-text("instant")').first();
    if (await instantBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await instantBtn.click();
      await page.waitForTimeout(500);
    }

    const playBtn = page.locator('button[title="Play"], button:has-text("Play")').first();
    if (await playBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await playBtn.click();
    }
    await page.waitForTimeout(5000);
  }

  // Scroll down to show analysis results
  await page.evaluate(() => window.scrollBy(0, 400));
  await page.waitForTimeout(3000);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(1000);

  // --- Scene 4: Ops Dashboard (15s) ---
  console.log('[25s] Opening Ops Dashboard...');
  await page.goto(`${DEMO_URL}/ops`);
  await page.waitForTimeout(4000);

  // Scroll through the dashboard slowly
  await page.evaluate(() => window.scrollBy(0, 300));
  await page.waitForTimeout(3000);
  await page.evaluate(() => window.scrollBy(0, 300));
  await page.waitForTimeout(3000);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(2000);

  // --- Scene 5: Chaos Mode (20s) ---
  console.log('[40s] Enabling Chaos Mode...');
  // Scroll to chaos panel
  const chaosToggle = page.locator('button[aria-label*="Enable"], button[aria-label*="LLM"]').first();
  if (await chaosToggle.isVisible({ timeout: 3000 }).catch(() => false)) {
    await chaosToggle.click();
    await page.waitForTimeout(1500);

    // Confirm if confirmation dialog appears
    const confirmBtn = page.locator('button:has-text("Confirm")').first();
    if (await confirmBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await confirmBtn.click();
    }
    await page.waitForTimeout(3000);

    // Show the red banner
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.waitForTimeout(4000);

    // Disable chaos
    console.log('[55s] Disabling chaos...');
    const disableToggle = page.locator('button[aria-label*="Disable"]').first();
    if (await disableToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      await disableToggle.click();
      await page.waitForTimeout(2000);
    }
  } else {
    console.log('  Chaos toggle not found, skipping...');
    await page.waitForTimeout(5000);
  }

  // --- Scene 6: Quick peek at an ADR (10s) ---
  console.log('[60s] Showing architecture decisions...');
  await page.goto(`${DEMO_URL}/ops`);
  await page.waitForTimeout(3000);

  // Scroll to show the full dashboard one more time
  await page.evaluate(() => window.scrollBy(0, 200));
  await page.waitForTimeout(4000);

  // --- Scene 7: End on watchlist (5s) ---
  console.log('[70s] Back to watchlist...');
  await page.goto(DEMO_URL);
  await page.waitForTimeout(4000);

  // --- Done ---
  console.log('[75s] Stopping recording...');
  await page.close();
  await context.close();
  await browser.close();

  // Find the recorded video
  const videos = fs.readdirSync(OUTPUT_DIR).filter(f => f.endsWith('.webm'));
  const latestVideo = videos
    .map(f => ({ name: f, time: fs.statSync(path.join(OUTPUT_DIR, f)).mtimeMs }))
    .sort((a, b) => b.time - a.time)[0];

  if (!latestVideo) {
    console.error('No video file found.');
    process.exit(1);
  }

  const recordedPath = path.join(OUTPUT_DIR, latestVideo.name);
  const outputPath = path.join(OUTPUT_DIR, 'walkthrough.webm');

  // Rename to final output
  fs.renameSync(recordedPath, outputPath);
  console.log(`\nWalkthrough recorded: ${outputPath}`);
  console.log('');
  console.log('Next steps:');
  console.log('  1. Review the video, trim if needed');
  console.log('  2. Upload to YouTube (unlisted) or convert to MP4:');
  console.log('     ffmpeg -i docs/assets/walkthrough.webm -c:v libx264 -crf 23 docs/assets/walkthrough.mp4');
  console.log('  3. Add the link to README.md ## Video Walkthrough section');
}

main().catch((err) => {
  console.error('Walkthrough recording failed:', err);
  process.exit(1);
});
