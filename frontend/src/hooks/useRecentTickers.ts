import { useState, useCallback, useEffect, useRef } from 'react'

interface RecentEntry {
  ticker: string
  count: number
  lastUsed: number
  pinned?: boolean
}

const STORAGE_KEY = 'invest-recents'
const MAX_RECENTS = 8
const MAX_STORED = 50
const MS_PER_DAY = 86_400_000
const STALE_DAYS = 30

/**
 * Frequency-weighted recent tickers with time-decay scoring.
 * Score = count / (daysSinceLastUse + 1)^1.5
 */
export function useRecentTickers() {
  const [entries, setEntries] = useState<RecentEntry[]>(() => loadEntries())
  const isInitialMount = useRef(true)

  // Persist to localStorage after state commits (not inside updater)
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false
      return
    }
    saveEntries(entries)
  }, [entries])

  const recordUsage = useCallback((ticker: string) => {
    setEntries((prev) => {
      const now = Date.now()
      const existing = prev.find((e) => e.ticker === ticker)
      let updated: RecentEntry[]

      if (existing) {
        updated = prev.map((e) =>
          e.ticker === ticker ? { ...e, count: e.count + 1, lastUsed: now } : e,
        )
      } else {
        updated = [...prev, { ticker, count: 1, lastUsed: now }]
      }

      // Prune stale entries
      updated = updated.filter(
        (e) => e.pinned || (now - e.lastUsed) / MS_PER_DAY < STALE_DAYS,
      )

      // Cap storage to prevent unbounded growth
      if (updated.length > MAX_STORED) {
        updated = updated
          .slice()
          .sort((a, b) => computeScore(b, now) - computeScore(a, now))
          .slice(0, MAX_STORED)
      }

      return updated
    })
  }, [])

  const getSuggestions = useCallback(
    (exclude: string[] = []): string[] => {
      const now = Date.now()
      return [...entries]
        .filter((e) => !exclude.includes(e.ticker))
        .sort((a, b) => computeScore(b, now) - computeScore(a, now))
        .slice(0, MAX_RECENTS)
        .map((e) => e.ticker)
    },
    [entries],
  )

  return { recordUsage, getSuggestions, entries }
}

function computeScore(entry: RecentEntry, now: number): number {
  if (entry.pinned) return entry.count * 1000
  const daysSince = Math.max(0, (now - entry.lastUsed) / MS_PER_DAY)
  return entry.count / Math.pow(daysSince + 1, 1.5)
}

function isValidEntry(value: unknown): value is RecentEntry {
  if (typeof value !== 'object' || value === null) return false
  const obj = value as Record<string, unknown>
  return (
    typeof obj.ticker === 'string' &&
    obj.ticker.length > 0 &&
    typeof obj.count === 'number' &&
    Number.isFinite(obj.count) &&
    obj.count > 0 &&
    typeof obj.lastUsed === 'number' &&
    Number.isFinite(obj.lastUsed) &&
    obj.lastUsed > 0
  )
}

function loadEntries(): RecentEntry[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) return []
    const parsed: unknown = JSON.parse(stored)
    if (!Array.isArray(parsed)) return []
    return parsed.filter(isValidEntry)
  } catch {
    return []
  }
}

function saveEntries(entries: RecentEntry[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
  } catch {
    // quota exceeded or storage unavailable
  }
}
