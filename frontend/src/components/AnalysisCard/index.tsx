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

const SECTION_DIVIDER = <hr className="border-gray-100" />

export default function AnalysisCard({ analysis }: Props) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="bg-white rounded-2xl shadow border border-gray-200 overflow-hidden">
      {/* Card header */}
      <div
        className="flex items-center justify-between px-6 py-4 cursor-pointer hover:bg-gray-50 transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <div className="flex items-center gap-4">
          <span className="text-2xl font-bold font-mono text-gray-900">{analysis.ticker}</span>
          <SignalBadge signal={analysis.signal} confidence={analysis.confidence} />
        </div>
        <button className="text-gray-400 hover:text-gray-600 text-xl font-bold">
          {expanded ? '▲' : '▼'}
        </button>
      </div>

      {expanded && (
        <div className="px-6 pb-6 space-y-6">
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
