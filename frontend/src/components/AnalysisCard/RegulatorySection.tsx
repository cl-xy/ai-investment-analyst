import { AlertTriangle } from 'lucide-react'

interface Props {
  riskFlags: string[]
}

export default function RegulatorySection({ riskFlags = [] }: Props) {
  const validFlags = (Array.isArray(riskFlags) ? riskFlags : []).filter(
    (f): f is string => typeof f === 'string' && f.trim().length > 0
  )

  return (
    <div>
      <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2 flex items-center gap-1.5">
        <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
        Risk Flags
      </h3>
      {validFlags.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">No significant risk flags identified.</p>
      ) : (
        <ul className="space-y-1.5">
          {validFlags.map((flag, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-[var(--bearish)]">
              <span className="mt-0.5 text-[var(--bearish)]" aria-hidden="true">•</span>
              <span>{flag}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
