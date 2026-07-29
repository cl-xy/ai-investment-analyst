import { chromium } from '@playwright/test';
import { execSync } from 'child_process';
import path from 'path';
import fs from 'fs';

/**
 * Records a 15-20s demo GIF of the Trace Replay page showing
 * the full analysis pipeline at 4x speed.
 *
 * Prerequisites:
 * - ffmpeg installed
 * - Live demo deployed with a featured trace available
 * - npx playwright install chromium
 *
 * Usage: npx tsx scripts/record-demo.ts
 * Output: docs/assets/demo.gif
 */

const DEMO_URL = process.env.DEMO_URL || 'https://ai-investment-analyst-iota.vercel.app';
const DEMO_PASSWORD = process.env.DEMO_PASSWORD || 'investor2026';
const OUTPUT_DIR = path.resolve(__dirname, '../docs/assets');
const VIDEO_PATH = path.join(OUTPUT_DIR, 'demo-raw.webm');
const GIF_PATH = path.join(OUTPUT_DIR, 'demo.gif');

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  console.log('Launching browser...');
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    colorScheme: 'dark',
    recordVideo: {
      dir: OUTPUT_DIR,
      size: { width: 1280, height: 720 },
    },
  });

  const page = await context.newPage();

  // Authenticate
  console.log('Navigating to demo...');
  await page.goto(DEMO_URL);
  await page.waitForTimeout(1000);

  // Check if password gate is shown
  const passwordInput = page.locator('input[type="password"]');
  if (await passwordInput.isVisible({ timeout: 3000 }).catch(() => false)) {
    console.log('Entering demo password...');
    await passwordInput.fill(DEMO_PASSWORD);
    await page.locator('button[type="submit"], button:has-text("Enter")').click();
    await page.waitForTimeout(1500);
  }

  // Navigate to Trace Replay
  console.log('Opening Trace Replay...');
  await page.goto(`${DEMO_URL}/replay`);
  await page.waitForTimeout(2000);

  // Click "Featured Demo" button
  console.log('Loading featured demo...');
  const featuredBtn = page.locator('button:has-text("Featured Demo"), button:has-text("featured")').first();
  if (await featuredBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
    await featuredBtn.click();
    await page.waitForTimeout(1500);
  } else {
    console.log('No featured demo button found, trying first trace...');
    const firstTrace = page.locator('[data-testid="trace-item"], button:has-text("NVDA")').first();
    if (await firstTrace.isVisible({ timeout: 3000 }).catch(() => false)) {
      await firstTrace.click();
      await page.waitForTimeout(1500);
    }
  }

  // Set speed to 4x if controls are visible
  const speed4x = page.locator('button:has-text("4x")').first();
  if (await speed4x.isVisible({ timeout: 3000 }).catch(() => false)) {
    await speed4x.click();
    await page.waitForTimeout(500);
  }

  // Click play
  const playBtn = page.locator('button[title="Play"], button:has-text("Play")').first();
  if (await playBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await playBtn.click();
  }

  // Wait for replay to finish (or timeout at 20s)
  console.log('Recording replay...');
  await page.waitForTimeout(18000);

  // Stop recording
  console.log('Stopping recording...');
  await page.close();
  await context.close();
  await browser.close();

  // Find the recorded video (Playwright names it with a random hash)
  const videos = fs.readdirSync(OUTPUT_DIR).filter(f => f.endsWith('.webm'));
  const latestVideo = videos
    .map(f => ({ name: f, time: fs.statSync(path.join(OUTPUT_DIR, f)).mtimeMs }))
    .sort((a, b) => b.time - a.time)[0];

  if (!latestVideo) {
    console.error('No video file found. Recording may have failed.');
    process.exit(1);
  }

  const recordedPath = path.join(OUTPUT_DIR, latestVideo.name);
  console.log(`Video recorded: ${recordedPath}`);

  // Convert to GIF with ffmpeg
  console.log('Converting to GIF...');
  try {
    execSync(
      `ffmpeg -y -i "${recordedPath}" -vf "fps=12,scale=1280:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer" -t 20 "${GIF_PATH}"`,
      { stdio: 'inherit' }
    );

    // Check file size
    const stats = fs.statSync(GIF_PATH);
    const sizeMB = stats.size / (1024 * 1024);
    console.log(`GIF created: ${GIF_PATH} (${sizeMB.toFixed(1)}MB)`);

    if (sizeMB > 5) {
      console.log('GIF exceeds 5MB, reducing quality...');
      execSync(
        `ffmpeg -y -i "${recordedPath}" -vf "fps=10,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=64[p];[s1][p]paletteuse=dither=bayer" -t 15 "${GIF_PATH}"`,
        { stdio: 'inherit' }
      );
      const newStats = fs.statSync(GIF_PATH);
      console.log(`Reduced GIF: ${(newStats.size / (1024 * 1024)).toFixed(1)}MB`);
    }

    // Clean up raw video
    fs.unlinkSync(recordedPath);
    console.log('Done! GIF saved to docs/assets/demo.gif');
    console.log('Update README.md reference from demo-placeholder.gif to demo.gif');
  } catch (err) {
    console.error('ffmpeg conversion failed. Is ffmpeg installed?');
    console.error('Install: brew install ffmpeg');
    console.log(`Raw video preserved at: ${recordedPath}`);
    process.exit(1);
  }
}

main().catch((err) => {
  console.error('Recording failed:', err);
  process.exit(1);
});
