import { useState, useRef, useEffect, useCallback } from 'react'
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
  { to: '/calibration', label: 'Track Record' },
  { to: '/backtest', label: 'Signal History' },
  { to: '/evals', label: 'Quality Metrics' },
] as const

const OPS_NAV = [
  { to: '/ops', label: 'Ops Dashboard' },
  { to: '/replay', label: 'Trace Replay' },
] as const

export default function Header() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [openDropdownId, setOpenDropdownId] = useState<string | null>(null)
  const { pathname } = useLocation()

  // Close mobile drawer on route change
  useEffect(() => {
    setMobileOpen(false)
  }, [pathname])

  // Close all dropdowns on route change
  useEffect(() => {
    setOpenDropdownId(null)
  }, [pathname])

  const handleDropdownToggle = useCallback((id: string) => {
    setOpenDropdownId((prev) => (prev === id ? null : id))
  }, [])

  const handleDropdownClose = useCallback(() => {
    setOpenDropdownId(null)
  }, [])

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
            <NavDropdown
              id="history"
              label="History"
              items={HISTORY_NAV}
              isOpen={openDropdownId === 'history'}
              onToggle={handleDropdownToggle}
              onClose={handleDropdownClose}
            />
            <NavDropdown
              id="ops"
              label="Ops"
              items={OPS_NAV}
              isOpen={openDropdownId === 'ops'}
              onToggle={handleDropdownToggle}
              onClose={handleDropdownClose}
            />
          </nav>

          <ThemeSwitcher />

          {/* Mobile hamburger */}
          <button
            onClick={() => setMobileOpen((prev) => !prev)}
            className="md:hidden min-w-[44px] min-h-[44px] flex items-center justify-center rounded-lg hover:bg-[var(--surface-elevated)] transition-colors focus-ring"
            aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={mobileOpen}
            aria-controls="mobile-nav"
          >
            {mobileOpen ? <X className="w-5 h-5 text-[var(--text-secondary)]" /> : <Menu className="w-5 h-5 text-[var(--text-secondary)]" />}
          </button>
        </div>
      </div>

      {/* Mobile nav drawer */}
      {mobileOpen && (
        <nav id="mobile-nav" className="md:hidden border-t border-[var(--border)] bg-[var(--surface)] px-4 py-3 space-y-1 animate-fade-in" aria-label="Mobile navigation">
          <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider px-3 pt-1 pb-2">Main</p>
          {PRIMARY_NAV.map((item) => (
            <NavLink key={item.to} to={item.to} label={item.label} mobile onClick={() => setMobileOpen(false)} />
          ))}
          <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider px-3 pt-4 pb-2">History</p>
          {HISTORY_NAV.map((item) => (
            <NavLink key={item.to} to={item.to} label={item.label} mobile onClick={() => setMobileOpen(false)} />
          ))}
          <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider px-3 pt-4 pb-2">Ops</p>
          {OPS_NAV.map((item) => (
            <NavLink key={item.to} to={item.to} label={item.label} mobile onClick={() => setMobileOpen(false)} />
          ))}
        </nav>
      )}
    </header>
  )
}

function NavDropdown({
  id,
  label,
  items,
  isOpen,
  onToggle,
  onClose,
}: {
  id: string
  label: string
  items: ReadonlyArray<{ to: string; label: string }>
  isOpen: boolean
  onToggle: (id: string) => void
  onClose: () => void
}) {
  const ref = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const { pathname } = useLocation()

  const hasActiveChild = items.some((item) => pathname === item.to)
  const panelId = `dropdown-panel-${id}`

  // Close on click outside or Escape (scoped to when focus is within)
  useEffect(() => {
    if (!isOpen) return
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose()
      }
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape' && ref.current?.contains(document.activeElement)) {
        onClose()
        triggerRef.current?.focus()
      }
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [isOpen, onClose])

  // Close when focus leaves the dropdown entirely
  function handleFocusOut(e: React.FocusEvent) {
    if (ref.current && !ref.current.contains(e.relatedTarget as Node)) {
      onClose()
    }
  }

  return (
    <div ref={ref} className="relative" onBlur={handleFocusOut}>
      <button
        ref={triggerRef}
        onClick={() => onToggle(id)}
        aria-expanded={isOpen}
        aria-controls={panelId}
        aria-haspopup="true"
        className={[
          'text-sm font-medium rounded-md transition-colors focus-ring min-h-[44px] px-3 py-2 inline-flex items-center gap-1',
          hasActiveChild
            ? 'bg-[var(--accent-bg)] text-[var(--accent)]'
            : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-elevated)]',
        ].join(' ')}
      >
        {label}
        <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div id={panelId} className="absolute right-0 top-full mt-1 w-44 rounded-lg border border-[var(--border)] bg-[var(--surface-elevated)] shadow-lg py-1 z-50 animate-fade-in">
          {items.map((item) => {
            const isActive = pathname === item.to
            return (
              <Link
                key={item.to}
                to={item.to}
                onClick={onClose}
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
