interface Props {
  priceData: Record<string, unknown>
}

function fmt(val: unknown, prefix = '', suffix = ''): string {
  if (val === undefined || val === null || val === '') return '—'
  if (typeof val === 'number') {
    return `${prefix}${val.toLocaleString(undefined, { maximumFractionDigits: 2 })}${suffix}`
  }
  return `${prefix}${String(val)}${suffix}`
}

export default function PriceMetrics({ priceData }: Props) {
  const metrics = [
    { label: 'Current Price', value: fmt(priceData.current_price, '$') },
    { label: 'P/E Ratio', value: fmt(priceData.pe_ratio) },
    { label: 'Market Cap', value: fmt(priceData.market_cap, '$') },
    { label: '52W High', value: fmt(priceData.fifty_two_week_high, '$') },
    { label: '52W Low', value: fmt(priceData.fifty_two_week_low, '$') },
    { label: 'Volume', value: fmt(priceData.volume) },
    { label: 'Beta', value: fmt(priceData.beta) },
    { label: 'Dividend Yield', value: fmt(priceData.dividend_yield, '', '%') },
  ]

  return (
    <div>
      <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">📊 Valuation Metrics</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {metrics.map((m) => (
          <div key={m.label} className="bg-[var(--surface)] rounded-lg p-3">
            <p className="text-xs text-[var(--text-muted)] mb-0.5">{m.label}</p>
            <p className="text-sm font-semibold text-[var(--text-primary)] font-mono">{m.value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
