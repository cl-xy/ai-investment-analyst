import { useState, useCallback, useEffect, useRef } from 'react'

const STORAGE_PREFIX = 'invest-hint-dismissed:'

interface HintDef {
  id: string
  target: string // CSS selector for the element to attach to
  message: string
  condition?: () => boolean
}

function safeGetItem(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSetItem(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Storage unavailable (private mode, quota, policy)
  }
}

function safeQuerySelector(selector: string): Element | null {
  try {
    return document.querySelector(selector)
  } catch {
    return null
  }
}

/**
 * Sequential one-shot contextual hints.
 * Each hint fires once per user, stored in localStorage.
 * Only one hint visible at a time.
 */
export function useContextualHints(hints: HintDef[]) {
  const [activeHint, setActiveHint] = useState<HintDef | null>(null)
  const [dismissVersion, setDismissVersion] = useState(0)
  const hintsRef = useRef(hints)
  hintsRef.current = hints

  // Derive a stable key from hint IDs so inline arrays don't restart the effect
  const hintsKey = hints.map((h) => h.id).join('|')

  const isDismissed = useCallback((id: string): boolean => {
    return safeGetItem(`${STORAGE_PREFIX}${id}`) === '1'
  }, [])

  const dismiss = useCallback((id: string) => {
    safeSetItem(`${STORAGE_PREFIX}${id}`, '1')
    setActiveHint(null)
    setDismissVersion((v) => v + 1)
  }, [])

  useEffect(() => {
    // Find first undismissed hint whose condition passes and target exists
    const timer = setTimeout(() => {
      for (const hint of hintsRef.current) {
        if (isDismissed(hint.id)) continue
        if (hint.condition && !hint.condition()) continue
        if (!safeQuerySelector(hint.target)) continue
        setActiveHint(hint)
        return
      }
      setActiveHint(null)
    }, 800) // Delay to let DOM settle

    return () => clearTimeout(timer)
    // hintsKey: re-scan when hint definitions change (by id)
    // dismissVersion: re-scan after a hint is dismissed
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hintsKey, dismissVersion, isDismissed])

  return { activeHint, dismiss }
}
