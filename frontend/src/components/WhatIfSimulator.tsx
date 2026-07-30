import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { Beaker, X, RotateCcw, ArrowRight, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { useFocusTrap } from '../hooks/useFocusTrap'
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion'

interface WhatIfSimulatorProps {
  analysis: {
    ticker: string
    signal: 'buy' | 'hold' | 'sell' | 'insufficient_data'
    confidence: string
    sentiment_score: number
    bull_case?: string[]
    bear_case?: string[]
    risk_flags?: string[]
  }
  open: boolean
  onClose: () => void
}

type ProjectedSignal = 'buy' | 'hold' | 'sell'

const SIGNAL_BASE_SCORES: Record<string, number> = {
  buy: 0.7,
  hold: 0.0,
  sell: -0.7,
  insufficient_data: 0.0,
}

const WEIGHTS = {
  revenue: 0.35,
  interestRate: -0.20,
  sentiment: 0.25,
  headwinds: -0.20,
}

function scoreToSignal(score: number): ProjectedSignal {
  if (score > 0.3) return 'buy'
  if (score < -0.3) return 'sell'
  return 'hold'
}

function signalColor(signal: ProjectedSignal | 'insufficient_data'): string {
  switch (signal) {
    case 'buy': return 'var(--bullish)'
    case 'sell': return 'var(--bearish)'
    case 'hold':
    case 'insufficient_data':
    default: return 'var(--neutral)'
  }
}

function SignalIcon({ signal, className, style }: { signal: ProjectedSignal | 'insufficient_data'; className?: string; style?: React.CSSProperties }) {
  switch (signal) {
    case 'buy': return <TrendingUp className={className} style={style} />
    case 'sell': return <TrendingDown className={className} style={style} />
    case 'hold':
    case 'insufficient_data':
    default: return <Minus className={className} style={style} />
  }
}

export default function WhatIfSimulator({ analysis, open, onClose }: WhatIfSimulatorProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [closing, setClosing] = useState(false)
  const reducedMotion = usePrefersReducedMotion()

  // Slider state
  const defaultSentiment = analysis.sentiment_score ?? 0
  const defaultHeadwinds = analysis.risk_flags?.length ?? 0

  const [revenueGrowth, setRevenueGrowth] = useState(0)
  const [interestRate, setInterestRate] = useState(0)
  const [sentiment, setSentiment] = useState(defaultSentiment)
  const [headwinds, setHeadwinds] = useState(defaultHeadwinds)

  // Reset sliders when analysis changes or panel opens
  useEffect(() => {
    if (open) {
      setRevenueGrowth(0)
      setInterestRate(0)
      setSentiment(analysis.sentiment_score ?? 0)
      setHeadwinds(analysis.risk_flags?.length ?? 0)
    }
  }, [open, analysis.sentiment_score, analysis.risk_flags?.length])

  // Reset closing state when panel opens
  useEffect(() => {
    if (open) {
      if (closeTimeoutRef.current) {
        clearTimeout(closeTimeoutRef.current)
        closeTimeoutRef.current = null
      }
      setClosing(false)
    }
  }, [open])

  // Clear timeout on unmount
  useEffect(() => {
    return () => {
      if (closeTimeoutRef.current) {
        clearTimeout(closeTimeoutRef.current)
      }
    }
  }, [])

  const handleClose = useCallback(() => {
    if (closing) return
    if (reducedMotion) {
      onClose()
      return
    }
    setClosing(true)
    closeTimeoutRef.current = setTimeout(() => {
      closeTimeoutRef.current = null
      setClosing(false)
      onClose()
    }, 200)
  }, [onClose, reducedMotion, closing])

  const handleReset = useCallback(() => {
    setRevenueGrowth(0)
    setInterestRate(0)
    setSentiment(analysis.sentiment_score ?? 0)
    setHeadwinds(analysis.risk_flags?.length ?? 0)
  }, [analysis.sentiment_score, analysis.risk_flags?.length])

  // Focus trap
  useFocusTrap(panelRef, open)

  // Escape key
  useEffect(() => {
    if (!open) return
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose()
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [open, handleClose])

  // Set inert on siblings
  useEffect(() => {
    if (!open) return
    const main = document.getElementById('main-content')
    const header = document.querySelector('header')
    const footer = document.querySelector('footer')
    main?.setAttribute('inert', '')
    header?.setAttribute('inert', '')
    footer?.setAttribute('inert', '')
    return () => {
      main?.removeAttribute('inert')
      header?.removeAttribute('inert')
      footer?.removeAttribute('inert')
    }
  }, [open])

  // Body scroll lock
  const savedOverflowRef = useRef<string | null>(null)
  useEffect(() => {
    if (!open && !closing) return
    if (savedOverflowRef.current === null) {
      savedOverflowRef.current = document.body.style.overflow
    }
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = savedOverflowRef.current ?? ''
      savedOverflowRef.current = null
    }
  }, [open, closing])

  // Sensitivity calculation
  const baseScore = SIGNAL_BASE_SCORES[analysis.signal] ?? 0

  const adjustedScore = useMemo(() => {
    // Normalize deltas to 0-1 range for the formula
    const revenueDelta = revenueGrowth / 30 // -30..+30 -> -1..+1
    const rateDelta = interestRate / 2.5 // -2..+3 -> -0.8..+1.2 (asymmetric, but close enough)
    const sentimentDelta = sentiment - defaultSentiment // already -1..+1 range change
    const headwindsDelta = headwinds / 5 // 0..5 -> 0..1

    return baseScore
      + revenueDelta * WEIGHTS.revenue
      + rateDelta * WEIGHTS.interestRate
      + sentimentDelta * WEIGHTS.sentiment
      + headwindsDelta * WEIGHTS.headwinds
  }, [baseScore, revenueGrowth, interestRate, sentiment, headwinds, defaultSentiment])

  const projectedSignal = scoreToSignal(adjustedScore)
  const originalSignal = analysis.signal === 'insufficient_data' ? 'hold' : analysis.signal
  const signalChanged = projectedSignal !== originalSignal

  if (!open && !closing) return null

  return (
    <>
      {/* Range input styling */}
      <style>{`
        .whatif-range {
          -webkit-appearance: none;
          appearance: none;
          width: 100%;
          height: 6px;
          border-radius: 3px;
          background: var(--border);
          outline: none;
          cursor: pointer;
        }
        .whatif-range::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 18px;
          height: 18px;
          border-radius: 50%;
          background: var(--accent);
          border: 2px solid var(--surface-elevated);
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
          cursor: pointer;
          transition: transform 150ms ease-out;
        }
        .whatif-range::-webkit-slider-thumb:hover {
          transform: scale(1.15);
        }
        .whatif-range::-moz-range-thumb {
          width: 18px;
          height: 18px;
          border-radius: 50%;
          background: var(--accent);
          border: 2px solid var(--surface-elevated);
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
          cursor: pointer;
        }
        .whatif-range::-moz-range-track {
          height: 6px;
          border-radius: 3px;
          background: var(--border);
        }
        .whatif-range:focus-visible {
          outline: 2px solid var(--accent);
          outline-offset: 3px;
          border-radius: 3px;
        }
        .whatif-signal-badge {
          transition: transform 150ms ease-out, opacity 150ms ease-out;
        }
        .whatif-signal-badge.changed {
          animation: whatif-pulse 300ms ease-out;
        }
        @keyframes whatif-pulse {
          0% { transform: scale(0.9); opacity: 0.7; }
          50% { transform: scale(1.05); }
          100% { transform: scale(1); opacity: 1; }
        }
      `}</style>

      {/* Backdrop */}
      <div
        className={`fixed inset-0 bg-black/50 z-40 transition-opacity ${closing ? 'animate-fade-out' : ''}`}
        onClick={handleClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        ref={panelRef}
        className={`fixed right-0 top-0 bottom-0 w-full max-w-md bg-[var(--surface-elevated)] border-l border-[var(--border)] z-50 overflow-y-auto shadow-xl ${closing ? 'animate-slide-out-right' : 'animate-slide-in-right'}`}
        role="dialog"
        aria-modal="true"
        aria-label={`Stress test simulator for ${analysis.ticker}`}
      >
        {/* Header */}
        <div className="sticky top-0 bg-[var(--surface-elevated)] border-b border-[var(--border)] px-5 py-4 flex items-center justify-between z-10">
          <div className="flex items-center gap-2">
            <Beaker className="w-4 h-4 text-[var(--accent)]" />
            <span className="text-sm font-medium text-[var(--text-primary)]">
              Stress Test: {analysis.ticker}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleReset}
              className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors focus-ring rounded min-w-[44px] min-h-[44px] flex items-center justify-center"
              aria-label="Reset all sliders to defaults"
              title="Reset"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
            <button
              onClick={handleClose}
              className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors focus-ring rounded min-w-[44px] min-h-[44px] flex items-center justify-center"
              aria-label="Close stress test"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="px-5 py-5 space-y-6">
          {/* Description */}
          <p className="text-xs text-[var(--text-muted)] leading-relaxed">
            Adjust assumptions below to see how the investment signal might shift under different scenarios.
          </p>

          {/* Sliders */}
          <div className="space-y-5">
            {/* Revenue Growth */}
            <SliderControl
              label="Revenue Growth"
              value={revenueGrowth}
              min={-30}
              max={30}
              step={1}
              onChange={setRevenueGrowth}
              formatValue={(v) => `${v > 0 ? '+' : ''}${v}%`}
            />

            {/* Interest Rate Change */}
            <SliderControl
              label="Interest Rate Change"
              value={interestRate}
              min={-2}
              max={3}
              step={0.1}
              onChange={setInterestRate}
              formatValue={(v) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`}
            />

            {/* Market Sentiment */}
            <SliderControl
              label="Market Sentiment"
              value={sentiment}
              min={-1}
              max={1}
              step={0.05}
              onChange={setSentiment}
              formatValue={(v) => v.toFixed(2)}
            />

            {/* Sector Headwinds */}
            <SliderControl
              label="Sector Headwinds"
              value={headwinds}
              min={0}
              max={5}
              step={1}
              onChange={setHeadwinds}
              formatValue={(v) => `${v} / 5`}
            />
          </div>

          {/* Projected Signal */}
          <div className="rounded-lg bg-[var(--surface)] border border-[var(--border)] p-4 space-y-3">
            <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
              Projected Signal
            </h3>

            <div className="flex items-center justify-center gap-4">
              {/* Original signal */}
              <div className="flex flex-col items-center gap-1 opacity-50">
                <div
                  className="w-10 h-10 rounded-full flex items-center justify-center"
                  style={{ backgroundColor: `color-mix(in srgb, ${signalColor(originalSignal)} 20%, transparent)` }}
                >
                  <SignalIcon signal={originalSignal} className="w-5 h-5" style={{ color: signalColor(originalSignal) } as React.CSSProperties} />
                </div>
                <span className="text-xs font-medium uppercase" style={{ color: signalColor(originalSignal) }}>
                  {originalSignal}
                </span>
              </div>

              {/* Arrow */}
              <ArrowRight className="w-5 h-5 text-[var(--text-muted)]" />

              {/* Projected signal */}
              <div className={`flex flex-col items-center gap-1 whatif-signal-badge ${signalChanged ? 'changed' : ''}`}>
                <div
                  className="w-10 h-10 rounded-full flex items-center justify-center"
                  style={{ backgroundColor: `color-mix(in srgb, ${signalColor(projectedSignal)} 20%, transparent)` }}
                >
                  <SignalIcon signal={projectedSignal} className="w-5 h-5" style={{ color: signalColor(projectedSignal) } as React.CSSProperties} />
                </div>
                <span className="text-xs font-medium uppercase" style={{ color: signalColor(projectedSignal) }}>
                  {projectedSignal}
                </span>
              </div>
            </div>

            {/* Score indicator */}
            <div className="flex items-center justify-between text-xs text-[var(--text-muted)] pt-2 border-t border-[var(--border)]">
              <span>Composite score</span>
              <span className="font-mono">{adjustedScore.toFixed(3)}</span>
            </div>

            {/* Confidence delta */}
            {signalChanged && (
              <p className="text-xs text-[var(--text-secondary)] text-center">
                Signal shifts from <span className="font-medium" style={{ color: signalColor(originalSignal) }}>{originalSignal}</span> to <span className="font-medium" style={{ color: signalColor(projectedSignal) }}>{projectedSignal}</span> under these assumptions
              </p>
            )}
            {!signalChanged && (
              <p className="text-xs text-[var(--text-muted)] text-center">
                Signal remains unchanged under current assumptions
              </p>
            )}
          </div>

          {/* Weight legend */}
          <div className="rounded-lg bg-[var(--surface)] border border-[var(--border)] p-4">
            <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
              Factor Weights
            </h3>
            <div className="grid grid-cols-2 gap-2 text-xs text-[var(--text-secondary)]">
              <span>Revenue Growth</span>
              <span className="font-mono text-right">+0.35</span>
              <span>Interest Rate</span>
              <span className="font-mono text-right">-0.20</span>
              <span>Market Sentiment</span>
              <span className="font-mono text-right">+0.25</span>
              <span>Sector Headwinds</span>
              <span className="font-mono text-right">-0.20</span>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

/** Reusable slider control */
function SliderControl({
  label,
  value,
  min,
  max,
  step,
  onChange,
  formatValue,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (v: number) => void
  formatValue: (v: number) => string
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm text-[var(--text-secondary)]">{label}</label>
        <span className="text-sm font-mono text-[var(--text-primary)]">
          {formatValue(value)}
        </span>
      </div>
      <input
        type="range"
        className="whatif-range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        aria-label={label}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-valuetext={formatValue(value)}
      />
    </div>
  )
}
