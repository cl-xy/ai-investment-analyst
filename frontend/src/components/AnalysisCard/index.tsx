import { useId, useState } from 'react'
import { Briefcase, Globe } from 'lucide-react'
import type { TickerAnalysis } from '../../types/analysis'
import SignalBadge from './SignalBadge'
import SentimentBar from './SentimentBar'
import PriceMetrics from './PriceMetrics'
import MarketPositionSection from './MarketPositionSection'
import RegulatorySection from './RegulatorySection'
import InfoSection from './InfoSection'

interface Props {
  analysis: TickerAnalysis
}

function SectionDivider() {
  return <hr className="border-[var(--border)]" />
}

export default function AnalysisCard({ analysis }: Props) {
  const [expanded, setExpanded] = useState(true)
  const contentId = useId()

  return (
    <div className="bg-[var(--surface-elevated)] rounded-2xl border border-[var(--border)] overflow-hidden">
      {/* Card header - keyboard operable */}
      <button
        type="button"
        className="w-full flex items-center justify-between px-6 py-4 hover:bg-[var(--surface)] transition-colors text-left focus-ring rounded-t-2xl"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-controls={expanded ? contentId : undefined}
      >
        <span className="flex items-center gap-4">
          <span className="text-2xl font-bold font-mono text-[var(--text-primary)]">{analysis.ticker}</span>
          <SignalBadge signal={analysis.signal} confidence={analysis.confidence} />
        </span>
        <span className="text-[var(--text-muted)] text-xl font-bold" aria-hidden="true">
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {expanded && (
        <div id={contentId} className="px-6 pb-6 space-y-6">
          {/* Sentiment */}
          <SentimentBar score={analysis.sentiment_score} />

          <SectionDivider />

          {/* Valuation metrics */}
          <PriceMetrics priceData={{
            ...analysis.price_data,
            beta: analysis.fundamentals?.beta,
            dividend_yield: analysis.fundamentals?.dividend_yield,
          }} />

          <SectionDivider />

          {/* Market position & fundamentals */}
          <MarketPositionSection fundamentals={analysis.fundamentals} />

          <SectionDivider />

          {/* Management & governance from SEC notes */}
          <InfoSection
            icon={<Briefcase size={14} />}
            title="Management & Corporate Governance"
            content={analysis.sec_notes}
            fallback="No SEC filing data available."
          />

          <SectionDivider />

          {/* Macroeconomic context */}
          <InfoSection
            icon={<Globe size={14} />}
            title="Macroeconomic Context"
            content={analysis.news_summary}
            fallback="No macroeconomic data available."
          />

          <SectionDivider />

          {/* Regulatory & risk flags */}
          <RegulatorySection riskFlags={analysis.risk_flags} />
        </div>
      )}
    </div>
  )
}
