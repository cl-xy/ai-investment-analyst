import { lazy, type ComponentType } from 'react'

/**
 * Lazy import with chunk-hash recovery after deploys.
 * If a chunk fails to load (stale hash after deploy), reloads the page once.
 * Uses a per-component key to avoid cross-component interference.
 */
export function lazyRetry<T extends ComponentType<any>>(
  factory: () => Promise<{ default: T }>,
  key: string,
) {
  const storageKey = `lazyRetry:${key}`

  return lazy(async () => {
    try {
      const module = await factory()
      // Clear retry flag on success so recovery re-arms for future deploys
      safeStorageRemove(storageKey)
      return module
    } catch (error) {
      if (!isStaleChunkError(error)) {
        throw error
      }

      const reloaded = safeStorageGet(storageKey)
      if (!reloaded) {
        safeStorageSet(storageKey, '1')
        window.location.reload()
        // Satisfy types while reloading
        return new Promise<{ default: T }>(() => {})
      }
      safeStorageRemove(storageKey)
      throw error
    }
  })
}

/** Detect Vite stale-chunk dynamic import errors */
function isStaleChunkError(error: unknown): boolean {
  if (!(error instanceof Error)) return false
  const msg = error.message.toLowerCase()
  return (
    msg.includes('failed to fetch dynamically imported module') ||
    msg.includes('error loading dynamically imported module')
  )
}

/** Safe sessionStorage wrappers (handles privacy modes, sandboxed iframes) */
function safeStorageGet(key: string): string | null {
  try {
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}

function safeStorageSet(key: string, value: string): void {
  try {
    sessionStorage.setItem(key, value)
  } catch {
    // Storage unavailable, reload guard won't persist but that's acceptable
  }
}

function safeStorageRemove(key: string): void {
  try {
    sessionStorage.removeItem(key)
  } catch {
    // Storage unavailable, no-op
  }
}
