import { create } from 'zustand'

export type ToastTier = 1 | 2 | 3
export type ToastType = 'info' | 'success' | 'error' | 'warning'

export interface Toast {
  id: string
  type: ToastType
  message: string
  tier: ToastTier
  action?: { label: string; onClick: () => void }
}

const TIER_DURATIONS: Record<ToastTier, number | null> = {
  1: 1500,  // brief flash, no action
  2: 5000,  // standard with optional undo
  3: null,  // persistent, user must dismiss
}

interface ToastStore {
  toasts: Toast[]
  addToast: (toast: Omit<Toast, 'id'>) => string
  removeToast: (id: string) => void
  clearAll: () => void
}

let counter = 0

const MAX_VISIBLE = 3

export const useToastStore = create<ToastStore>((set, get) => ({
  toasts: [],

  addToast: (toast) => {
    const id = `toast-${++counter}-${Date.now()}`
    const newToast: Toast = { ...toast, id }

    // Coalesce duplicate messages (same message + type within the visible stack)
    const existing = get().toasts.find((t) => t.message === toast.message && t.type === toast.type)
    if (existing) return existing.id

    set((state) => {
      const updated = [...state.toasts, newToast]
      // Evict oldest non-persistent toasts when exceeding max visible
      if (updated.length > MAX_VISIBLE) {
        const evictable = updated.findIndex((t) => t.tier !== 3)
        if (evictable >= 0) updated.splice(evictable, 1)
      }
      return { toasts: updated }
    })

    const duration = TIER_DURATIONS[toast.tier]
    if (duration !== null) {
      setTimeout(() => get().removeToast(id), duration)
    }
    return id
  },

  removeToast: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

  clearAll: () => set({ toasts: [] }),
}))

export function toast(message: string, type: ToastType = 'info', tier: ToastTier = 1) {
  return useToastStore.getState().addToast({ message, type, tier })
}

export function toastSuccess(message: string) {
  return useToastStore.getState().addToast({ message, type: 'success', tier: 1 })
}

export function toastError(message: string, persistent = false) {
  return useToastStore.getState().addToast({
    message,
    type: 'error',
    tier: persistent ? 3 : 2,
  })
}

export function toastUndo(message: string, onUndo: () => void) {
  return useToastStore.getState().addToast({
    message,
    type: 'info',
    tier: 2,
    action: { label: 'Undo', onClick: onUndo },
  })
}
