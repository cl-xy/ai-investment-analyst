export const API_BASE = import.meta.env.VITE_API_URL || ''
export const DEMO_PASSWORD = import.meta.env.VITE_DEMO_PASSWORD || ''

export function authHeaders(): Record<string, string> {
  if (!DEMO_PASSWORD) return {}
  return { 'X-Demo-Password': DEMO_PASSWORD }
}

export function authParam(): string {
  if (!DEMO_PASSWORD) return ''
  return `password=${encodeURIComponent(DEMO_PASSWORD)}`
}
