import { chromium } from '@playwright/test';
import { execSync } from 'child_process';
import path from 'path';
import fs from 'fs';

/**
 * Records a 60-75s walkthrough video showing:
 * 1. Instant trace replay (Featured Demo)
 * 2. Ops dashboard (SLOs, circuit breakers)
 * 3. Chaos mode (failure injection + graceful degradation)
 * 4. Recovery
 *
 * Strategy: Auth in unrecorded context, then record only the interesting parts.
 *
 * Prerequisites:
 * - ffmpeg installed
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

  console.log('Launching browser...');
  const browser = await chromium.launch({ headless: true });

  // Phase 1: Auth in unrecorded context
  const setupContext = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    colorScheme: 'dark',
  });
  const setupPage = await setupContext.newPage();

  console.log('[setup] Authenticating...');
  await setupPage.goto(DEMO_URL);
  await setupPage.waitForTimeout(1000);

  const passwordInput = setupPage.locator('input[type="password"]');
  if (await passwordInput.isVisible({ timeout: 3000 }).catch(() => false)) {
    await passwordInput.fill(DEMO_PASSWORD);
    await setupPage.locator('button[type="submit"], button:has-text("Enter")').click();
    await setupPage.waitForTimeout(2000);
  }

  const storageState = await setupContext.storageState();
  await setupPage.close();
  await setupContext.close();

  // Phase 2: Recorded context (already authenticated)
  console.log('[record] Starting recorded session...');
  const recordContext = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    colorScheme: 'dark',
    storageState,
    recordVideo: {
      dir: OUTPUT_DIR,
      size: { width: 1920, height: 1080 },
    },
  });
  const page = await recordContext.newPage();

  // --- Scene 1: Watchlist (5s) ---
  console.log('[0s] Showing watchlist...');
  await page.goto(DEMO_URL);
  await page.waitForTimeout(4000);

  // --- Scene 2: Trace Replay - Featured Demo (20s) ---
  console.log('[5s] Opening Trace Replay...');
  await page.goto(`${DEMO_URL}/replay`);
  await page.waitForTimeout(1500);

  const featuredBtn = page.locator('button:has-text("Featured Demo"), button:has-text("featured")').first();
  if (await featuredBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
    console.log('[7s] Loading featured trace...');
    await featuredBtn.click();

    // Wait for content to actually load
    try {
      await page.locator('text=/Event \\d+|Router|Fetch Data|Debate/i').first().waitFor({ timeout: 12000 });
    } catch {
      console.log('  Content wait timed out, continuing...');
    }
    await page.waitForTimeout(500);

    // Set instant speed (target speed control buttons specifically, not the featured button)
    const instantBtn = page.locator('button:has-text("Instant"):not([disabled])').first();
    if (await instantBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await instantBtn.click();
      await page.waitForTimeout(300);
    } else {
      const speed4x = page.locator('button:has-text("4x"):not([disabled])').first();
      if (await speed4x.isVisible({ timeout: 2000 }).catch(() => false)) {
        await speed4x.click();
        await page.waitForTimeout(300);
      }
    }

    const playBtn = page.locator('button[title="Play"], button:has-text("Play"):not([disabled])').first();
    if (await playBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await playBtn.click();
    }
    await page.waitForTimeout(5000);
  }

  // Scroll down to show analysis results
  await page.evaluate(() => window.scrollBy(0, 400));
  await page.waitForTimeout(3000);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(1000);

  // --- Scene 3: Ops Dashboard (15s) ---
  console.log('[25s] Opening Ops Dashboard...');
  await page.goto(`${DEMO_URL}/ops`);
  await page.waitForTimeout(4000);

  // Scroll through the dashboard
  await page.evaluate(() => window.scrollBy(0, 300));
  await page.waitForTimeout(3000);
  await page.evaluate(() => window.scrollBy(0, 300));
  await page.waitForTimeout(3000);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(2000);

  // --- Scene 4: Chaos Mode (20s) ---
  console.log('[40s] Enabling Chaos Mode...');
  const chaosToggle = page.locator('button[aria-label*="Enable"], button[aria-label*="LLM"]').first();
  if (await chaosToggle.isVisible({ timeout: 3000 }).catch(() => false)) {
    await chaosToggle.click();
    await page.waitForTimeout(1500);

    const confirmBtn = page.locator('button:has-text("Confirm")').first();
    if (await confirmBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await confirmBtn.click();
    }
    await page.waitForTimeout(3000);

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
    console.log('  Chaos toggle not found, showing dashboard instead...');
    await page.waitForTimeout(5000);
  }

  // --- Scene 5: Back to ops for final state (5s) ---
  console.log('[60s] Final ops state...');
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(3000);

  // --- Scene 6: End on watchlist (5s) ---
  console.log('[65s] Back to watchlist...');
  await page.goto(DEMO_URL);
  await page.waitForTimeout(4000);

  // --- Done ---
  console.log('[70s] Stopping recording...');
  await page.close();
  await recordContext.close();
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
  const mp4Path = path.join(OUTPUT_DIR, 'walkthrough.mp4');

  // Convert webm to mp4 (GitHub renders mp4 inline, not webm)
  console.log('Converting to MP4...');
  try {
    execSync(
      `ffmpeg -y -i "${recordedPath}" -c:v libx264 -crf 23 -preset fast -pix_fmt yuv420p "${mp4Path}"`,
      { stdio: 'inherit' }
    );
    const stats = fs.statSync(mp4Path);
    console.log(`Walkthrough: ${mp4Path} (${(stats.size / (1024 * 1024)).toFixed(1)}MB)`);
    fs.unlinkSync(recordedPath);
  } catch {
    console.error('ffmpeg mp4 conversion failed.');
    console.log(`Raw webm preserved: ${recordedPath}`);
    process.exit(1);
  }

  console.log('Done!');
}

main().catch((err) => {
  console.error('Walkthrough recording failed:', err);
  process.exit(1);
});
