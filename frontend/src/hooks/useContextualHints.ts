import { useState, useCallback, useEffect } from 'react'

const STORAGE_PREFIX = 'invest-hint-dismissed:'

interface HintDef {
  id: string
  target: string // CSS selector for the element to attach to
  message: string
  condition?: () => boolean
}

/**
 * Sequential one-shot contextual hints.
 * Each hint fires once per user, stored in localStorage.
 * Only one hint visible at a time.
 */
export function useContextualHints(hints: HintDef[]) {
  const [activeHint, setActiveHint] = useState<HintDef | null>(null)

  const isDismissed = useCallback((id: string): boolean => {
    return localStorage.getItem(`${STORAGE_PREFIX}${id}`) === '1'
  }, [])

  const dismiss = useCallback((id: string) => {
    localStorage.setItem(`${STORAGE_PREFIX}${id}`, '1')
    setActiveHint(null)
  }, [])

  useEffect(() => {
    // Find first undismissed hint whose condition passes and target exists
    const timer = setTimeout(() => {
      for (const hint of hints) {
        if (isDismissed(hint.id)) continue
        if (hint.condition && !hint.condition()) continue
        if (!document.querySelector(hint.target)) continue
        setActiveHint(hint)
        return
      }
      setActiveHint(null)
    }, 800) // Delay to let DOM settle

    return () => clearTimeout(timer)
  }, [hints, isDismissed])

  return { activeHint, dismiss }
}
