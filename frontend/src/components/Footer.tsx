import { ExternalLink } from 'lucide-react'

const GITHUB_URL = 'https://github.com/cl-xy/ai-investment-analyst'

const links = [
  { label: 'Source Code', href: GITHUB_URL },
  { label: 'Architecture', href: `${GITHUB_URL}/blob/main/docs/ARCHITECTURE.md` },
  { label: 'How it Works', href: `${GITHUB_URL}/blob/main/README.md` },
]

export default function Footer() {
  return (
    <footer className="border-t border-[var(--border)] mt-auto">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4">
        <nav aria-label="Footer links">
          <ul className="flex flex-wrap items-center justify-center gap-x-1 gap-y-1 mb-2 list-none p-0 m-0">
            {links.map((link, i) => (
              <li key={link.label} className="flex items-center">
                {i > 0 && <span className="text-[var(--text-muted)] mx-1.5" aria-hidden="true">&middot;</span>}
                <a
                  href={link.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors inline-flex items-center gap-1"
                >
                  {link.label}
                  <ExternalLink className="w-3 h-3" aria-hidden="true" />
                  <span className="sr-only">(opens in new tab)</span>
                </a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="flex flex-col sm:flex-row items-center justify-between gap-2">
          <p className="text-xs text-[var(--text-muted)] text-center sm:text-left">
            For educational purposes only. Not investment advice.
          </p>
          <p className="text-xs text-[var(--text-muted)] text-center sm:text-right">
            Data may be delayed. Sources: yfinance, NewsAPI, SEC EDGAR.
          </p>
        </div>
      </div>
    </footer>
  )
}
