interface Props {
  fundamentals: Record<string, unknown>
}

function fmtNum(val: unknown, decimals = 2, suffix = ''): string {
  if (val === undefined || val === null || val === '') return '—'
  if (typeof val === 'number') {
    return `${val.toLocaleString(undefined, { maximumFractionDigits: decimals })}${suffix}`
  }
  return String(val)
}

export default function MarketPositionSection({ fundamentals }: Props) {
  const items = [
    { label: 'Revenue (TTM)', value: fmtNum(fundamentals.revenue, 0) },
    { label: 'Net Income', value: fmtNum(fundamentals.net_income, 0) },
    { label: 'Gross Margin', value: fmtNum(fundamentals.gross_margin, 1, '%') },
    { label: 'Operating Margin', value: fmtNum(fundamentals.operating_margin, 1, '%') },
    { label: 'Return on Equity', value: fmtNum(fundamentals.roe, 1, '%') },
    { label: 'Debt to Equity', value: fmtNum(fundamentals.debt_to_equity) },
    { label: 'EPS (TTM)', value: fmtNum(fundamentals.eps) },
    { label: 'Sector', value: String(fundamentals.sector ?? '—') },
  ]

  const description = typeof fundamentals.description === 'string' ? fundamentals.description : ''

  return (
    <div>
      <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">🏆 Market Position & Fundamentals</h3>
      {description && (
        <p className="text-sm text-[var(--text-secondary)] leading-relaxed mb-3">{description}</p>
      )}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {items.map((item) => (
          <div key={item.label} className="bg-[var(--surface)] rounded-lg p-3">
            <p className="text-xs text-[var(--text-muted)] mb-0.5">{item.label}</p>
            <p className="text-sm font-semibold text-[var(--text-primary)] font-mono">{item.value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
