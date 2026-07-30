import { WifiOff } from 'lucide-react'
import { useOnlineStatus } from '../hooks/useOnlineStatus'

export default function OfflineBanner() {
  const online = useOnlineStatus()

  return (
    <div role="status" aria-live="polite" aria-atomic="true">
      {!online && (
        <div className="bg-amber-500/10 border-b border-amber-500/20 px-4 py-2 flex items-center justify-center gap-2">
          <WifiOff className="w-3.5 h-3.5 text-amber-500" aria-hidden="true" />
          <span className="text-xs font-medium text-amber-500">
            You are offline. Some features may be unavailable.
          </span>
        </div>
      )}
    </div>
  )
}
