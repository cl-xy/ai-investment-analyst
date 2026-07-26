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

function getInitialTheme(): ThemeId {
  if (typeof window === 'undefined') return 'petroleum'
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored && themes.some(t => t.id === stored)) return stored as ThemeId
  return 'petroleum'
}

function applyTheme(id: ThemeId): void {
  document.documentElement.setAttribute('data-theme', id)
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
      applyTheme(id)
      localStorage.setItem(STORAGE_KEY, id)
      set({ theme: id })
    },
  }
})
