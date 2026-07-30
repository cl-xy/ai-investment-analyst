import { create } from 'zustand'

interface SaveStatusState {
  status: 'idle' | 'saving' | 'saved' | 'failed' | 'offline'
  lastSavedAt: number | null
  error: string | null
  setSaving: () => void
  setSaved: () => void
  setFailed: (error: string) => void
  setOffline: () => void
  setIdle: () => void
}

export const useSaveStatusStore = create<SaveStatusState>((set) => ({
  status: 'idle',
  lastSavedAt: null,
  error: null,
  setSaving: () => set({ status: 'saving', error: null }),
  setSaved: () => set({ status: 'saved', lastSavedAt: Date.now(), error: null }),
  setFailed: (error: string) => set({ status: 'failed', error }),
  setOffline: () => set({ status: 'offline', error: null }),
  setIdle: () => set({ status: 'idle', error: null }),
}))
