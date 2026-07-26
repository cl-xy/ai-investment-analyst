export default function Footer() {
  return (
    <footer className="border-t border-[var(--border)] mt-auto">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <p className="text-xs text-[var(--text-muted)]">
          For educational purposes only. Not investment advice.
        </p>
        <p className="text-xs text-[var(--text-muted)]">
          Data may be delayed. Sources: yfinance, NewsAPI, SEC EDGAR.
        </p>
      </div>
    </footer>
  )
}
