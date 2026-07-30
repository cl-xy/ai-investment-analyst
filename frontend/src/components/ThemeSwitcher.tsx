import { Palette } from 'lucide-react'
import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react'
import { themes, useThemeStore } from '../stores/themeStore'

function getSafeIndex(themeId: string): number {
  const idx = themes.findIndex((t) => t.id === themeId)
  return idx >= 0 ? idx : 0
}

export function ThemeSwitcher() {
  const { theme, setTheme } = useThemeStore()
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(() => getSafeIndex(theme))
  const ref = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)

  const closeDropdown = useCallback((restoreFocus = true) => {
    setOpen(false)
    if (restoreFocus) {
      requestAnimationFrame(() => triggerRef.current?.focus())
    }
  }, [])

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        closeDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [closeDropdown])

  // Resync activeIndex and focus the active option when opening
  useEffect(() => {
    if (open && listRef.current) {
      const safeIndex = getSafeIndex(theme)
      setActiveIndex(safeIndex)
      requestAnimationFrame(() => {
        const options = listRef.current?.querySelectorAll<HTMLElement>('[role="option"]')
        options?.[safeIndex]?.focus()
      })
    }
  }, [open, theme])

  const handleTriggerKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      setOpen(true)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setOpen(true)
      setActiveIndex(themes.length > 0 ? themes.length - 1 : 0)
    }
  }

  const handleListKeyDown = useCallback((e: KeyboardEvent) => {
    if (themes.length === 0) return

    const focusOption = (index: number) => {
      requestAnimationFrame(() => {
        const options = listRef.current?.querySelectorAll<HTMLElement>('[role="option"]')
        options?.[index]?.focus()
      })
    }

    switch (e.key) {
      case 'ArrowDown': {
        e.preventDefault()
        const next = (activeIndex + 1) % themes.length
        setActiveIndex(next)
        focusOption(next)
        break
      }
      case 'ArrowUp': {
        e.preventDefault()
        const prev = (activeIndex - 1 + themes.length) % themes.length
        setActiveIndex(prev)
        focusOption(prev)
        break
      }
      case 'Enter':
      case ' ':
        e.preventDefault()
        if (themes[activeIndex]) {
          setTheme(themes[activeIndex].id)
        }
        closeDropdown(true)
        break
      case 'Escape':
        e.preventDefault()
        closeDropdown(true)
        break
      case 'Home': {
        e.preventDefault()
        setActiveIndex(0)
        focusOption(0)
        break
      }
      case 'End': {
        e.preventDefault()
        const last = themes.length - 1
        setActiveIndex(last)
        focusOption(last)
        break
      }
      case 'Tab':
        closeDropdown(false)
        break
    }
  }, [activeIndex, setTheme, closeDropdown])

  return (
    <div ref={ref} className="relative" data-tour-target="theme-switcher">
      <button
        ref={triggerRef}
        type="button"
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
          onKeyDown={handleListKeyDown}
        >
          {themes.map((t, i) => (
            <div
              key={t.id}
              role="option"
              aria-selected={theme === t.id}
              tabIndex={i === activeIndex ? 0 : -1}
              onClick={() => { setTheme(t.id); closeDropdown(true) }}
              onFocus={() => setActiveIndex(i)}
              className={`w-full text-left px-3 py-2.5 text-sm transition-colors min-h-[44px] cursor-pointer ${
                i === activeIndex ? 'bg-[var(--surface)]' : ''
              } ${theme === t.id ? 'text-[var(--accent)]' : 'text-[var(--text-primary)]'}`}
            >
              <span className="font-medium">{t.name}</span>
              <span className="block text-xs text-[var(--text-muted)]">{t.description}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
