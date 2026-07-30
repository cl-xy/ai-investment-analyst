import { Loader2 } from 'lucide-react'

export default function LoadingSpinner() {
  return (
    <div
      className="flex flex-col items-center justify-center py-20 gap-4 text-[var(--text-muted)]"
      role="status"
    >
      <Loader2 className="w-8 h-8 text-[var(--accent)] motion-safe:animate-spin" aria-hidden="true" />
      <p className="text-sm font-medium text-[var(--text-secondary)]" aria-hidden="true">Loading...</p>
      <span className="sr-only">Loading content, please wait.</span>
    </div>
  )
}
