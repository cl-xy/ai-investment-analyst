import { Link, useLocation } from 'react-router-dom'

interface Props {
  loading: boolean
  error: string | null
}

export default function TabNav({ loading, error }: Props) {
  const { pathname } = useLocation()

  const tabs = [
    { path: '/', label: 'Watchlist', icon: '👀' },
    { path: '/explore', label: 'Explore', icon: '🔥' },
    { path: '/dashboard', label: 'Stock Analysis Results', icon: '📊' },
  ]

  return (
    <div className="bg-white border-b border-gray-200">
      <div className="max-w-5xl mx-auto px-4">
        <nav className="flex gap-0" aria-label="Tabs">
          {tabs.map((tab) => {
            const isActive = pathname === tab.path
            const isDashboard = tab.path === '/dashboard'

            return (
              <Link
                key={tab.path}
                to={tab.path}
                className={[
                  'flex items-center gap-2 px-5 py-4 text-sm font-medium border-b-2 transition-colors',
                  isActive
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300',
                ].join(' ')}
                aria-current={isActive ? 'page' : undefined}
              >
                <span>{tab.icon}</span>
                {tab.label}
                {isDashboard && loading && (
                  <span className="ml-1 bg-yellow-100 text-yellow-700 text-xs font-semibold px-2 py-0.5 rounded-full">
                    Running…
                  </span>
                )}
                {isDashboard && !loading && error && (
                  <span className="ml-1 bg-red-100 text-red-700 text-xs font-semibold px-2 py-0.5 rounded-full">
                    Error
                  </span>
                )}
              </Link>
            )
          })}
        </nav>
      </div>
    </div>
  )
}
