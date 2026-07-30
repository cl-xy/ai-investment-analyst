import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { BarChart3, Trash2, Loader2, RefreshCw } from 'lucide-react'
import { deleteAnalysis, getDashboardResult, getDashboardResults } from '../api/analyzeService'
import type { AnalysisListItem, AnalyzeResponse } from '../types/analysis'
import AnalysisCard from './AnalysisCard'
import LoadingSpinner from './LoadingSpinner'
import SearchInput from './ui/SearchInput'
import { toastUndo, toastError, toastSuccess } from '../stores/toastStore'

export default function DashboardPage() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<AnalysisListItem[]>([])
  const [tickerFilter, setTickerFilter] = useState('')
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null)
  const [sessionDetail, setSessionDetail] = useState<AnalyzeResponse | null>(null)
  const [loadingList, setLoadingList] = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [listError, setListError] = useState<string | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const deleteTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map())
  const mountedRef = useRef(true)
  const detailReqIdRef = useRef(0)

  // Cleanup pending delete timers on unmount
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      for (const timer of deleteTimersRef.current.values()) {
        clearTimeout(timer)
      }
      deleteTimersRef.current.clear()
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

  const filteredTickers = useMemo(
    () => uniqueTickers.filter((t) => t.toLowerCase().includes(tickerFilter.toLowerCase())),
    [uniqueTickers, tickerFilter]
  )

  useEffect(() => {
    getDashboardResults()
      .then((data) => {
        if (!mountedRef.current) return
        setSessions(Array.isArray(data) ? data : [])
      })
      .catch((err: unknown) => {
        if (!mountedRef.current) return
        setListError(err instanceof Error ? err.message : 'Failed to load dashboard')
      })
      .finally(() => {
        if (mountedRef.current) setLoadingList(false)
      })
  }, [])

  // Auto-select first ticker once list loads
  useEffect(() => {
    if (uniqueTickers.length > 0 && selectedTicker === null) {
      selectTicker(uniqueTickers[0])
    }
  }, [uniqueTickers, selectedTicker])

  async function selectTicker(ticker: string) {
    const session = tickerSessionMap.get(ticker)
    if (!session) {
      setSelectedTicker(ticker)
      setSessionDetail(null)
      setLoadingDetail(false)
      return
    }
    setSelectedTicker(ticker)
    setDetailError(null)
    setLoadingDetail(true)
    setSessionDetail(null)
    const reqId = ++detailReqIdRef.current
    try {
      const data = await getDashboardResult(session.id)
      if (!mountedRef.current || reqId !== detailReqIdRef.current) return
      setSessionDetail(data)
    } catch (err: unknown) {
      if (!mountedRef.current || reqId !== detailReqIdRef.current) return
      setDetailError(err instanceof Error ? err.message : 'Failed to load analysis')
    } finally {
      if (mountedRef.current && reqId === detailReqIdRef.current) {
        setLoadingDetail(false)
      }
    }
  }

  async function handleDelete() {
    if (!sessionDetail || !selectedTicker) return

    // Guard against double-click while a delete is already pending for this session
    const deletedId = sessionDetail.id
    if (deleteTimersRef.current.has(deletedId)) return

    const deletedTicker = selectedTicker
    const deletedSession = sessions.find((s) => s.id === deletedId)

    // Optimistic remove with undo toast
    setSessions((prev) => prev.filter((s) => s.id !== deletedId))
    setSessionDetail(null)
    setSelectedTicker(null)

    let undone = false

    toastUndo(`Deleted analysis for ${deletedTicker}`, () => {
      undone = true
      // Cancel the pending deletion for this specific item
      const timer = deleteTimersRef.current.get(deletedId)
      if (timer) {
        clearTimeout(timer)
        deleteTimersRef.current.delete(deletedId)
      }
      if (!mountedRef.current) return
      // Restore only the specific deleted session, not the whole snapshot
      if (deletedSession) {
        setSessions((prev) =>
          prev.some((s) => s.id === deletedId) ? prev : [...prev, deletedSession]
        )
      }
      setSelectedTicker(deletedTicker)
    })

    // Delay actual deletion to allow undo
    const timer = setTimeout(async () => {
      deleteTimersRef.current.delete(deletedId)
      if (undone || !mountedRef.current) return
      setDeletingId(deletedId)
      try {
        await deleteAnalysis(deletedId)
        if (mountedRef.current) toastSuccess('Analysis deleted')
      } catch (err: unknown) {
        if (!mountedRef.current) return
        // Rollback on failure: re-insert only the deleted session
        if (deletedSession) {
          setSessions((prev) =>
            prev.some((s) => s.id === deletedId) ? prev : [...prev, deletedSession]
          )
        }
        toastError(err instanceof Error ? err.message : 'Failed to delete analysis')
      } finally {
        if (mountedRef.current) setDeletingId(null)
      }
    }, 5200)
    deleteTimersRef.current.set(deletedId, timer)
  }

  if (loadingList) return <LoadingSpinner />

  if (listError) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16">
        <div className="bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl px-5 py-4 text-sm">
          <strong>Error:</strong> {listError}
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
  const reanalyzeUrl = selectedTicker ? `/analyze?tickers=${encodeURIComponent(selectedTicker)}` : '#'

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 flex flex-col md:flex-row gap-6">
      {/* Sidebar: horizontal scrollable pills on mobile, vertical list on desktop */}
      <aside className="md:w-48 shrink-0">
        <h2 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-3 hidden md:block">
          Stocks
        </h2>
        {/* Ticker search filter (desktop only) */}
        <div className="hidden md:block mb-3">
          <SearchInput
            value={tickerFilter}
            onChange={setTickerFilter}
            placeholder="Filter..."
            aria-label="Filter analyzed tickers"
            size="xs"
          />
        </div>
        <ul className="flex md:flex-col gap-2 overflow-x-auto pb-2 md:pb-0 md:overflow-x-visible">
          {filteredTickers.length === 0 && tickerFilter ? (
            <li className="text-xs text-[var(--text-muted)] px-3 py-2">No matches</li>
          ) : null}
          {filteredTickers.map((ticker, index) => (
            <li key={ticker} className="shrink-0">
              <button
                onClick={() => selectTicker(ticker)}
                {...(index === 0 ? { 'data-hint-target': 'dashboard-card' } : {})}
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
        ) : detailError ? (
          <div className="flex flex-col items-center gap-4 py-16 text-center">
            <div className="bg-red-500/10 border border-red-500/20 text-red-500 rounded-xl px-5 py-4 text-sm max-w-sm">
              <strong>Error:</strong> {detailError}
            </div>
            {selectedTicker && (
              <button
                onClick={() => selectTicker(selectedTicker)}
                className="text-sm text-[var(--accent)] hover:underline"
              >
                Retry
              </button>
            )}
          </div>
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
              <div className="flex items-center gap-3">
                {selectedTicker && (
                  <Link
                    to={reanalyzeUrl}
                    className="flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                    Re-analyze
                  </Link>
                )}
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
            </div>
            <AnalysisCard analysis={analysis} />
          </div>
        ) : selectedTicker && sessionDetail ? (
          <div className="flex flex-col items-center gap-4 py-16 text-center">
            <RefreshCw className="w-10 h-10 text-[var(--text-muted)]" />
            <h3 className="text-base font-medium text-[var(--text-secondary)]">
              No detailed data for {selectedTicker}
            </h3>
            <p className="text-sm text-[var(--text-muted)] max-w-sm">
              This analysis was run before full data persistence was enabled.
              Re-run it to get the complete breakdown.
            </p>
            <Link
              to={reanalyzeUrl}
              className="mt-2 inline-flex items-center gap-2 rounded-lg bg-[var(--accent)] px-4 py-2.5 text-sm font-medium text-white hover:opacity-90 transition-opacity"
            >
              <RefreshCw className="w-4 h-4" />
              Re-analyze {selectedTicker}
            </Link>
          </div>
        ) : null}
      </div>
    </div>
  )
}
