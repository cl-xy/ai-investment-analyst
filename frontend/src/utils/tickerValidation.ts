const TICKER_REGEX = /^[A-Z][A-Z0-9.]{0,9}$/

export function isValidTicker(input: string): boolean {
  return TICKER_REGEX.test(input.toUpperCase())
}

export function normalizeTicker(input: string): string {
  return input.trim().toUpperCase().replace(/[^A-Z0-9.]/g, '')
}

export function getTickerError(input: string): string | null {
  const trimmed = input.trim()
  if (!trimmed) return null
  if (trimmed.length > 10) return 'Ticker must be 10 characters or fewer'
  if (!/^[A-Za-z]/.test(trimmed)) return 'Ticker must start with a letter'
  if (!/^[A-Za-z0-9.]+$/.test(trimmed)) return 'Only letters, numbers, and dots allowed'
  return null
}
