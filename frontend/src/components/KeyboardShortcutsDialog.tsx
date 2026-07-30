import { useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Keyboard, X } from 'lucide-react'
import { useFocusTrap } from '../hooks/useFocusTrap'
import { isMac } from '../hooks/useKeyboardShortcuts'

interface Props {
  open: boolean
  onClose: () => void
}

const MOD_KEY = isMac ? '⌘' : 'Ctrl'

const SHORTCUTS = [
  { keys: [MOD_KEY, 'K'], action: 'Open command palette' },
  { keys: [MOD_KEY, 'Shift', '?'], action: 'Show keyboard shortcuts' },
  { keys: ['Esc'], action: 'Close dialog / palette' },
  { keys: ['/'], action: 'Focus search (on watchlist)' },
]

export default function KeyboardShortcutsDialog({ open, onClose }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null)
  useFocusTrap(dialogRef, open)

  useEffect(() => {
    if (!open) return
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        onClose()
      }
    }
    document.addEventListener('keydown', handleKey, true)
    return () => document.removeEventListener('keydown', handleKey, true)
  }, [open, onClose])

  if (!open) return null

  return createPortal(
    <div
      className="fixed inset-0 z-[150] flex items-center justify-center"
      onClick={onClose}
      aria-hidden="true"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 motion-safe:animate-fade-in" />

      {/* Dialog */}
      <div
        ref={dialogRef}
        role="dialog"
        aria-labelledby="kbd-shortcuts-title"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
        className="relative w-full max-w-md mx-4 rounded-2xl border border-[var(--border)] bg-[var(--surface-elevated)] shadow-2xl motion-safe:animate-scale-in"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-[var(--border)]">
          <div className="flex items-center gap-2.5">
            <Keyboard className="w-5 h-5 text-[var(--accent)]" />
            <h2
              id="kbd-shortcuts-title"
              className="text-base font-semibold text-[var(--text-primary)]"
            >
              Keyboard Shortcuts
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--surface)] transition-colors focus-ring"
            aria-label="Close shortcuts dialog"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Shortcuts table */}
        <div className="px-6 py-4">
          <table className="w-full">
            <thead className="sr-only">
              <tr>
                <th>Shortcut</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {SHORTCUTS.map(({ keys, action }) => (
                <tr
                  key={action}
                  className="group"
                >
                  <td className="py-2.5 pr-4 align-middle">
                    <span className="flex items-center gap-1">
                      {keys.map((key, i) => (
                        <span key={i}>
                          {i > 0 && (
                            <span className="text-[var(--text-muted)] text-xs mx-0.5">+</span>
                          )}
                          <kbd className="inline-flex items-center justify-center min-w-[24px] px-1.5 py-0.5 text-xs font-mono font-medium rounded-md border border-[var(--border)] bg-[var(--surface)] text-[var(--text-secondary)] shadow-sm">
                            {key}
                          </kbd>
                        </span>
                      ))}
                    </span>
                  </td>
                  <td className="py-2.5 text-sm text-[var(--text-secondary)] align-middle">
                    {action}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Footer hint */}
        <div className="px-6 pb-5 pt-1">
          <p className="text-xs text-[var(--text-muted)]">
            Press <kbd className="px-1 py-0.5 text-[10px] font-mono rounded border border-[var(--border)] bg-[var(--surface)]">Esc</kbd> to close
          </p>
        </div>
      </div>
    </div>,
    document.body
  )
}
