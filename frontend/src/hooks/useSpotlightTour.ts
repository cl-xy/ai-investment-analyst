import { useState, useEffect, useCallback, useRef } from 'react'

export interface TourStep {
  target: string
  title: string
  description: string
  position: 'top' | 'bottom' | 'left' | 'right'
}

export interface SpotlightTourReturn {
  isActive: boolean
  currentStep: number
  totalSteps: number
  step: TourStep | null
  next: () => void
  back: () => void
  skip: () => void
  start: () => void
  targetRect: DOMRect | null
}

const STORAGE_KEY = 'invest-state:tour-completed'

const TOUR_STEPS: TourStep[] = [
  {
    target: '[data-tour-target="ticker-input"]',
    title: 'Add Tickers',
    description:
      'Type any stock ticker symbol and press Enter to add it to your watchlist.',
    position: 'bottom',
  },
  {
    target: '[data-tour-target="demo-cta"]',
    title: 'Quick Demo',
    description:
      'Try a live analysis to see the multi-agent system in action with real market data.',
    position: 'bottom',
  },
  {
    target: '[data-tour-target="nav-explore"]',
    title: 'Explore Markets',
    description:
      'Browse trending stocks, sector movers, and market insights.',
    position: 'bottom',
  },
  {
    target: '[data-tour-target="theme-switcher"]',
    title: 'Personalize',
    description:
      'Choose from 4 dark themes. Each has unique risk-signal encoding.',
    position: 'bottom',
  },
  {
    target: '[data-tour-target="cmd-palette-hint"]',
    title: 'Power User',
    description:
      'Press Cmd+K anytime to open the command palette for quick navigation.',
    position: 'bottom',
  },
]

export function useSpotlightTour(): SpotlightTourReturn {
  const [isActive, setIsActive] = useState(false)
  const [currentStep, setCurrentStep] = useState(0)
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null)
  const rafRef = useRef<number>(0)

  const step = isActive ? TOUR_STEPS[currentStep] ?? null : null

  // Measure the target element position and keep it updated
  const measureTarget = useCallback(() => {
    if (!isActive || !TOUR_STEPS[currentStep]) {
      setTargetRect(null)
      return
    }
    const el = document.querySelector(TOUR_STEPS[currentStep].target)
    if (el) {
      setTargetRect(el.getBoundingClientRect())
    } else {
      // Target not present on this route/page (e.g. tour steps only exist on
      // the watchlist page). Abort the tour entirely instead of leaving
      // isActive=true with no visible UI, which would otherwise make #root
      // inert with no way for the user to see or dismiss it.
      setTargetRect(null)
      setIsActive(false)
      setCurrentStep(0)
    }
  }, [isActive, currentStep])

  // Re-measure on scroll, resize, and step changes
  useEffect(() => {
    if (!isActive) return

    measureTarget()

    const handleUpdate = () => {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = requestAnimationFrame(measureTarget)
    }

    window.addEventListener('resize', handleUpdate)
    window.addEventListener('scroll', handleUpdate, true)

    return () => {
      window.removeEventListener('resize', handleUpdate)
      window.removeEventListener('scroll', handleUpdate, true)
      cancelAnimationFrame(rafRef.current)
    }
  }, [isActive, currentStep, measureTarget])

  // Apply inert attribute to non-spotlighted content.
  // Only while the tour is actually visible (isActive AND a target was
  // found) — otherwise #root would be inert with no visible UI to dismiss it.
  useEffect(() => {
    if (!isActive || !targetRect) return

    const mainContent = document.getElementById('root')
    if (mainContent) {
      mainContent.setAttribute('inert', '')
    }

    return () => {
      if (mainContent) {
        mainContent.removeAttribute('inert')
      }
    }
  }, [isActive, targetRect])

  const complete = useCallback(() => {
    setIsActive(false)
    setCurrentStep(0)
    setTargetRect(null)
    try {
      localStorage.setItem(STORAGE_KEY, 'true')
    } catch {
      // Quota or private browsing, silently ignore
    }
  }, [])

  const next = useCallback(() => {
    if (currentStep >= TOUR_STEPS.length - 1) {
      complete()
    } else {
      setCurrentStep((s) => s + 1)
    }
  }, [currentStep, complete])

  const back = useCallback(() => {
    if (currentStep > 0) {
      setCurrentStep((s) => s - 1)
    }
  }, [currentStep])

  const skip = useCallback(() => {
    complete()
  }, [complete])

  const start = useCallback(() => {
    setCurrentStep(0)
    setIsActive(true)
  }, [])

  // Auto-start on first visit — only on the watchlist page ("/"), since all
  // tour step targets (ticker-input, demo-cta, nav-explore, etc.) only exist
  // there. Starting it on other routes (e.g. a deep link to /analyze) leaves
  // isActive=true with no matching target, which previously made #root inert.
  useEffect(() => {
    if (window.location.pathname !== '/') return
    try {
      const completed = localStorage.getItem(STORAGE_KEY)
      if (!completed) {
        // Small delay to let the page render and targets mount
        const timer = setTimeout(() => {
          setIsActive(true)
        }, 800)
        return () => clearTimeout(timer)
      }
    } catch {
      // localStorage unavailable, don't auto-start
    }
  }, [])

  // Listen for external trigger (e.g., from command palette)
  useEffect(() => {
    function handleStartTour() {
      start()
    }
    document.addEventListener('start-spotlight-tour', handleStartTour)
    return () => document.removeEventListener('start-spotlight-tour', handleStartTour)
  }, [start])

  // Keyboard controls
  useEffect(() => {
    if (!isActive) return

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.preventDefault()
        skip()
      } else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault()
        next()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isActive, next, skip])

  return {
    isActive,
    currentStep,
    totalSteps: TOUR_STEPS.length,
    step,
    next,
    back,
    skip,
    start,
    targetRect,
  }
}
