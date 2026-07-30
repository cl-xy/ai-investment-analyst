import { create } from 'zustand'

interface CompareStore {
  tickers: string[]
  setTickers: (tickers: string[]) => void
  setTicker: (index: number, value: string) => void
  addSlot: () => void
  removeSlot: (index: number) => void
  reset: () => void
}

export const useCompareStore = create<CompareStore>((set) => ({
  tickers: ['', ''],

  setTickers: (tickers) => set({ tickers }),

  setTicker: (index, value) =>
    set((state) => {
      const updated = [...state.tickers]
      updated[index] = value
      return { tickers: updated }
    }),

  addSlot: () =>
    set((state) => {
      if (state.tickers.length >= 3) return state
      return { tickers: [...state.tickers, ''] }
    }),

  removeSlot: (index) =>
    set((state) => {
      if (state.tickers.length <= 2) return state
      return { tickers: state.tickers.filter((_, i) => i !== index) }
    }),

  reset: () => set({ tickers: ['', ''] }),
}))
