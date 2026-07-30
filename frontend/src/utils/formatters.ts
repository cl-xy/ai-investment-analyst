export function formatPrice(price: number | null | undefined): string {
  if (price == null || !Number.isFinite(price)) return '-'
  return `$${price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function formatVolume(volume: number | null | undefined): string {
  if (volume == null || !Number.isFinite(volume)) return '-'

  const sign = volume < 0 ? '-' : ''
  const abs = Math.abs(volume)

  if (abs >= 999_950_000_000) return `${sign}${(abs / 1_000_000_000_000).toFixed(1)}T`
  if (abs >= 999_950_000) return `${sign}${(abs / 1_000_000_000).toFixed(1)}B`
  if (abs >= 999_950) return `${sign}${(abs / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000) return `${sign}${(abs / 1_000).toFixed(0)}K`
  return `${sign}${Math.round(abs).toLocaleString('en-US')}`
}
