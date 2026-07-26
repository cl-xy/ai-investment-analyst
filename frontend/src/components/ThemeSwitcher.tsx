import { Palette } from 'lucide-react'
import { useState, useRef, useEffect } from 'react'
import { themes, useThemeStore } from '../stores/themeStore'

export function ThemeSwitcher() {
  const { theme, setTheme } = useThemeStore()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="p-2 rounded-lg hover:bg-[var(--surface-elevated)] transition-colors duration-150 focus-ring"
        aria-label="Change theme"
        aria-expanded={open}
      >
        <Palette size={18} className="text-[var(--text-secondary)]" />
      </button>

      {open && (
        <div
          className="absolute right-0 top-full mt-2 w-48 rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] shadow-lg py-1 z-50 animate-fade-in"
          role="listbox"
          aria-label="Theme selection"
        >
          {themes.map((t) => (
            <button
              key={t.id}
              role="option"
              aria-selected={theme === t.id}
              onClick={() => { setTheme(t.id); setOpen(false) }}
              className={`w-full text-left px-3 py-2 text-sm transition-colors duration-100 hover:bg-[var(--surface)] ${
                theme === t.id ? 'text-[var(--accent)]' : 'text-[var(--text-primary)]'
              }`}
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
