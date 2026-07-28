import { useState } from 'react'
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

const SECTION_DIVIDER = <hr className="border-[var(--border)]" />

export default function AnalysisCard({ analysis }: Props) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="bg-[var(--surface-elevated)] rounded-2xl border border-[var(--border)] overflow-hidden">
      {/* Card header - #5: keyboard operable */}
      <button
        className="w-full flex items-center justify-between px-6 py-4 hover:bg-[var(--surface)] transition-colors text-left focus-ring rounded-t-2xl"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-controls={`analysis-content-${analysis.ticker}`}
      >
        <div className="flex items-center gap-4">
          <span className="text-2xl font-bold font-mono text-[var(--text-primary)]">{analysis.ticker}</span>
          <SignalBadge signal={analysis.signal} confidence={analysis.confidence} />
        </div>
        <span className="text-[var(--text-muted)] text-xl font-bold" aria-hidden="true">
          {expanded ? '▲' : '▼'}
        </span>
      </button>

      {expanded && (
        <div id={`analysis-content-${analysis.ticker}`} className="px-6 pb-6 space-y-6">
          {/* Sentiment */}
          <SentimentBar score={analysis.sentiment_score} />

          {SECTION_DIVIDER}

          {/* Valuation metrics */}
          <PriceMetrics priceData={{
            ...analysis.price_data,
            beta: analysis.fundamentals.beta,
            dividend_yield: analysis.fundamentals.dividend_yield,
          }} />

          {SECTION_DIVIDER}

          {/* Market position & fundamentals */}
          <MarketPositionSection fundamentals={analysis.fundamentals} />

          {SECTION_DIVIDER}

          {/* Management & governance from SEC notes */}
          <InfoSection
            icon="👔"
            title="Management & Corporate Governance"
            content={analysis.sec_notes}
            fallback="No SEC filing data available."
          />

          {SECTION_DIVIDER}

          {/* Macroeconomic context */}
          <InfoSection
            icon="🌍"
            title="Macroeconomic Context"
            content={analysis.news_summary}
            fallback="No macroeconomic data available."
          />

          {SECTION_DIVIDER}

          {/* Regulatory & risk flags */}
          <RegulatorySection riskFlags={analysis.risk_flags} />
        </div>
      )}
    </div>
  )
}
