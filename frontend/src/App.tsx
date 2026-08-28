import { Suspense, useEffect, useRef } from 'react'
import { Link, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { FileQuestion } from 'lucide-react'
import Footer from './components/Footer'
import Header from './components/Header'
import { ErrorBoundary } from './components/ErrorBoundary'
import ToastContainer from './components/ToastContainer'
import OfflineBanner from './components/OfflineBanner'
import CommandPalette from './components/CommandPalette'
import KeyboardShortcutsDialog from './components/KeyboardShortcutsDialog'
import ContextualHintOverlay from './components/ContextualHintOverlay'
import { SpotlightTour } from './components/SpotlightTour'
import { DefaultSkeleton } from './components/ui/PageSkeleton'
import { useRestorableState } from './hooks/useRestorableState'
import { useRecentTickers } from './hooks/useRecentTickers'
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts'
import { toastUndo } from './stores/toastStore'
import { lazyRetry } from './utils/lazyRetry'

// #24: Code-split routes with chunk-hash recovery
const WatchlistPage = lazyRetry(() => import('./components/WatchlistPage'), 'WatchlistPage')
const StreamingAnalysisPage = lazyRetry(() => import('./components/StreamingAnalysisPage'), 'StreamingAnalysisPage')
const DashboardPage = lazyRetry(() => import('./components/DashboardPage'), 'DashboardPage')
const ExplorePage = lazyRetry(() => import('./components/ExplorePage'), 'ExplorePage')
const EvalPage = lazyRetry(() => import('./components/EvalPage'), 'EvalPage')
const ComparePage = lazyRetry(() => import('./components/ComparePage'), 'ComparePage')
const BacktestPage = lazyRetry(() => import('./components/BacktestPage'), 'BacktestPage')
const ChatPage = lazyRetry(() => import('./components/ChatPage'), 'ChatPage')
const CalibrationPage = lazyRetry(() => import('./components/CalibrationPage'), 'CalibrationPage')
const OpsPage = lazyRetry(() => import('./components/OpsPage'), 'OpsPage')
const ReplayPage = lazyRetry(() => import('./components/ReplayPage'), 'ReplayPage')
const AlertsPage = lazyRetry(() => import('./components/AlertsPage'), 'AlertsPage')

function ScrollToTop() {
  const { pathname } = useLocation()
  useEffect(() => { window.scrollTo(0, 0) }, [pathname])
  return null
}

function NotFoundPage() {
  return (
    <div className="flex flex-col items-center text-center py-16 gap-4">
      <div className="text-[var(--text-muted)]">
        <FileQuestion className="w-12 h-12" />
      </div>
      <div>
        <h3 className="text-lg font-semibold text-[var(--text-secondary)]">
          Page not found
        </h3>
        <p className="text-sm text-[var(--text-muted)] mt-1 max-w-sm mx-auto">
          The page you're looking for doesn't exist or has been moved.
        </p>
      </div>
      <Link
        to="/"
        className="text-sm font-medium text-[var(--accent)] hover:underline focus-ring rounded px-3 py-2 min-h-[44px] inline-flex items-center"
      >
        Go Home
      </Link>
    </div>
  )
}

// Validate ticker format: 1-10 alphanumeric chars and dots (matches backend)
const TICKER_PATTERN = /^[A-Z0-9.]{1,10}$/

function normalizeTicker(raw: string): string | null {
  const cleaned = raw.trim().toUpperCase()
  if (!cleaned || !TICKER_PATTERN.test(cleaned)) return null
  return cleaned
}

// Defensive: ensure restored sessionStorage value is a valid string[]
function validateTickers(restored: unknown): string[] {
  if (!Array.isArray(restored)) return []
  return restored.filter((item): item is string => typeof item === 'string' && item.length > 0)
}

export default function App() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const { helpOpen, setHelpOpen } = useKeyboardShortcuts()
  // #22: Persist watchlist state across refreshes
  const [rawTickers, setTickers] = useRestorableState<string[]>('watchlist', [])
  const { recordUsage } = useRecentTickers()

  // Defensive validation of restored state
  const tickers = validateTickers(rawTickers)

  // Keep a ref to latest tickers to avoid stale-closure in handleAnalyze
  const tickersRef = useRef(tickers)
  tickersRef.current = tickers

  const addTicker = (ticker: string) => {
    const normalized = normalizeTicker(ticker)
    if (!normalized) return
    const current = validateTickers(tickersRef.current)
    if (current.includes(normalized)) return
    setTickers((prev) => {
      const valid = validateTickers(prev)
      if (valid.includes(normalized)) return valid
      return [...valid, normalized]
    })
    recordUsage(normalized)
  }

  const removeTicker = (ticker: string) => {
    const normalized = normalizeTicker(ticker)
    if (!normalized) return
    const currentTickers = tickersRef.current
    const index = currentTickers.indexOf(normalized)
    if (index === -1) return

    setTickers((prev) => validateTickers(prev).filter((t) => t !== normalized))

    toastUndo(`Removed ${normalized}`, () => {
      setTickers((prev) => {
        const next = [...prev]
        next.splice(Math.min(index, next.length), 0, normalized)
        return next
      })
    })
  }

  const handleAnalyze = () => {
    const current = tickersRef.current
    if (current.length === 0) return
    const tickerParam = current.join(',')
    navigate(`/analyze?tickers=${encodeURIComponent(tickerParam)}`)
  }

  return (
    <div className="min-h-screen bg-[var(--bg)] flex flex-col">
      {/* #15: Skip-to-content link */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[200] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-[var(--accent)] focus:text-white focus:text-sm focus:font-medium"
      >
        Skip to main content
      </a>

      {/* #11: Offline banner */}
      <OfflineBanner />

      <Header />
      <ScrollToTop />

      <main id="main-content" className="flex-1 animate-fade-in" tabIndex={-1}>
        <ErrorBoundary key={pathname}>
          <Suspense fallback={<DefaultSkeleton />}>
            <Routes>
              <Route
                path="/"
                element={
                  <WatchlistPage
                    tickers={tickers}
                    onAdd={addTicker}
                    onRemove={removeTicker}
                    onAnalyze={handleAnalyze}
                    loading={false}
                  />
                }
              />
              <Route path="/analyze" element={<StreamingAnalysisPage />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/explore" element={<ExplorePage />} />
              <Route path="/evals" element={<EvalPage />} />
              <Route path="/compare" element={<ComparePage />} />
              <Route path="/backtest" element={<BacktestPage />} />
              <Route path="/chat" element={<ChatPage />} />
              <Route path="/calibration" element={<CalibrationPage />} />
              <Route path="/ops" element={<OpsPage />} />
              <Route path="/replay" element={<ReplayPage />} />
              <Route path="/alerts" element={<AlertsPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>
      <Footer />

      {/* #8: Global toast notification system */}
      <ToastContainer />

      {/* Command palette (Cmd+K) */}
      <CommandPalette />

      {/* Keyboard shortcuts help (Cmd+Shift+?) */}
      <KeyboardShortcutsDialog open={helpOpen} onClose={() => setHelpOpen(false)} />

      {/* Contextual hints for first-time users */}
      <ContextualHintOverlay />

      {/* Spotlight onboarding tour */}
      <SpotlightTour />
    </div>
  )
}
