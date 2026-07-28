export default function Footer() {
  return (
    <footer className="border-t border-[var(--border)] mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex flex-col sm:flex-row items-center justify-between gap-2">
        <p className="text-xs text-[var(--text-muted)] text-center sm:text-left">
          For educational purposes only. Not investment advice.
        </p>
        <p className="text-xs text-[var(--text-muted)] text-center sm:text-right">
          Data may be delayed. Sources: yfinance, NewsAPI, SEC EDGAR.
        </p>
      </div>
    </footer>
  )
}
