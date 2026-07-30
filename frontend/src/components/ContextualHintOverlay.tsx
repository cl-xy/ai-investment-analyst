import { useContextualHints } from '../hooks/useContextualHints'
import ContextualHint from './ui/ContextualHint'

/**
 * Central hint definitions for all pages.
 * Pages only need to render elements with matching data-hint-target attributes.
 */
const HINT_DEFINITIONS = [
  {
    id: 'watchlist-input',
    target: '[data-hint-target="watchlist-input"]',
    message: 'Type a stock ticker like AAPL or NVDA to get started',
  },
  {
    id: 'trace-panel',
    target: '[data-hint-target="trace-panel"]',
    message: "Watch the agent's reasoning unfold in real-time as it processes your tickers",
  },
  {
    id: 'ops-nav',
    target: '[data-hint-target="ops-nav"]',
    message: 'Check system health, SLOs, and circuit breakers in the Ops Dashboard',
  },
  {
    id: 'dashboard-card',
    target: '[data-hint-target="dashboard-card"]',
    message: 'Click any analysis to see the full evidence and reasoning',
  },
]

/**
 * Global overlay that renders the currently active contextual hint.
 * Mount once in App.tsx. Pages add data-hint-target attributes to their elements.
 */
export default function ContextualHintOverlay() {
  const { activeHint, dismiss } = useContextualHints(HINT_DEFINITIONS)

  if (!activeHint) return null

  return (
    <ContextualHint
      key={activeHint.id}
      message={activeHint.message}
      targetSelector={activeHint.target}
      onDismiss={() => dismiss(activeHint.id)}
    />
  )
}
