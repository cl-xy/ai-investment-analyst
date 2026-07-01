export default function LoadingSpinner() {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4 text-gray-500">
      <svg className="animate-spin h-12 w-12 text-blue-500" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
      </svg>
      <p className="text-lg font-medium">Running investment analysis…</p>
      <p className="text-sm text-gray-400">Fetching news, market data, SEC filings, and running AI analysis</p>
    </div>
  )
}
