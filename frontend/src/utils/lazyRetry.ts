import { lazy, type ComponentType } from 'react'

/**
 * Lazy import with chunk-hash recovery after deploys.
 * If a chunk fails to load (stale hash after deploy), reloads the page once.
 */
export function lazyRetry<T extends ComponentType<any>>(
  factory: () => Promise<{ default: T }>,
) {
  return lazy(async () => {
    try {
      return await factory()
    } catch (error) {
      const reloaded = sessionStorage.getItem('chunk_reload')
      if (!reloaded) {
        sessionStorage.setItem('chunk_reload', '1')
        window.location.reload()
        // Satisfy types while reloading
        return new Promise<{ default: T }>(() => {})
      }
      sessionStorage.removeItem('chunk_reload')
      throw error
    }
  })
}
