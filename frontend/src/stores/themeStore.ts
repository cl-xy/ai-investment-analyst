import { create } from 'zustand'

export type ThemeId = 'petroleum' | 'plum' | 'moss' | 'graphite'

export interface ThemeMeta {
  id: ThemeId
  name: string
  description: string
}

export const themes: ThemeMeta[] = [
  { id: 'petroleum', name: 'Petroleum', description: 'Deep teal, amber accent' },
  { id: 'plum', name: 'Plum', description: 'Rich plum, gold accent' },
  { id: 'moss', name: 'Moss', description: 'Forest green, saffron accent' },
  { id: 'graphite', name: 'Graphite', description: 'Warm charcoal, oxide accent' },
]

const STORAGE_KEY = 'invest-theme'

function safeGetItem(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function safeSetItem(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Storage unavailable (disabled, quota exceeded, sandboxed iframe)
  }
}

function isValidTheme(value: string | null): value is ThemeId {
  return value !== null && themes.some(t => t.id === value)
}

function getInitialTheme(): ThemeId {
  if (typeof window === 'undefined') return 'petroleum'
  const stored = safeGetItem(STORAGE_KEY)
  if (isValidTheme(stored)) return stored
  return 'petroleum'
}

let transitionTimeout: ReturnType<typeof setTimeout> | null = null

function applyTheme(id: ThemeId, animate = false): void {
  if (typeof document === 'undefined') return
  const el = document.documentElement

  if (transitionTimeout !== null) {
    clearTimeout(transitionTimeout)
    transitionTimeout = null
    el.removeAttribute('data-theme-transitioning')
  }

  if (animate && typeof window !== 'undefined'
    && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === false) {
    el.setAttribute('data-theme-transitioning', '')
    el.setAttribute('data-theme', id)
    // Remove after transition completes (320ms = --motion-surface)
    transitionTimeout = setTimeout(() => {
      el.removeAttribute('data-theme-transitioning')
      transitionTimeout = null
    }, 350)
  } else {
    el.setAttribute('data-theme', id)
  }
}

interface ThemeStore {
  theme: ThemeId
  setTheme: (id: ThemeId) => void
}

export const useThemeStore = create<ThemeStore>((set) => {
  const initial = getInitialTheme()
  // Apply on store creation
  if (typeof window !== 'undefined') applyTheme(initial)

  return {
    theme: initial,
    setTheme: (id) => {
      if (!isValidTheme(id)) return
      applyTheme(id, true)
      safeSetItem(STORAGE_KEY, id)
      set({ theme: id })
    },
  }
})
