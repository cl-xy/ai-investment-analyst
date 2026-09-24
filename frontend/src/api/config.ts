export const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/+$/, '')
export const DEMO_PASSWORD = import.meta.env.VITE_DEMO_PASSWORD || ''

if (import.meta.env.PROD && !import.meta.env.VITE_API_URL) {
  console.error('[config] VITE_API_URL is not set — API requests will fail')
}

const SESSION_TOKEN_KEY = 'session_token'

let sessionToken: string | null = null
try {
  sessionToken = sessionStorage.getItem(SESSION_TOKEN_KEY)
} catch {
  // sessionStorage unavailable (private mode, etc.) — fall back to in-memory only
}

export function setSessionToken(token: string): void {
  sessionToken = token
  try {
    sessionStorage.setItem(SESSION_TOKEN_KEY, token)
  } catch {
    // ignore storage errors
  }
}

export function clearSessionToken(): void {
  sessionToken = null
  try {
    sessionStorage.removeItem(SESSION_TOKEN_KEY)
  } catch {
    // ignore storage errors
  }
}

export function getSessionToken(): string | null {
  return sessionToken
}

export function authHeaders(): Record<string, string> {
  if (sessionToken) return { Authorization: `Bearer ${sessionToken}` }
  if (!DEMO_PASSWORD) return {}
  return { 'X-Demo-Password': DEMO_PASSWORD }
}

export function authParam(): string {
  if (!DEMO_PASSWORD) return ''
  return `password=${encodeURIComponent(DEMO_PASSWORD)}`
}
