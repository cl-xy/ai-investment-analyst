import { useState } from 'react'
import { Route, Routes, useNavigate } from 'react-router-dom'
import DashboardPage from './components/DashboardPage'
import ExplorePage from './components/ExplorePage'
import Header from './components/Header'
import StreamingAnalysisPage from './components/StreamingAnalysisPage'
import TabNav from './components/TabNav'
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
    // Navigate to streaming analysis page
    const tickerParam = tickers.map((t) => t.toUpperCase()).join(',')
    navigate(`/analyze?tickers=${encodeURIComponent(tickerParam)}`)
  }

  return (
    <div className="min-h-screen bg-[var(--bg)]">
      <Header />
      <TabNav loading={false} error={null} />

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
      </Routes>
    </div>
  )
}
