import type { AnalyzeResponse } from '../types/analysis'
import AnalysisCard from './AnalysisCard'
import LoadingSpinner from './LoadingSpinner'

interface Props {
  result: AnalyzeResponse | null
  loading: boolean
  error: string | null
}

export default function AnalysisResultsPage({ result, loading, error }: Props) {
  if (loading) {
    return <LoadingSpinner />
  }

  if (error) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16">
        <div className="bg-red-50 border border-red-200 text-red-800 rounded-xl px-5 py-4 text-sm">
          <strong>Error:</strong> {error}
        </div>
      </div>
    )
  }

  if (!result) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-24 flex flex-col items-center gap-4 text-center">
        <span className="text-5xl">📊</span>
        <h3 className="text-xl font-semibold text-gray-700">No analysis yet</h3>
        <p className="text-gray-400 text-sm">
          Head to the <strong>Watchlist</strong> tab, add some stocks, and click Analyze.
        </p>
      </div>
    )
  }

  const { tickers, analyses } = result

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-gray-800">
          Analysis Results
          <span className="ml-2 text-sm font-normal text-gray-400">
            ({tickers.length} stock{tickers.length > 1 ? 's' : ''})
          </span>
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
