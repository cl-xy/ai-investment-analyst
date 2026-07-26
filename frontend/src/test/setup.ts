import '@testing-library/jest-dom'
import 'vitest-axe/extend-expect'
import * as matchers from 'vitest-axe/matchers'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeAll, afterAll, expect } from 'vitest'
import { server } from './server'

expect.extend(matchers)

// Mock EventSource (not available in jsdom)
class MockEventSource {
  static readonly CONNECTING = 0
  static readonly OPEN = 1
  static readonly CLOSED = 2

  readonly CONNECTING = 0
  readonly OPEN = 1
  readonly CLOSED = 2

  readyState = MockEventSource.OPEN
  url: string
  withCredentials = false
  onerror: ((ev: Event) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onopen: ((ev: Event) => void) | null = null

  private listeners: Record<string, EventListener[]> = {}

  constructor(url: string) {
    this.url = url
  }

  addEventListener(type: string, listener: EventListener) {
    if (!this.listeners[type]) this.listeners[type] = []
    this.listeners[type].push(listener)
  }

  removeEventListener(type: string, listener: EventListener) {
    if (!this.listeners[type]) return
    this.listeners[type] = this.listeners[type].filter((l) => l !== listener)
  }

  close() {
    this.readyState = MockEventSource.CLOSED
  }

  dispatchEvent(_event: Event): boolean {
    return true
  }
}

globalThis.EventSource = MockEventSource as unknown as typeof EventSource

// Ensure localStorage is available (some jsdom versions need this)
if (typeof globalThis.localStorage === 'undefined') {
  const store: Record<string, string> = {}
  globalThis.localStorage = {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value },
    removeItem: (key: string) => { delete store[key] },
    clear: () => { Object.keys(store).forEach((k) => delete store[k]) },
    get length() { return Object.keys(store).length },
    key: (index: number) => Object.keys(store)[index] ?? null,
  }
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
  localStorage.clear()
})
afterAll(() => server.close())
