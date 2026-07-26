import { TrendingUp } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { ThemeSwitcher } from './ThemeSwitcher'

export default function Header() {
  return (
    <header className="border-b border-[var(--border)] bg-[var(--surface)]">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5 focus-ring rounded">
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
          <nav className="flex items-center gap-1 overflow-x-auto">
            <NavLink to="/" label="Analyze" />
            <NavLink to="/dashboard" label="History" />
            <NavLink to="/explore" label="Explore" />
            <NavLink to="/evals" label="Evals" />
            <NavLink to="/compare" label="Compare" />
          </nav>
          <ThemeSwitcher />
        </div>
      </div>
    </header>
  )
}

function NavLink({ to, label }: { to: string; label: string }) {
  const { pathname } = useLocation()
  const isActive = pathname === to

  return (
    <Link
      to={to}
      className={[
        'px-3 py-1.5 text-sm font-medium rounded-md transition-colors focus-ring',
        isActive
          ? 'bg-[var(--accent-bg)] text-[var(--accent)]'
          : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-elevated)]',
      ].join(' ')}
    >
      {label}
    </Link>
  )
}
