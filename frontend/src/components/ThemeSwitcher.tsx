import { Palette } from 'lucide-react'
import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react'
import { themes, useThemeStore } from '../stores/themeStore'

export function ThemeSwitcher() {
  const { theme, setTheme } = useThemeStore()
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(() => themes.findIndex((t) => t.id === theme))
  const ref = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Focus active option when opening
  useEffect(() => {
    if (open && listRef.current) {
      const active = listRef.current.querySelector('[aria-selected="true"]') as HTMLElement
      active?.focus()
    }
  }, [open])

  const handleTriggerKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      setOpen(true)
    }
  }

  const handleListKeyDown = useCallback((e: KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault()
        setActiveIndex((i) => (i + 1) % themes.length)
        break
      case 'ArrowUp':
        e.preventDefault()
        setActiveIndex((i) => (i - 1 + themes.length) % themes.length)
        break
      case 'Enter':
      case ' ':
        e.preventDefault()
        setTheme(themes[activeIndex].id)
        setOpen(false)
        break
      case 'Escape':
        e.preventDefault()
        setOpen(false)
        break
      case 'Home':
        e.preventDefault()
        setActiveIndex(0)
        break
      case 'End':
        e.preventDefault()
        setActiveIndex(themes.length - 1)
        break
    }
  }, [activeIndex, setTheme])

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        onKeyDown={handleTriggerKeyDown}
        className="min-w-[44px] min-h-[44px] flex items-center justify-center rounded-lg hover:bg-[var(--surface-elevated)] transition-colors focus-ring"
        aria-label="Change theme"
        aria-expanded={open}
        aria-haspopup="listbox"
      >
        <Palette size={18} className="text-[var(--text-secondary)]" />
      </button>

      {open && (
        <div
          ref={listRef}
          className="absolute right-0 top-full mt-2 w-48 rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] shadow-lg py-1 z-50 animate-fade-in"
          role="listbox"
          aria-label="Theme selection"
          aria-activedescendant={`theme-${themes[activeIndex].id}`}
          onKeyDown={handleListKeyDown}
        >
          {themes.map((t, i) => (
            <button
              key={t.id}
              id={`theme-${t.id}`}
              role="option"
              aria-selected={theme === t.id}
              tabIndex={i === activeIndex ? 0 : -1}
              onClick={() => { setTheme(t.id); setOpen(false) }}
              onFocus={() => setActiveIndex(i)}
              className={`w-full text-left px-3 py-2.5 text-sm transition-colors min-h-[44px] ${
                i === activeIndex ? 'bg-[var(--surface)]' : ''
              } ${theme === t.id ? 'text-[var(--accent)]' : 'text-[var(--text-primary)]'}`}
            >
              <span className="font-medium">{t.name}</span>
              <span className="block text-xs text-[var(--text-muted)]">{t.description}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
