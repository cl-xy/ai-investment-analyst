import { useState, useRef, useEffect } from 'react'
import { TrendingUp, Menu, X, ChevronDown } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { ThemeSwitcher } from './ThemeSwitcher'

const PRIMARY_NAV = [
  { to: '/', label: 'Analyze' },
  { to: '/explore', label: 'Explore' },
  { to: '/compare', label: 'Compare' },
  { to: '/chat', label: 'Chat' },
] as const

const HISTORY_NAV = [
  { to: '/dashboard', label: 'Past Analyses' },
  { to: '/backtest', label: 'Signal History' },
  { to: '/evals', label: 'Quality Metrics' },
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
            {PRIMARY_NAV.map((item) => (
              <NavLink key={item.to} to={item.to} label={item.label} />
            ))}
            <NavDropdown label="History" items={HISTORY_NAV} />
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
          <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider px-3 pt-1 pb-2">Main</p>
          {PRIMARY_NAV.map((item) => (
            <NavLink key={item.to} to={item.to} label={item.label} mobile onClick={() => setMobileOpen(false)} />
          ))}
          <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider px-3 pt-4 pb-2">History</p>
          {HISTORY_NAV.map((item) => (
            <NavLink key={item.to} to={item.to} label={item.label} mobile onClick={() => setMobileOpen(false)} />
          ))}
        </nav>
      )}
    </header>
  )
}

function NavDropdown({ label, items }: { label: string; items: ReadonlyArray<{ to: string; label: string }> }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const { pathname } = useLocation()

  const hasActiveChild = items.some((item) => pathname === item.to)

  // Close on click outside or Escape
  useEffect(() => {
    if (!open) return
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [open])

  return (
    <div ref={ref} className="relative">
      <button
        ref={triggerRef}
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className={[
          'text-sm font-medium rounded-md transition-colors focus-ring min-h-[44px] px-3 py-2 inline-flex items-center gap-1',
          hasActiveChild
            ? 'bg-[var(--accent-bg)] text-[var(--accent)]'
            : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-elevated)]',
        ].join(' ')}
      >
        {label}
        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-44 rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] shadow-lg py-1 z-50 animate-fade-in">
          {items.map((item) => {
            const isActive = pathname === item.to
            return (
              <Link
                key={item.to}
                to={item.to}
                onClick={() => setOpen(false)}
                aria-current={isActive ? 'page' : undefined}
                className={[
                  'block px-4 py-2.5 text-sm transition-colors',
                  isActive
                    ? 'bg-[var(--accent-bg)] text-[var(--accent)] font-medium'
                    : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface)]',
                ].join(' ')}
              >
                {item.label}
              </Link>
            )
          })}
        </div>
      )}
    </div>
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
