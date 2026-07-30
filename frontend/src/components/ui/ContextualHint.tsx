import { useEffect, useRef, useState, useCallback } from 'react'

interface ContextualHintProps {
  message: string
  targetSelector: string
  onDismiss: () => void
}

/**
 * Floating tooltip that anchors to a data-hint-target element.
 * Appears below the target by default, flips above if near viewport bottom.
 */
export default function ContextualHint({ message, targetSelector, onDismiss }: ContextualHintProps) {
  const tooltipRef = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState<{ top: number; left: number; arrowLeft: number; above: boolean } | null>(null)
  const [visible, setVisible] = useState(false)
  const rafRef = useRef<number>(0)

  const calculatePosition = useCallback(() => {
    const target = document.querySelector(targetSelector)
    const tooltip = tooltipRef.current
    if (!target || !tooltip) return

    const rect = target.getBoundingClientRect()
    const tooltipRect = tooltip.getBoundingClientRect()
    const gap = 10

    // Determine if we should flip above
    const spaceBelow = window.innerHeight - rect.bottom
    const above = spaceBelow < tooltipRect.height + gap + 20

    let top: number
    if (above) {
      top = rect.top + window.scrollY - tooltipRect.height - gap
    } else {
      top = rect.bottom + window.scrollY + gap
    }

    // Horizontal: center on target, clamp to viewport
    const targetCenterX = rect.left + rect.width / 2
    let left = targetCenterX - tooltipRect.width / 2
    const padding = 12
    left = Math.max(padding, Math.min(left, window.innerWidth - tooltipRect.width - padding))

    // Arrow position relative to tooltip
    const arrowLeft = Math.max(16, Math.min(targetCenterX - left, tooltipRect.width - 16))

    setPosition({ top, left, arrowLeft, above })
  }, [targetSelector])

  // Initial position + fade in
  useEffect(() => {
    rafRef.current = requestAnimationFrame(() => {
      calculatePosition()
      requestAnimationFrame(() => setVisible(true))
    })
    return () => cancelAnimationFrame(rafRef.current)
  }, [calculatePosition])

  // Recalculate on scroll/resize (throttled via rAF)
  useEffect(() => {
    let ticking = false
    function onUpdate() {
      if (ticking) return
      ticking = true
      rafRef.current = requestAnimationFrame(() => {
        calculatePosition()
        ticking = false
      })
    }
    window.addEventListener('scroll', onUpdate, { passive: true })
    window.addEventListener('resize', onUpdate, { passive: true })
    return () => {
      window.removeEventListener('scroll', onUpdate)
      window.removeEventListener('resize', onUpdate)
      cancelAnimationFrame(rafRef.current)
    }
  }, [calculatePosition])

  return (
    <div
      ref={tooltipRef}
      role="tooltip"
      aria-live="polite"
      className="fixed z-[100] max-w-xs transition-all duration-200 ease-out"
      style={{
        top: position ? `${position.top}px` : '-9999px',
        left: position ? `${position.left}px` : '0',
        opacity: visible && position ? 1 : 0,
        transform: visible && position
          ? 'translateY(0)'
          : position?.above ? 'translateY(8px)' : 'translateY(-8px)',
        pointerEvents: visible ? 'auto' : 'none',
      }}
    >
      <div className="relative rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] shadow-lg px-4 py-3">
        {/* Arrow */}
        <div
          className="absolute w-2.5 h-2.5 border border-[var(--border)] bg-[var(--surface-elevated)] rotate-45"
          style={{
            left: `${position?.arrowLeft ?? 24}px`,
            ...(position?.above
              ? { bottom: '-6px', borderTop: 'none', borderLeft: 'none' }
              : { top: '-6px', borderBottom: 'none', borderRight: 'none' }),
          }}
        />

        <p className="text-sm text-[var(--text-secondary)] leading-relaxed pr-6">
          {message}
        </p>

        <button
          onClick={onDismiss}
          className="absolute top-2 right-2 w-6 h-6 flex items-center justify-center rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--surface)] transition-colors focus-ring text-xs"
          aria-label="Dismiss hint"
        >
          &times;
        </button>
      </div>
    </div>
  )
}
