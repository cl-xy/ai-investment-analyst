# Frontend

React 19 + TypeScript + Vite frontend for the AI Investment Analyst.

## Development

```bash
npm install
npm run dev       # dev server on :5173 (proxies API to :8000)
npm run build     # production build
npm run lint      # oxlint
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `VITE_API_URL` | Backend base URL (required in production; empty uses same-origin in dev) |
| `VITE_DEMO_PASSWORD` | Demo password sent with API requests, if the backend has `DEMO_PASSWORD` set |
| `VITE_TELEGRAM_BOT_USERNAME` | Telegram bot username (without `@`) used to build the "Connect on Telegram" deep link on `/alerts`. Leave unset to hide the link. |

## Structure

```
src/
├── components/          # UI components
│   ├── StreamingAnalysisPage.tsx   # Main streaming experience
│   ├── AgentTracePanel.tsx         # Real-time execution trace
│   ├── TraceEvent.tsx              # Individual trace rows
│   ├── WatchlistPage.tsx           # Ticker input + demo CTA
│   ├── ComparePage.tsx             # Side-by-side comparison
│   ├── EvalPage.tsx                # Eval metrics dashboard
│   ├── ThemeSwitcher.tsx            # Multi-theme selector (4 dark themes)
│   └── DataFreshness.tsx           # "Data as of" badges
├── hooks/
│   └── useAnalysisStream.ts        # SSE EventSource with backoff
├── stores/
│   └── analysisStore.ts            # Zustand streaming state
├── types/
│   └── stream.ts                   # Domain event types
└── index.css                       # Design tokens + animations
```

## Design

- Dark-first with 4 theme options (petroleum, plum, moss, graphite) via CSS custom properties
- Inter for prose, JetBrains Mono for data/tickers
- Lucide React icons throughout
- Tailwind 3 with semantic color tokens (bullish, bearish, neutral, accent)
- CSS transitions (150ms ease-out), shimmer skeleton loaders
- Accessible: ARIA labels, focus rings, reduced-motion support
