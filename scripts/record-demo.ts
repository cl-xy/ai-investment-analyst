import { chromium } from '@playwright/test';
import { execSync } from 'child_process';
import path from 'path';
import fs from 'fs';

/**
 * Records a ~15s demo GIF of the Trace Replay page showing
 * the full analysis pipeline playing back instantly.
 *
 * Strategy:
 * 1. Auth + navigate to /replay WITHOUT recording (avoid dead frames)
 * 2. Load featured trace and wait for content to render
 * 3. Start a SECOND context with recording enabled once content is ready
 * 4. Replay the trace at instant speed so the GIF shows continuous action
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
const GIF_PATH = path.join(OUTPUT_DIR, 'demo.gif');

async function main() {
  fs.mkdirSync(OUTPUT_DIR, { recursive: true });

  console.log('Launching browser...');
  const browser = await chromium.launch({ headless: true });

  // Phase 1: Auth in a non-recorded context, grab cookies
  const setupContext = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    colorScheme: 'dark',
  });
  const setupPage = await setupContext.newPage();

  console.log('Authenticating...');
  await setupPage.goto(DEMO_URL);
  await setupPage.waitForTimeout(1000);

  const passwordInput = setupPage.locator('input[type="password"]');
  if (await passwordInput.isVisible({ timeout: 3000 }).catch(() => false)) {
    await passwordInput.fill(DEMO_PASSWORD);
    await setupPage.locator('button[type="submit"], button:has-text("Enter")').click();
    await setupPage.waitForTimeout(2000);
  }

  // Save auth state (cookies/localStorage)
  const storageState = await setupContext.storageState();
  await setupPage.close();
  await setupContext.close();

  // Phase 2: Open recorded context with auth already done
  console.log('Starting recording context...');
  const recordContext = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    colorScheme: 'dark',
    storageState,
    recordVideo: {
      dir: OUTPUT_DIR,
      size: { width: 1280, height: 720 },
    },
  });
  const page = await recordContext.newPage();

  // Navigate directly to replay (already authenticated via storageState)
  await page.goto(`${DEMO_URL}/replay`);
  await page.waitForTimeout(1500);

  // Click "Featured Demo" and wait for trace to actually load
  console.log('Loading featured demo...');
  const featuredBtn = page.locator('button:has-text("Featured Demo"), button:has-text("featured")').first();
  if (await featuredBtn.isVisible({ timeout: 5000 }).catch(() => false)) {
    await featuredBtn.click();
  } else {
    console.log('No featured button, trying first trace...');
    const firstTrace = page.locator('[data-testid="trace-item"], button:has-text("NVDA")').first();
    if (await firstTrace.isVisible({ timeout: 3000 }).catch(() => false)) {
      await firstTrace.click();
    }
  }

  // Wait for trace content to render (look for node names or event count)
  console.log('Waiting for trace content...');
  try {
    await page.locator('text=/Event \\d+|Router|Fetch Data|Debate/i').first().waitFor({ timeout: 12000 });
  } catch {
    console.log('Content selector timed out, continuing anyway...');
  }
  await page.waitForTimeout(300);

  // Set instant speed and play
  const instantBtn = page.locator('button:has-text("Instant"), button:has-text("instant")').first();
  if (await instantBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await instantBtn.click();
    await page.waitForTimeout(300);
  } else {
    // Fall back to 4x
    const speed4x = page.locator('button:has-text("4x")').first();
    if (await speed4x.isVisible({ timeout: 2000 }).catch(() => false)) {
      await speed4x.click();
      await page.waitForTimeout(300);
    }
  }

  const playBtn = page.locator('button[title="Play"], button:has-text("Play")').first();
  if (await playBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
    await playBtn.click();
  }

  // Let the replay run and show the full pipeline populating
  console.log('Recording replay playback...');
  await page.waitForTimeout(8000);

  // Scroll down to show analysis results
  await page.evaluate(() => window.scrollBy(0, 300));
  await page.waitForTimeout(3000);

  // Scroll back up to show final state
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(2000);

  // Stop recording
  console.log('Stopping recording...');
  await page.close();
  await recordContext.close();
  await browser.close();

  // Find the recorded video
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

  // Convert to GIF, skip first 2s (page load/navigation), cap at 18s total
  console.log('Converting to GIF...');
  try {
    execSync(
      `ffmpeg -y -ss 2 -i "${recordedPath}" -vf "fps=12,scale=1280:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer" -t 16 "${GIF_PATH}"`,
      { stdio: 'inherit' }
    );

    const stats = fs.statSync(GIF_PATH);
    const sizeMB = stats.size / (1024 * 1024);
    console.log(`GIF created: ${GIF_PATH} (${sizeMB.toFixed(1)}MB)`);

    if (sizeMB > 5) {
      console.log('GIF exceeds 5MB, reducing quality...');
      execSync(
        `ffmpeg -y -ss 2 -i "${recordedPath}" -vf "fps=10,scale=960:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=64[p];[s1][p]paletteuse=dither=bayer" -t 14 "${GIF_PATH}"`,
        { stdio: 'inherit' }
      );
      const newStats = fs.statSync(GIF_PATH);
      console.log(`Reduced GIF: ${(newStats.size / (1024 * 1024)).toFixed(1)}MB`);
    }

    // Clean up raw video
    fs.unlinkSync(recordedPath);
    console.log('Done! GIF saved to docs/assets/demo.gif');
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
