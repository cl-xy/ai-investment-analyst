import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BarChart3, Trash2, Loader2 } from 'lucide-react'
import { deleteAnalysis, getDashboardResult, getDashboardResults } from '../api/analyzeService'
import type { AnalysisListItem, AnalyzeResponse } from '../types/analysis'
import AnalysisCard from './AnalysisCard'
import LoadingSpinner from './LoadingSpinner'
import { toastUndo, toastError, toastSuccess } from '../stores/toastStore'

export default function DashboardPage() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<AnalysisListItem[]>([])
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null)
  const [sessionDetail, setSessionDetail] = useState<AnalyzeResponse | null>(null)
  const [loadingList, setLoadingList] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const deleteTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  // Cleanup pending delete timer on unmount
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (deleteTimerRef.current) {
        clearTimeout(deleteTimerRef.current)
        deleteTimerRef.current = null
      }
    }
  }, [])

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

    // Capture immutable snapshot at delete time
    const deletedId = sessionDetail.id
    const deletedTicker = selectedTicker
    const snapshotSessions = sessions
    const snapshotDetail = sessionDetail

    // #4: Optimistic remove with undo toast
    setSessions((prev) => prev.filter((s) => s.id !== deletedId))
    setSessionDetail(null)
    setSelectedTicker(null)

    let undone = false

    // Clear any previous pending delete timer
    if (deleteTimerRef.current) {
      clearTimeout(deleteTimerRef.current)
      deleteTimerRef.current = null
    }

    toastUndo(`Deleted analysis for ${deletedTicker}`, () => {
      undone = true
      // Cancel the pending deletion
      if (deleteTimerRef.current) {
        clearTimeout(deleteTimerRef.current)
        deleteTimerRef.current = null
      }
      // Restore from snapshot (uses captured values, not stale closure)
      setSessions(snapshotSessions)
      setSessionDetail(snapshotDetail)
      setSelectedTicker(deletedTicker)
    })

    // Delay actual deletion to allow undo
    deleteTimerRef.current = setTimeout(async () => {
      deleteTimerRef.current = null
      if (undone || !mountedRef.current) return
      setDeletingId(deletedId)
      try {
        await deleteAnalysis(deletedId)
        if (mountedRef.current) toastSuccess('Analysis deleted')
      } catch (err: unknown) {
        if (!mountedRef.current) return
        // Rollback on failure using snapshot
        setSessions(snapshotSessions)
        setSessionDetail(snapshotDetail)
        setSelectedTicker(deletedTicker)
        toastError(err instanceof Error ? err.message : 'Failed to delete analysis')
      } finally {
        if (mountedRef.current) setDeletingId(null)
      }
    }, 5200)
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
    <div className="max-w-6xl mx-auto px-4 py-8 flex flex-col md:flex-row gap-6">
      {/* Sidebar: horizontal scrollable pills on mobile, vertical list on desktop */}
      <aside className="md:w-48 shrink-0">
        <h2 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-3 hidden md:block">
          Stocks
        </h2>
        <ul className="flex md:flex-col gap-2 overflow-x-auto pb-2 md:pb-0 md:overflow-x-visible">
          {uniqueTickers.map((ticker) => (
            <li key={ticker} className="shrink-0">
              <button
                onClick={() => selectTicker(ticker)}
                className={[
                  'whitespace-nowrap md:w-full md:text-left rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
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
