import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  description?: string
  action?: { label: string; onClick: () => void }
  compact?: boolean
}

export default function EmptyState({ icon, title, description, action, compact }: EmptyStateProps) {
  return (
    <div className={`flex flex-col items-center text-center ${compact ? 'py-8 gap-3' : 'py-16 gap-4'}`}>
      <div className="text-[var(--text-muted)]" aria-hidden="true">{icon}</div>
      <div>
        <h3 className={`font-semibold text-[var(--text-secondary)] ${compact ? 'text-base' : 'text-lg'}`}>
          {title}
        </h3>
        {description && (
          <p className="text-sm text-[var(--text-muted)] mt-1 max-w-sm mx-auto">
            {description}
          </p>
        )}
      </div>
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          className="text-sm font-medium text-[var(--accent)] hover:underline focus-ring rounded px-3 py-2 min-h-[44px] min-w-[44px]"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}
