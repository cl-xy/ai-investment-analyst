interface Props {
  riskFlags: string[]
}

export default function RegulatorySection({ riskFlags }: Props) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">⚠️ Risk Flags</h3>
      {riskFlags.length === 0 ? (
        <p className="text-sm text-gray-400">No significant risk flags identified.</p>
      ) : (
        <ul className="space-y-1.5">
          {riskFlags.map((flag, i) => (
            <li key={i} className="flex items-start gap-2 text-sm text-red-700">
              <span className="mt-0.5 text-red-400">•</span>
              <span>{flag}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
