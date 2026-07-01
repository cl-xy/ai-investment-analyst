import type { AnalyzeResponse } from '../types/analysis'
import AnalysisCard from './AnalysisCard'

interface Props {
  result: AnalyzeResponse
}

export default function AnalysisResults({ result }: Props) {
  const { tickers, analyses } = result

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">
          Analysis Results
          <span className="ml-2 text-sm font-normal text-gray-400">({tickers.length} stock{tickers.length > 1 ? 's' : ''})</span>
        </h2>
      </div>

      {tickers.map((ticker) => {
        const analysis = analyses[ticker]
        if (!analysis) return null
        return <AnalysisCard key={ticker} analysis={analysis} />
      })}
    </div>
  )
}
