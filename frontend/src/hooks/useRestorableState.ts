import { useState, useEffect, useRef, type Dispatch, type SetStateAction } from 'react'

const STORAGE_PREFIX = 'invest-state:'
const DEBOUNCE_MS = 400

/**
 * State hook that persists to sessionStorage across page refreshes.
 * Debounces writes to avoid blocking the main thread on hot paths (e.g. keystrokes).
 */
export function useRestorableState<T>(key: string, initial: T): [T, Dispatch<SetStateAction<T>>] {
  const storageKey = `${STORAGE_PREFIX}${key}`
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const latestRef = useRef<T>(initial)

  const [value, setValue] = useState<T>(() => {
    if (typeof window === 'undefined') return initial
    try {
      const stored = sessionStorage.getItem(storageKey)
      return stored ? JSON.parse(stored) : initial
    } catch {
      return initial
    }
  })

  // Keep ref in sync after commit (safe for concurrent mode)
  useEffect(() => {
    latestRef.current = value
  })

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      try {
        sessionStorage.setItem(storageKey, JSON.stringify(value))
      } catch {
        // quota exceeded, silently ignore
      }
    }, DEBOUNCE_MS)
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [storageKey, value])

  // Flush on page unload (pagehide fires reliably, effect cleanup does not)
  useEffect(() => {
    const flush = () => {
      try {
        sessionStorage.setItem(storageKey, JSON.stringify(latestRef.current))
      } catch { /* ignore */ }
    }
    window.addEventListener('pagehide', flush)
    return () => {
      flush()
      window.removeEventListener('pagehide', flush)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey])

  return [value, setValue]
}
