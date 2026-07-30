import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Generic timed-undo hook. Stores a payload for a configurable window,
 * then auto-dismisses. Useful for optimistic deletes with undo support.
 */
export function useTimedUndo<T>(timeoutMs = 5000) {
  const [pending, setPending] = useState(false)
  const payloadRef = useRef<T | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  const dismiss = useCallback(() => {
    clearTimer()
    payloadRef.current = null
    setPending(false)
  }, [clearTimer])

  const trigger = useCallback((payload: T) => {
    clearTimer()
    payloadRef.current = payload
    setPending(true)
    timerRef.current = setTimeout(() => {
      payloadRef.current = null
      setPending(false)
    }, timeoutMs)
  }, [clearTimer, timeoutMs])

  const undo = useCallback((): T | null => {
    if (payloadRef.current === null) return null
    const payload = payloadRef.current
    dismiss()
    return payload
  }, [dismiss])

  // Cleanup on unmount
  useEffect(() => {
    return () => clearTimer()
  }, [clearTimer])

  return { trigger, undo, dismiss, pending }
}
