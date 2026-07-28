import { Info } from 'lucide-react'

export default function InvestmentDisclaimer() {
  return (
    <div className="flex items-center gap-2 text-[10px] text-[var(--text-muted)] py-2">
      <Info className="w-3 h-3 shrink-0" />
      <span>AI-generated analysis for informational purposes only. Not financial advice. Verify independently before making investment decisions.</span>
    </div>
  )
}
