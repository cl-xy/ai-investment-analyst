import { useState, useEffect, useCallback } from 'react'

const isMac = typeof navigator !== 'undefined'
  ? /Mac|iPhone|iPad|iPod/.test(
      (navigator as { userAgentData?: { platform?: string } }).userAgentData?.platform
        ?? navigator.platform
    )
  : false

export { isMac }

function isEditableTarget(target: EventTarget | null): boolean {
  if (!target || !(target instanceof HTMLElement)) return false
  const tag = target.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (target.isContentEditable) return true
  return false
}

export function useKeyboardShortcuts() {
  const [helpOpen, setHelpOpen] = useState(false)

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (isEditableTarget(e.target)) return

    const mod = isMac ? e.metaKey : e.ctrlKey

    // Cmd+Shift+? (which is Cmd+Shift+/ on most keyboards)
    if (mod && e.shiftKey && (e.key === '?' || e.key === '/')) {
      e.preventDefault()
      setHelpOpen((prev) => !prev)
      return
    }

    // Cmd+K: dispatch custom event for command palette
    if (mod && !e.shiftKey && e.key === 'k') {
      e.preventDefault()
      window.dispatchEvent(new CustomEvent('open-command-palette'))
      return
    }
  }, [])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  return { helpOpen, setHelpOpen }
}
