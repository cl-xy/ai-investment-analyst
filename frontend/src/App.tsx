import { Suspense, useEffect } from 'react'
import { Link, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { FileQuestion } from 'lucide-react'
import Footer from './components/Footer'
import Header from './components/Header'
import { ErrorBoundary } from './components/ErrorBoundary'
import ToastContainer from './components/ToastContainer'
import OfflineBanner from './components/OfflineBanner'
import LoadingSpinner from './components/LoadingSpinner'
import { useRestorableState } from './hooks/useRestorableState'
import { useRecentTickers } from './hooks/useRecentTickers'
import { lazyRetry } from './utils/lazyRetry'

// #24: Code-split routes with chunk-hash recovery
const WatchlistPage = lazyRetry(() => import('./components/WatchlistPage'))
const StreamingAnalysisPage = lazyRetry(() => import('./components/StreamingAnalysisPage'))
const DashboardPage = lazyRetry(() => import('./components/DashboardPage'))
const ExplorePage = lazyRetry(() => import('./components/ExplorePage'))
const EvalPage = lazyRetry(() => import('./components/EvalPage'))
const ComparePage = lazyRetry(() => import('./components/ComparePage'))
const BacktestPage = lazyRetry(() => import('./components/BacktestPage'))
const ChatPage = lazyRetry(() => import('./components/ChatPage'))
const CalibrationPage = lazyRetry(() => import('./components/CalibrationPage'))
const OpsPage = lazyRetry(() => import('./components/OpsPage'))
const ReplayPage = lazyRetry(() => import('./components/ReplayPage'))

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

export default function App() {
  const navigate = useNavigate()
  // #22: Persist watchlist state across refreshes
  const [tickers, setTickers] = useRestorableState<string[]>('watchlist', [])
  const { recordUsage } = useRecentTickers()

  const addTicker = (ticker: string) => {
    setTickers((prev) => (prev.includes(ticker) ? prev : [...prev, ticker]))
    recordUsage(ticker)
  }

  const removeTicker = (ticker: string) =>
    setTickers((prev) => prev.filter((t) => t !== ticker))

  const handleAnalyze = () => {
    if (tickers.length === 0) return
    const tickerParam = tickers.map((t) => t.toUpperCase()).join(',')
    navigate(`/analyze?tickers=${encodeURIComponent(tickerParam)}`)
  }

  return (
    <div className="min-h-screen bg-[var(--bg)] flex flex-col">
      {/* #15: Skip-to-content link */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-[200] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-[var(--accent)] focus:text-white focus:text-sm focus:font-medium"
      >
        Skip to main content
      </a>

      {/* #11: Offline banner */}
      <OfflineBanner />

      <Header />
      <ScrollToTop />

      <main id="main-content" className="flex-1 animate-fade-in" tabIndex={-1}>
        <ErrorBoundary>
          <Suspense fallback={<LoadingSpinner />}>
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
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>
      <Footer />

      {/* #8: Global toast notification system */}
      <ToastContainer />
    </div>
  )
}
