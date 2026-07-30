export const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '')
export const DEMO_PASSWORD = import.meta.env.VITE_DEMO_PASSWORD || ''

if (import.meta.env.PROD && !import.meta.env.VITE_API_URL) {
  console.error('[config] VITE_API_URL is not set — API requests will fail')
}

export function authHeaders(): Record<string, string> {
  if (!DEMO_PASSWORD) return {}
  return { 'X-Demo-Password': DEMO_PASSWORD }
}

export function authParam(): string {
  if (!DEMO_PASSWORD) return ''
  return `password=${encodeURIComponent(DEMO_PASSWORD)}`
}
