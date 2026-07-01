import { useState } from 'react'
import { Route, Routes, useNavigate } from 'react-router-dom'
import { analyzeStocks } from './api/analyzeService'
import DashboardPage from './components/DashboardPage'
import ExplorePage from './components/ExplorePage'
import Header from './components/Header'
import TabNav from './components/TabNav'
import WatchlistPage from './components/WatchlistPage'

export default function App() {
  const navigate = useNavigate()
  const [tickers, setTickers] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const addTicker = (ticker: string) =>
    setTickers((prev) => (prev.includes(ticker) ? prev : [...prev, ticker]))

  const removeTicker = (ticker: string) =>
    setTickers((prev) => prev.filter((t) => t !== ticker))

  const handleAnalyze = async () => {
    if (tickers.length === 0) return
    setLoading(true)
    setError(null)
    navigate('/dashboard')
    try {
      await analyzeStocks({ tickers })
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'An unexpected error occurred'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <TabNav loading={loading} error={error} />

      <Routes>
        <Route
          path="/"
          element={
            <WatchlistPage
              tickers={tickers}
              onAdd={addTicker}
              onRemove={removeTicker}
              onAnalyze={handleAnalyze}
              loading={loading}
            />
          }
        />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/explore" element={<ExplorePage />} />
      </Routes>
    </div>
  )
}
