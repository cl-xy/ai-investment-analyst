/**
 * Minimal fetch-based SSE client.
 *
 * The native browser EventSource is a GET that cannot send custom headers, so
 * SSE auth had to put the demo password in the URL query string, where it
 * leaks into access logs and browser history. This client uses fetch() with a
 * ReadableStream body reader instead, so credentials ride in the Authorization
 * header (via authHeaders()) and never touch the URL.
 *
 * It exposes the small slice of the EventSource interface the app actually
 * uses - addEventListener(type, handler), onerror, close() - so the existing
 * consumers (useAnalysisStream, ChatPage) swap in with no behavioral change:
 * named events, event.data, event.lastEventId, single-retry and resume logic
 * all keep working. No external dependency.
 *
 * Not a full EventSource polyfill: it does not auto-reconnect (callers own
 * retry), and readyState is not exposed. That is intentional - the callers
 * already manage their own lifecycle.
 */

import { authHeaders } from './config'

export interface SSEMessage {
  /** The concatenated `data:` payload for one event. */
  data: string
  /** The `id:` field of the most recent event, if any. */
  lastEventId: string
}

type SSEHandler = (event: SSEMessage) => void

export class FetchEventSource {
  private controller = new AbortController()
  private listeners = new Map<string, SSEHandler[]>()
  private closed = false
  private lastEventId = ''

  /** Mirrors EventSource.onerror. Called once on network/HTTP/parse failure. */
  onerror: (() => void) | null = null

  constructor(url: string) {
    // Kick off the request on the next tick so callers can attach listeners
    // and set onerror synchronously after construction, exactly like they do
    // with `new EventSource(url)`.
    queueMicrotask(() => void this.run(url))
  }

  addEventListener(type: string, handler: SSEHandler): void {
    const existing = this.listeners.get(type)
    if (existing) {
      existing.push(handler)
    } else {
      this.listeners.set(type, [handler])
    }
  }

  close(): void {
    this.closed = true
    this.controller.abort()
  }

  private emitError(): void {
    if (this.closed) return
    this.onerror?.()
  }

  private dispatch(eventType: string, data: string): void {
    if (this.closed) return
    const handlers = this.listeners.get(eventType)
    if (!handlers || handlers.length === 0) return
    const message: SSEMessage = { data, lastEventId: this.lastEventId }
    for (const handler of handlers) {
      handler(message)
    }
  }

  private async run(url: string): Promise<void> {
    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          ...authHeaders(),
          Accept: 'text/event-stream',
        },
        signal: this.controller.signal,
        // A 3xx that drops the Authorization header would leak nothing useful
        // but could silently change the endpoint; fail instead of following.
        redirect: 'error',
      })

      if (!response.ok || !response.body) {
        this.emitError()
        return
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // SSE frames are separated by a blank line. Normalize CRLF to LF.
        let sepIndex: number
        buffer = buffer.replace(/\r\n/g, '\n')
        while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, sepIndex)
          buffer = buffer.slice(sepIndex + 2)
          this.processFrame(frame)
        }
      }

      // Stream ended cleanly. If the caller did not close() (e.g. it saw a
      // terminal event), that is expected; otherwise treat an unsolicited
      // end as an error so the retry path can fire.
      if (!this.closed) {
        this.emitError()
      }
    } catch {
      // AbortError (from close()) and network errors both land here. A
      // deliberate close() must not fire onerror; everything else should.
      this.emitError()
    }
  }

  /**
   * Parse one SSE frame per the wire format: lines of `field: value`.
   * Comment lines (starting with ':', e.g. heartbeats) are ignored.
   * Multiple `data:` lines are joined with newlines.
   */
  private processFrame(frame: string): void {
    let eventType = 'message'
    const dataLines: string[] = []
    let sawData = false

    for (const rawLine of frame.split('\n')) {
      if (rawLine === '' || rawLine.startsWith(':')) continue
      const colon = rawLine.indexOf(':')
      const field = colon === -1 ? rawLine : rawLine.slice(0, colon)
      // A single leading space after the colon is stripped per the SSE spec.
      let value = colon === -1 ? '' : rawLine.slice(colon + 1)
      if (value.startsWith(' ')) value = value.slice(1)

      if (field === 'event') {
        eventType = value
      } else if (field === 'data') {
        dataLines.push(value)
        sawData = true
      } else if (field === 'id') {
        this.lastEventId = value
      }
      // Ignore `retry:` and unknown fields.
    }

    if (sawData) {
      this.dispatch(eventType, dataLines.join('\n'))
    }
  }
}
