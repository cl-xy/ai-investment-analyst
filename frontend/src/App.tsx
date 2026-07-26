import { useState } from 'react'
import { Route, Routes, useNavigate } from 'react-router-dom'
import ComparePage from './components/ComparePage'
import DashboardPage from './components/DashboardPage'
import EvalPage from './components/EvalPage'
import ExplorePage from './components/ExplorePage'
import Footer from './components/Footer'
import Header from './components/Header'
import StreamingAnalysisPage from './components/StreamingAnalysisPage'
import WatchlistPage from './components/WatchlistPage'

export default function App() {
  const navigate = useNavigate()
  const [tickers, setTickers] = useState<string[]>([])

  const addTicker = (ticker: string) =>
    setTickers((prev) => (prev.includes(ticker) ? prev : [...prev, ticker]))

  const removeTicker = (ticker: string) =>
    setTickers((prev) => prev.filter((t) => t !== ticker))

  const handleAnalyze = () => {
    if (tickers.length === 0) return
    const tickerParam = tickers.map((t) => t.toUpperCase()).join(',')
    navigate(`/analyze?tickers=${encodeURIComponent(tickerParam)}`)
  }

  return (
    <div className="min-h-screen bg-[var(--bg)] flex flex-col">
      <Header />

      <main className="flex-1">
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
        </Routes>
      </main>
      <Footer />
    </div>
  )
}
