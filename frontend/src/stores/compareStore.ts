import { create } from 'zustand'

const MIN_SLOTS = 2
const MAX_SLOTS = 4
const DEFAULT_TICKERS: string[] = ['', '']

interface CompareStore {
  tickers: string[]
  setTickers: (tickers: string[]) => void
  setTicker: (index: number, value: string) => void
  addSlot: () => void
  removeSlot: (index: number) => void
  reset: () => void
}

export const useCompareStore = create<CompareStore>((set) => ({
  tickers: [...DEFAULT_TICKERS],

  setTickers: (tickers) => {
    // Enforce the 2-3 slot invariant: pad if too short, truncate if too long
    let normalized = tickers.slice(0, MAX_SLOTS)
    while (normalized.length < MIN_SLOTS) {
      normalized.push('')
    }
    set({ tickers: normalized })
  },

  setTicker: (index, value) =>
    set((state) => {
      if (index < 0 || index >= state.tickers.length) return state
      const updated = [...state.tickers]
      updated[index] = value
      return { tickers: updated }
    }),

  addSlot: () =>
    set((state) => {
      if (state.tickers.length >= MAX_SLOTS) return state
      return { tickers: [...state.tickers, ''] }
    }),

  removeSlot: (index) =>
    set((state) => {
      if (state.tickers.length <= MIN_SLOTS) return state
      if (index < 0 || index >= state.tickers.length) return state
      return { tickers: state.tickers.filter((_, i) => i !== index) }
    }),

  reset: () => set({ tickers: [...DEFAULT_TICKERS] }),
}))
