import { useRef, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import {
  TrendingUp,
  Compass,
  GitCompare,
  MessageSquare,
  LayoutDashboard,
  Target,
  BarChart3,
  Award,
  Activity,
  PlayCircle,
  Search,
  Map,
} from 'lucide-react'
import { useCommandPalette, type CommandItem } from '../hooks/useCommandPalette'
import { useFocusTrap } from '../hooks/useFocusTrap'

const COMMANDS: CommandItem[] = [
  { id: 'analyze', label: 'Analyze', path: '/', keywords: ['home', 'watchlist', 'ticker'] },
  { id: 'explore', label: 'Explore', path: '/explore', keywords: ['search', 'discover', 'browse'] },
  { id: 'compare', label: 'Compare', path: '/compare', keywords: ['versus', 'diff', 'side by side'] },
  { id: 'chat', label: 'Chat', path: '/chat', keywords: ['ask', 'question', 'conversation'] },
  { id: 'dashboard', label: 'Past Analyses', path: '/dashboard', keywords: ['history', 'previous', 'results'] },
  { id: 'calibration', label: 'Track Record', path: '/calibration', keywords: ['accuracy', 'performance', 'predictions'] },
  { id: 'backtest', label: 'Signal History', path: '/backtest', keywords: ['signals', 'past', 'trades'] },
  { id: 'evals', label: 'Quality Metrics', path: '/evals', keywords: ['evaluation', 'quality', 'score'] },
  { id: 'ops', label: 'Ops Dashboard', path: '/ops', keywords: ['operations', 'health', 'monitoring'] },
  { id: 'replay', label: 'Trace Replay', path: '/replay', keywords: ['trace', 'debug', 'playback'] },
  { id: 'tour', label: 'Start Tour', path: '/__tour__', keywords: ['onboarding', 'guide', 'help', 'walkthrough'] },
]

const ICONS: Record<string, typeof TrendingUp> = {
  analyze: TrendingUp,
  explore: Compass,
  compare: GitCompare,
  chat: MessageSquare,
  dashboard: LayoutDashboard,
  calibration: Target,
  backtest: BarChart3,
  evals: Award,
  ops: Activity,
  replay: PlayCircle,
  tour: Map,
}

export default function CommandPalette() {
  const navigate = useNavigate()
  const { isOpen, close, query, setQuery, results, selectedIndex, setSelectedIndex } = useCommandPalette(COMMANDS)
  const dialogRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  useFocusTrap(dialogRef, isOpen)

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      requestAnimationFrame(() => {
        inputRef.current?.focus()
      })
    }
  }, [isOpen])

  // Scroll selected item into view
  useEffect(() => {
    if (!listRef.current) return
    const activeEl = listRef.current.querySelector('[data-active="true"]')
    if (activeEl) {
      activeEl.scrollIntoView({ block: 'nearest' })
    }
  }, [selectedIndex])

  const handleSelect = useCallback((item: CommandItem) => {
    close()
    if (item.id === 'tour') {
      document.dispatchEvent(new CustomEvent('start-spotlight-tour'))
      return
    }
    navigate(item.path)
  }, [close, navigate])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setSelectedIndex((prev) => (prev + 1) % Math.max(results.length, 1))
        break
      case 'ArrowUp':
        e.preventDefault()
        setSelectedIndex((prev) => (prev - 1 + results.length) % Math.max(results.length, 1))
        break
      case 'Enter':
        e.preventDefault()
        if (results[selectedIndex]) {
          handleSelect(results[selectedIndex])
        }
        break
      case 'Escape':
        e.preventDefault()
        close()
        break
    }
  }, [results, selectedIndex, setSelectedIndex, handleSelect, close])

  const handleBackdropClick = useCallback((e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      close()
    }
  }, [close])

  if (!isOpen) return null

  return createPortal(
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[20vh]"
      onClick={handleBackdropClick}
      style={{
        backgroundColor: 'rgba(0, 0, 0, 0.5)',
        backdropFilter: 'blur(4px)',
        animation: 'command-palette-backdrop-in var(--motion-micro) var(--ease-standard) both',
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-label="Command palette"
        aria-modal="true"
        className="w-full max-w-lg mx-4 rounded-xl border border-[var(--border)] bg-[var(--surface-elevated)] shadow-2xl overflow-hidden motion-safe:animate-[command-palette-in_var(--motion-standard)_var(--ease-decelerate)_both]"
        onKeyDown={handleKeyDown}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[var(--border)]">
          <Search className="w-4 h-4 text-[var(--text-muted)] shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search pages..."
            className="flex-1 bg-transparent text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] outline-none"
            aria-label="Search pages"
            aria-activedescendant={results[selectedIndex] ? `command-item-${results[selectedIndex].id}` : undefined}
            aria-controls="command-palette-list"
            aria-autocomplete="list"
            role="combobox"
            aria-expanded="true"
          />
          <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium text-[var(--text-muted)] bg-[var(--surface)] border border-[var(--border)]">
            Esc
          </kbd>
        </div>

        {/* Results list */}
        <ul
          ref={listRef}
          id="command-palette-list"
          role="listbox"
          aria-label="Pages"
          className="max-h-[320px] overflow-y-auto py-2"
        >
          {results.length === 0 ? (
            <li className="px-4 py-8 text-center text-sm text-[var(--text-muted)]">
              No results found
            </li>
          ) : (
            results.map((item, index) => {
              const Icon = ICONS[item.id] ?? Search
              const isActive = index === selectedIndex
              return (
                <li
                  key={item.id}
                  id={`command-item-${item.id}`}
                  role="option"
                  aria-selected={isActive}
                  data-active={isActive}
                  onClick={() => handleSelect(item)}
                  onMouseEnter={() => setSelectedIndex(index)}
                  className={[
                    'flex items-center gap-3 px-4 py-2.5 cursor-pointer transition-colors',
                    isActive
                      ? 'bg-[var(--accent-bg)] text-[var(--text-primary)]'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--surface)]',
                  ].join(' ')}
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  <span className="flex-1 text-sm font-medium">{item.label}</span>
                  <span className="text-xs text-[var(--text-muted)]">{item.path}</span>
                </li>
              )
            })
          )}
        </ul>

        {/* Footer hint */}
        <div className="flex items-center gap-4 px-4 py-2 border-t border-[var(--border)] text-[10px] text-[var(--text-muted)]">
          <span className="inline-flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-[var(--surface)] border border-[var(--border)]">&uarr;&darr;</kbd>
            navigate
          </span>
          <span className="inline-flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-[var(--surface)] border border-[var(--border)]">&crarr;</kbd>
            open
          </span>
          <span className="inline-flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-[var(--surface)] border border-[var(--border)]">esc</kbd>
            close
          </span>
        </div>
      </div>
    </div>,
    document.body
  )
}
