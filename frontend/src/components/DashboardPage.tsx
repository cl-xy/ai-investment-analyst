import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { deleteAnalysis, getDashboardResult, getDashboardResults } from '../api/analyzeService'
import type { AnalysisListItem, AnalyzeResponse } from '../types/analysis'
import AnalysisCard from './AnalysisCard'
import LoadingSpinner from './LoadingSpinner'

export default function DashboardPage() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<AnalysisListItem[]>([])
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null)
  const [sessionDetail, setSessionDetail] = useState<AnalyzeResponse | null>(null)
  const [loadingList, setLoadingList] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Derive unique tickers sorted alphabetically, with their most recent session
  const tickerSessionMap = useMemo(() => {
    const map = new Map<string, AnalysisListItem>()
    const sorted = [...sessions].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    )
    for (const session of sorted) {
      for (const ticker of session.tickers) {
        if (!map.has(ticker)) map.set(ticker, session)
      }
    }
    return map
  }, [sessions])

  const uniqueTickers = useMemo(
    () => Array.from(tickerSessionMap.keys()).sort(),
    [tickerSessionMap]
  )

  useEffect(() => {
    getDashboardResults()
      .then((data) => {
        setSessions(data)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Failed to load dashboard')
      })
      .finally(() => setLoadingList(false))
  }, [])

  // Auto-select first ticker once list loads
  useEffect(() => {
    if (uniqueTickers.length > 0 && selectedTicker === null) {
      selectTicker(uniqueTickers[0])
    }
  }, [uniqueTickers])

  async function selectTicker(ticker: string) {
    setSelectedTicker(ticker)
    const session = tickerSessionMap.get(ticker)
    if (!session) return
    setLoadingDetail(true)
    setSessionDetail(null)
    try {
      const data = await getDashboardResult(session.id)
      setSessionDetail(data)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load analysis')
    } finally {
      setLoadingDetail(false)
    }
  }

  async function handleDelete() {
    if (!sessionDetail || !selectedTicker) return
    setDeletingId(sessionDetail.id)
    try {
      await deleteAnalysis(sessionDetail.id)
      const updatedSessions = sessions.filter((s) => s.id !== sessionDetail.id)
      setSessions(updatedSessions)
      setSessionDetail(null)
      setSelectedTicker(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to delete analysis')
    } finally {
      setDeletingId(null)
    }
  }

  if (loadingList) return <LoadingSpinner />

  if (error) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16">
        <div className="bg-red-50 border border-red-200 text-red-800 rounded-xl px-5 py-4 text-sm">
          <strong>Error:</strong> {error}
        </div>
      </div>
    )
  }

  if (uniqueTickers.length === 0) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-24 flex flex-col items-center gap-4 text-center">
        <span className="text-5xl">📊</span>
        <h3 className="text-xl font-semibold text-gray-700">No analyses yet</h3>
        <p className="text-gray-400 text-sm">
          Head to the{' '}
          <button
            onClick={() => navigate('/')}
            className="text-blue-600 hover:underline font-medium"
          >
            Watchlist
          </button>{' '}
          tab, add some stocks, and click Analyze.
        </p>
      </div>
    )
  }

  const analysis = selectedTicker && sessionDetail ? sessionDetail.analyses[selectedTicker] : null
  const sessionDate = tickerSessionMap.get(selectedTicker ?? '')?.created_at

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 flex gap-6">
      {/* Sidebar: one button per stock */}
      <aside className="w-48 shrink-0">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          Stocks
        </h2>
        <ul className="space-y-2">
          {uniqueTickers.map((ticker) => (
            <li key={ticker}>
              <button
                onClick={() => selectTicker(ticker)}
                className={[
                  'w-full text-left rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                  selectedTicker === ticker
                    ? 'bg-blue-50 border border-blue-200 text-blue-700'
                    : 'bg-white border border-gray-200 text-gray-700 hover:bg-gray-50',
                ].join(' ')}
              >
                {ticker}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      {/* Main: selected stock's analysis */}
      <div className="flex-1 min-w-0">
        {loadingDetail ? (
          <LoadingSpinner />
        ) : analysis ? (
          <div className="space-y-5">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-800">
                {selectedTicker}
                {sessionDate && (
                  <span className="ml-2 text-sm font-normal text-gray-400">
                    as of {new Date(sessionDate).toLocaleString()}
                  </span>
                )}
              </h2>
              <button
                onClick={handleDelete}
                disabled={!!deletingId}
                title="Delete this analysis"
                className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-red-500 disabled:opacity-40 transition-colors"
              >
                {deletingId ? (
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7V4h6v3M4 7h16" />
                  </svg>
                )}
                Delete
              </button>
            </div>
            <AnalysisCard analysis={analysis} />
          </div>
        ) : null}
      </div>
    </div>
  )
}
