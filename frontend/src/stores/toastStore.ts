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

const timers = new Map<string, ReturnType<typeof setTimeout>>()

const MAX_VISIBLE = 3

function scheduleRemoval(id: string, duration: number, removeFn: (id: string) => void) {
  clearTimer(id)
  timers.set(id, setTimeout(() => {
    timers.delete(id)
    removeFn(id)
  }, duration))
}

function clearTimer(id: string) {
  const handle = timers.get(id)
  if (handle !== undefined) {
    clearTimeout(handle)
    timers.delete(id)
  }
}

function clearAllTimers() {
  timers.forEach((handle) => clearTimeout(handle))
  timers.clear()
}

export const useToastStore = create<ToastStore>((set, get) => ({
  toasts: [],

  addToast: (toast) => {
    const id = `toast-${crypto.randomUUID()}`
    const newToast: Toast = { ...toast, id }

    // Coalesce: same message + type + tier + has-action must all match
    const hasAction = toast.action != null
    let coalescedId: string | null = null

    set((state) => {
      const existing = state.toasts.find(
        (t) =>
          t.message === toast.message &&
          t.type === toast.type &&
          t.tier === toast.tier &&
          (t.action != null) === hasAction
      )

      if (existing) {
        coalescedId = existing.id
        return state // no change
      }

      const updated = [...state.toasts, newToast]
      // Evict oldest non-persistent toast when exceeding max visible,
      // but never evict the toast we just added
      if (updated.length > MAX_VISIBLE) {
        const evictable = updated.findIndex(
          (t) => t.tier !== 3 && t.id !== id
        )
        if (evictable >= 0) {
          clearTimer(updated[evictable].id)
          updated.splice(evictable, 1)
        }
      }
      return { toasts: updated }
    })

    if (coalescedId) {
      // Reset timer on the coalesced toast so it stays visible for a full duration
      const duration = TIER_DURATIONS[toast.tier]
      if (duration !== null) {
        scheduleRemoval(coalescedId, duration, (cid) => get().removeToast(cid))
      }
      return coalescedId
    }

    const duration = TIER_DURATIONS[toast.tier]
    if (duration !== null) {
      scheduleRemoval(id, duration, (tid) => get().removeToast(tid))
    }
    return id
  },

  removeToast: (id) => {
    clearTimer(id)
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }))
  },

  clearAll: () => {
    clearAllTimers()
    set({ toasts: [] })
  },
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
