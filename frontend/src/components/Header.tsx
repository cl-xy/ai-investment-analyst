import { useState } from 'react'
import { TrendingUp, Menu, X } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { ThemeSwitcher } from './ThemeSwitcher'

const NAV_ITEMS = [
  { to: '/', label: 'Analyze' },
  { to: '/dashboard', label: 'History' },
  { to: '/explore', label: 'Explore' },
  { to: '/evals', label: 'Evals' },
  { to: '/compare', label: 'Compare' },
  { to: '/backtest', label: 'Signals' },
  { to: '/chat', label: 'Chat' },
] as const

export default function Header() {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <header className="border-b border-[var(--border)] bg-[var(--surface)]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5 focus-ring rounded min-h-[44px]">
          <TrendingUp className="w-5 h-5 text-[var(--accent)]" />
          <div>
            <h1 className="text-base font-semibold text-[var(--text-primary)] leading-tight">
              Investment Analyst
            </h1>
            <p className="text-xs text-[var(--text-muted)] hidden sm:block">
              Multi-agent analysis with LangGraph + MCP
            </p>
          </div>
        </Link>

        <div className="flex items-center gap-2">
          {/* Desktop nav */}
          <nav className="hidden md:flex items-center gap-1" aria-label="Main navigation">
            {NAV_ITEMS.map((item) => (
              <NavLink key={item.to} to={item.to} label={item.label} />
            ))}
          </nav>

          <ThemeSwitcher />

          {/* Mobile hamburger */}
          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="md:hidden min-w-[44px] min-h-[44px] flex items-center justify-center rounded-lg hover:bg-[var(--surface-elevated)] transition-colors focus-ring"
            aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={mobileOpen}
          >
            {mobileOpen ? <X className="w-5 h-5 text-[var(--text-secondary)]" /> : <Menu className="w-5 h-5 text-[var(--text-secondary)]" />}
          </button>
        </div>
      </div>

      {/* Mobile nav drawer */}
      {mobileOpen && (
        <nav className="md:hidden border-t border-[var(--border)] bg-[var(--surface)] px-4 py-3 space-y-1 animate-fade-in" aria-label="Main navigation">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} label={item.label} mobile onClick={() => setMobileOpen(false)} />
          ))}
        </nav>
      )}
    </header>
  )
}

function NavLink({ to, label, mobile, onClick }: { to: string; label: string; mobile?: boolean; onClick?: () => void }) {
  const { pathname } = useLocation()
  const isActive = pathname === to

  return (
    <Link
      to={to}
      onClick={onClick}
      aria-current={isActive ? 'page' : undefined}
      className={[
        'text-sm font-medium rounded-md transition-colors focus-ring min-h-[44px]',
        mobile
          ? 'block px-3 py-3 rounded-lg'
          : 'px-3 py-2 inline-flex items-center',
        isActive
          ? 'bg-[var(--accent-bg)] text-[var(--accent)]'
          : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-elevated)]',
      ].join(' ')}
    >
      {label}
    </Link>
  )
}
