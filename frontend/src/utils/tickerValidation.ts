const TICKER_REGEX = /^[A-Z0-9][A-Z0-9.]{0,9}$/

export function isValidTicker(input: string): boolean {
  const trimmed = input.trim()
  // Reject if raw input contains non-ASCII (prevents Unicode case-mapping bypass like ß -> SS)
  if (/[^\x00-\x7F]/.test(trimmed)) return false
  return TICKER_REGEX.test(trimmed.toUpperCase())
}

export function normalizeTicker(input: string): string {
  const stripped = input.trim().toUpperCase().replace(/[^A-Z0-9.]/g, '')
  // Remove leading dots
  const cleaned = stripped.replace(/^\.+/, '')
  return cleaned
}

export function getTickerError(input: string): string | null {
  const trimmed = input.trim()
  if (!trimmed) return null
  if (/[^\x00-\x7F]/.test(trimmed)) return 'Only ASCII letters, numbers, and dots allowed'
  if (trimmed.length > 10) return 'Ticker must be 10 characters or fewer'
  if (!/^[A-Za-z0-9]/.test(trimmed)) return 'Ticker must start with a letter or number'
  if (!/^[A-Za-z0-9.]+$/.test(trimmed)) return 'Only letters, numbers, and dots allowed'
  return null
}
