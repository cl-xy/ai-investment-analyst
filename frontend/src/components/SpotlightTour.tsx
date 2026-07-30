import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useSpotlightTour } from '../hooks/useSpotlightTour'

const PADDING = 8
const ARROW_SIZE = 8

function getTooltipPosition(
  targetRect: DOMRect,
  position: 'top' | 'bottom' | 'left' | 'right',
  tooltipEl: HTMLElement | null
) {
  if (!tooltipEl) return { top: 0, left: 0 }

  const tooltipRect = tooltipEl.getBoundingClientRect()
  const gap = 12

  switch (position) {
    case 'bottom':
      return {
        top: targetRect.bottom + gap + PADDING,
        left: targetRect.left + targetRect.width / 2 - tooltipRect.width / 2,
      }
    case 'top':
      return {
        top: targetRect.top - gap - PADDING - tooltipRect.height,
        left: targetRect.left + targetRect.width / 2 - tooltipRect.width / 2,
      }
    case 'left':
      return {
        top: targetRect.top + targetRect.height / 2 - tooltipRect.height / 2,
        left: targetRect.left - gap - PADDING - tooltipRect.width,
      }
    case 'right':
      return {
        top: targetRect.top + targetRect.height / 2 - tooltipRect.height / 2,
        left: targetRect.right + gap + PADDING,
      }
  }
}

function getArrowStyle(position: 'top' | 'bottom' | 'left' | 'right') {
  const base: React.CSSProperties = {
    position: 'absolute',
    width: 0,
    height: 0,
    borderStyle: 'solid',
  }

  switch (position) {
    case 'bottom':
      return {
        ...base,
        top: -ARROW_SIZE,
        left: '50%',
        transform: 'translateX(-50%)',
        borderWidth: `0 ${ARROW_SIZE}px ${ARROW_SIZE}px ${ARROW_SIZE}px`,
        borderColor: 'transparent transparent var(--surface-elevated) transparent',
      }
    case 'top':
      return {
        ...base,
        bottom: -ARROW_SIZE,
        left: '50%',
        transform: 'translateX(-50%)',
        borderWidth: `${ARROW_SIZE}px ${ARROW_SIZE}px 0 ${ARROW_SIZE}px`,
        borderColor: 'var(--surface-elevated) transparent transparent transparent',
      }
    case 'left':
      return {
        ...base,
        right: -ARROW_SIZE,
        top: '50%',
        transform: 'translateY(-50%)',
        borderWidth: `${ARROW_SIZE}px 0 ${ARROW_SIZE}px ${ARROW_SIZE}px`,
        borderColor: 'transparent transparent transparent var(--surface-elevated)',
      }
    case 'right':
      return {
        ...base,
        left: -ARROW_SIZE,
        top: '50%',
        transform: 'translateY(-50%)',
        borderWidth: `${ARROW_SIZE}px ${ARROW_SIZE}px ${ARROW_SIZE}px 0`,
        borderColor: 'transparent var(--surface-elevated) transparent transparent',
      }
  }
}

export function SpotlightTour() {
  const {
    isActive,
    currentStep,
    totalSteps,
    step,
    next,
    back,
    skip,
    targetRect,
  } = useSpotlightTour()

  const tooltipRef = useRef<HTMLDivElement>(null)
  const positionRef = useRef({ top: 0, left: 0 })

  // Calculate tooltip position after render
  useEffect(() => {
    if (!targetRect || !step || !tooltipRef.current) return
    const pos = getTooltipPosition(targetRect, step.position, tooltipRef.current)
    positionRef.current = pos
    tooltipRef.current.style.top = `${pos.top}px`
    tooltipRef.current.style.left = `${pos.left}px`
  }, [targetRect, step, currentStep])

  const portalTarget = document.getElementById('tour-portal')

  if (!isActive || !step || !targetRect || !portalTarget) return null

  const spotlightStyle: React.CSSProperties = {
    position: 'fixed',
    top: targetRect.top - PADDING,
    left: targetRect.left - PADDING,
    width: targetRect.width + PADDING * 2,
    height: targetRect.height + PADDING * 2,
    zIndex: 9998,
    pointerEvents: 'none',
    background: 'transparent',
    boxShadow: '0 0 0 9999px rgba(0, 0, 0, 0.75)',
    borderRadius: '8px',
    transition: 'all var(--motion-surface) var(--ease-standard)',
  }

  const tooltipStyle: React.CSSProperties = {
    position: 'fixed',
    zIndex: 9999,
    background: 'var(--surface-elevated)',
    border: '1px solid var(--border)',
    borderRadius: '12px',
    padding: '16px 20px',
    maxWidth: '320px',
    minWidth: '260px',
    transition: 'all var(--motion-surface) var(--ease-standard)',
  }

  const isLastStep = currentStep === totalSteps - 1
  const isFirstStep = currentStep === 0

  return createPortal(
    <>
      {/* Spotlight overlay: dims everything except target */}
      <div style={spotlightStyle} aria-hidden="true" />

      {/* Click-capture layer behind tooltip to prevent stray clicks */}
      <div
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 9997,
        }}
        onClick={skip}
        aria-hidden="true"
      />

      {/* Tooltip */}
      <div
        ref={tooltipRef}
        role="dialog"
        aria-label="Onboarding tour"
        aria-modal="false"
        style={tooltipStyle}
      >
        {/* Arrow */}
        <div style={getArrowStyle(step.position)} aria-hidden="true" />

        {/* Content */}
        <h3
          className="text-sm font-semibold mb-1"
          style={{ color: 'var(--text-primary)' }}
        >
          {step.title}
        </h3>
        <p
          className="text-sm mb-4 leading-relaxed"
          style={{ color: 'var(--text-secondary)' }}
          aria-live="polite"
        >
          {step.description}
        </p>

        {/* Footer: step counter + buttons */}
        <div className="flex items-center justify-between">
          <span
            className="text-xs"
            style={{ color: 'var(--text-muted)' }}
            aria-label={`Step ${currentStep + 1} of ${totalSteps}`}
          >
            {currentStep + 1} of {totalSteps}
          </span>

          <div className="flex items-center gap-2">
            <button
              onClick={skip}
              className="px-3 py-1.5 text-xs rounded-md transition-colors hover:opacity-80"
              style={{ color: 'var(--text-muted)' }}
              type="button"
            >
              Skip
            </button>

            {!isFirstStep && (
              <button
                onClick={back}
                className="px-3 py-1.5 text-xs rounded-md border transition-colors hover:opacity-80"
                style={{
                  color: 'var(--text-secondary)',
                  borderColor: 'var(--border)',
                }}
                type="button"
              >
                Back
              </button>
            )}

            <button
              onClick={next}
              className="px-4 py-1.5 text-xs font-medium rounded-md transition-colors hover:opacity-90"
              style={{
                background: 'var(--accent)',
                color: 'var(--bg)',
              }}
              type="button"
            >
              {isLastStep ? 'Done' : 'Next'}
            </button>
          </div>
        </div>
      </div>
    </>,
    portalTarget
  )
}
