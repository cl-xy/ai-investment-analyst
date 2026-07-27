import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BarChart3, Trash2, Loader2 } from 'lucide-react'
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
      for (const ticker of session.tickers ?? []) {
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
        setSessions(Array.isArray(data) ? data : [])
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
        <div className="bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl px-5 py-4 text-sm">
          <strong>Error:</strong> {error}
        </div>
      </div>
    )
  }

  if (uniqueTickers.length === 0) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-24 flex flex-col items-center gap-4 text-center">
        <BarChart3 className="w-12 h-12 text-[var(--text-muted)]" />
        <h3 className="text-xl font-semibold text-[var(--text-secondary)]">No analyses yet</h3>
        <p className="text-[var(--text-muted)] text-sm">
          Head to the{' '}
          <button
            onClick={() => navigate('/')}
            className="text-[var(--accent)] hover:underline font-medium"
          >
            Watchlist
          </button>{' '}
          tab, add some stocks, and click Analyze.
        </p>
      </div>
    )
  }

  const analysis = selectedTicker && sessionDetail ? (sessionDetail.analyses ?? {})[selectedTicker] : null
  const sessionDate = tickerSessionMap.get(selectedTicker ?? '')?.created_at

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 flex gap-6">
      {/* Sidebar: one button per stock */}
      <aside className="w-48 shrink-0">
        <h2 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-3">
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
                    ? 'bg-[var(--accent-bg)] border border-[var(--accent)]/20 text-[var(--accent)]'
                    : 'bg-[var(--surface-elevated)] border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--surface)]',
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
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">
                {selectedTicker}
                {sessionDate && (
                  <span className="ml-2 text-sm font-normal text-[var(--text-muted)]">
                    as of {new Date(sessionDate).toLocaleString()}
                  </span>
                )}
              </h2>
              <button
                onClick={handleDelete}
                disabled={!!deletingId}
                title="Delete this analysis"
                className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-red-500 disabled:opacity-40 transition-colors"
              >
                {deletingId ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Trash2 className="w-4 h-4" />
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
