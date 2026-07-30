import { useEffect, useRef, type RefObject } from 'react'

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[contenteditable]:not([contenteditable="false"])',
  'audio[controls]',
  'video[controls]',
  'summary',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

/** Check if an element is actually visible and focusable at runtime */
function isVisibleAndFocusable(el: HTMLElement): boolean {
  if (el.closest('[inert]')) return false
  // offsetParent is null for hidden elements, but also for position:fixed;
  // use getClientRects as a fallback for fixed-position elements
  if (el.offsetParent === null && el.getClientRects().length === 0) return false
  const style = getComputedStyle(el)
  if (style.visibility === 'hidden' || style.display === 'none') return false
  return true
}

/** Get all actually-focusable elements within a container */
function getFocusableElements(container: HTMLElement): HTMLElement[] {
  const candidates = container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
  return Array.from(candidates).filter(isVisibleAndFocusable)
}

/**
 * Traps focus within a container element when active.
 * Restores focus to the previously focused element on deactivation.
 */
export function useFocusTrap(containerRef: RefObject<HTMLElement | null>, active: boolean) {
  const previousFocusRef = useRef<HTMLElement | null>(null)
  const wasActiveRef = useRef(false)
  // Store latest containerRef to read lazily inside event handlers,
  // avoiding effect re-runs from unstable ref identity
  const containerRefLatest = useRef<RefObject<HTMLElement | null>>(containerRef)
  containerRefLatest.current = containerRef

  useEffect(() => {
    if (!active) {
      // Deactivation path: restore focus if we were previously active
      if (wasActiveRef.current) {
        wasActiveRef.current = false
        const prev = previousFocusRef.current
        if (prev && prev.isConnected && !prev.hasAttribute('disabled') && !prev.closest('[inert]')) {
          try {
            prev.focus({ preventScroll: true })
          } catch {
            // Silently fail if focus() throws (e.g., detached node edge cases)
          }
        }
        previousFocusRef.current = null
      }
      return
    }

    const container = containerRefLatest.current.current
    if (!container) {
      // Container not yet mounted; retry once on next frame
      const frameId = requestAnimationFrame(() => {
        const c = containerRefLatest.current.current
        if (c && active) {
          activateTrap(c)
        }
      })
      return () => cancelAnimationFrame(frameId)
    }

    activateTrap(container)

    function activateTrap(container: HTMLElement) {
      // Only capture previous focus on fresh activation (not re-runs)
      if (!wasActiveRef.current) {
        wasActiveRef.current = true
        const activeEl = document.activeElement
        if (activeEl instanceof HTMLElement && !container.contains(activeEl)) {
          previousFocusRef.current = activeEl
        }
      }

      // Focus first focusable element in container
      const focusables = getFocusableElements(container)
      if (focusables.length > 0) {
        focusables[0].focus()
      } else {
        // Fallback: focus the container itself
        if (!container.hasAttribute('tabindex')) {
          container.setAttribute('tabindex', '-1')
          container.dataset.focusTrapTabindex = 'true'
        }
        container.focus()
      }
    }

    // Use capture phase so child stopPropagation cannot defeat the trap
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return
      const container = containerRefLatest.current.current
      if (!container) return

      const focusables = getFocusableElements(container)
      if (focusables.length === 0) {
        e.preventDefault()
        return
      }

      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      const activeEl = document.activeElement

      // If focus is outside container, redirect into it
      if (!container.contains(activeEl as Node)) {
        e.preventDefault()
        first.focus()
        return
      }

      if (e.shiftKey) {
        if (activeEl === first) {
          e.preventDefault()
          last.focus()
        }
      } else {
        if (activeEl === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }

    // Recapture focus when it escapes via click or programmatic focus
    const handleFocusIn = (e: FocusEvent) => {
      const container = containerRefLatest.current.current
      if (!container) return
      const target = e.target as Node | null
      if (target && !container.contains(target)) {
        const focusables = getFocusableElements(container)
        if (focusables.length > 0) {
          focusables[0].focus()
        } else {
          container.focus()
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown, true)
    document.addEventListener('focusin', handleFocusIn, true)

    return () => {
      document.removeEventListener('keydown', handleKeyDown, true)
      document.removeEventListener('focusin', handleFocusIn, true)

      // Clean up temporary tabindex if we added it
      const container = containerRefLatest.current.current
      if (container?.dataset.focusTrapTabindex) {
        container.removeAttribute('tabindex')
        delete container.dataset.focusTrapTabindex
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active])
}
