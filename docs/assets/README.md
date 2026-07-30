# Demo Assets

This directory holds media assets for the README and documentation.

## Contents

- `demo.gif` - README hero image (trace replay at 4x speed, 15-20s)
- `walkthrough.mp4` - 75-second video tour (trace replay, ops dashboard, chaos mode, recovery)

## Re-recording

To re-record using Playwright automation:

```bash
# Record demo GIF
npx tsx scripts/record-demo.ts
# Produces: docs/assets/demo.gif

# Record walkthrough video
npx tsx scripts/record-walkthrough.ts
# Produces: docs/assets/walkthrough.mp4
```

Prerequisites: `ffmpeg` installed, Playwright chromium (`npx playwright install chromium`), live demo deployed.
