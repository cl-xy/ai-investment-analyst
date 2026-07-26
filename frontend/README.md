# Frontend

React 19 + TypeScript + Vite frontend for the AI Investment Analyst.

## Development

```bash
npm install
npm run dev       # dev server on :5173 (proxies API to :8000)
npm run build     # production build
npm run lint      # oxlint
```

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
│   ├── ThemeToggle.tsx             # Dark/light switch
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

- Dark-first with light mode toggle (CSS custom properties)
- Inter for prose, JetBrains Mono for data/tickers
- Lucide React icons throughout
- Tailwind 3 with semantic color tokens (bullish, bearish, neutral, accent)
- CSS transitions (150ms ease-out), shimmer skeleton loaders
- Accessible: ARIA labels, focus rings, reduced-motion support
