import { useCallback, useMemo, useState } from 'react'

const COOLDOWN_KEY = 'invest-state:dissent-cooldown'
const COOLDOWN_MS = 24 * 60 * 60 * 1000 // 24 hours
const MIN_INTERACTIONS = 5
const ACCEPTANCE_THRESHOLD = 0.8

export interface DissentState {
  interactions: number
  agreements: number
  shouldPrompt: boolean
  dismiss: () => void
  trackAgreement: () => void
  trackDisagreement: () => void
}

function isCooldownActive(): boolean {
  try {
    const stored = localStorage.getItem(COOLDOWN_KEY)
    if (!stored) return false
    const timestamp = parseInt(stored, 10)
    if (isNaN(timestamp)) return false
    return Date.now() - timestamp < COOLDOWN_MS
  } catch {
    return false
  }
}

export function useDissentDetection(): DissentState {
  const [interactions, setInteractions] = useState(0)
  const [agreements, setAgreements] = useState(0)
  const [dismissed, setDismissed] = useState(() => isCooldownActive())

  const shouldPrompt = useMemo(() => {
    if (dismissed) return false
    if (interactions < MIN_INTERACTIONS) return false
    return agreements / interactions > ACCEPTANCE_THRESHOLD
  }, [interactions, agreements, dismissed])

  const dismiss = useCallback(() => {
    try {
      localStorage.setItem(COOLDOWN_KEY, String(Date.now()))
    } catch {
      // quota exceeded, proceed without persistence
    }
    setDismissed(true)
    setInteractions(0)
    setAgreements(0)
  }, [])

  const trackAgreement = useCallback(() => {
    setInteractions((n) => n + 1)
    setAgreements((n) => n + 1)
  }, [])

  const trackDisagreement = useCallback(() => {
    setInteractions((n) => n + 1)
  }, [])

  return { interactions, agreements, shouldPrompt, dismiss, trackAgreement, trackDisagreement }
}
