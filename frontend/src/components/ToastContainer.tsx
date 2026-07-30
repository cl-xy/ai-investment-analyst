import { useToastStore, type Toast } from '../stores/toastStore'
import { X, CheckCircle2, AlertCircle, Info, AlertTriangle } from 'lucide-react'

const ICONS = {
  info: Info,
  success: CheckCircle2,
  error: AlertCircle,
  warning: AlertTriangle,
}

const TYPE_STYLES = {
  info: 'border-[var(--accent)]/30 bg-[var(--surface-elevated)]',
  success: 'border-[var(--success)]/30 bg-[var(--success-bg)]',
  error: 'border-[var(--error)]/30 bg-[var(--error-bg)]',
  warning: 'border-[var(--warning)]/30 bg-[var(--warning-bg)]',
}

const ICON_STYLES = {
  info: 'text-[var(--accent)]',
  success: 'text-[var(--success)]',
  error: 'text-[var(--error)]',
  warning: 'text-[var(--warning)]',
}

export default function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts)
  const removeToast = useToastStore((s) => s.removeToast)

  return (
    <div
      className="fixed bottom-16 left-4 right-4 sm:bottom-4 sm:left-auto sm:right-4 z-[100] flex flex-col gap-2 max-w-sm sm:w-auto"
      role="region"
      aria-label="Notifications"
      aria-live="polite"
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={() => removeToast(t.id)} />
      ))}
    </div>
  )
}

function ToastItem({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const Icon = ICONS[toast.type] ?? Info

  return (
    <div
      className={`flex items-start gap-3 px-4 py-3 rounded-xl border shadow-lg animate-slide-in-right ${TYPE_STYLES[toast.type] ?? TYPE_STYLES.info}`}
      role={toast.type === 'error' ? 'alert' : 'status'}
    >
      <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${ICON_STYLES[toast.type] ?? ICON_STYLES.info}`} aria-hidden="true" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-[var(--text-primary)]">{toast.message}</p>
        {toast.action && (
          <button
            type="button"
            onClick={() => {
              try {
                toast.action!.onClick()
              } finally {
                onDismiss()
              }
            }}
            className="mt-1 text-xs font-medium text-[var(--accent)] hover:underline focus-ring rounded"
          >
            {toast.action.label}
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        className="shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors p-1 min-w-[28px] min-h-[28px] flex items-center justify-center focus-ring rounded"
        aria-label="Dismiss notification"
      >
        <X className="w-3.5 h-3.5" aria-hidden="true" />
      </button>
    </div>
  )
}
