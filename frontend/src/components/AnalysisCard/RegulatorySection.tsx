interface Props {
  riskFlags: string[]
}

export default function RegulatorySection({ riskFlags }: Props) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">⚠️ Risk Flags</h3>
      {riskFlags.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">No significant risk flags identified.</p>
      ) : (
        <ul className="space-y-1.5">
          {riskFlags.map((flag, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-[var(--bearish)]">
              <span className="mt-0.5 text-[var(--bearish)]">•</span>
              <span>{flag}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
