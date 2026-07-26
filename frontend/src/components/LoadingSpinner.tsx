import { Loader2 } from 'lucide-react'

export default function LoadingSpinner() {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4 text-[var(--text-muted)]">
      <Loader2 className="w-8 h-8 text-[var(--accent)] animate-spin" />
      <p className="text-sm font-medium text-[var(--text-secondary)]">Loading...</p>
    </div>
  )
}
