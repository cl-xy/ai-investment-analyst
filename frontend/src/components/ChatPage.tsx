import { useState, useRef, useEffect, useCallback, type KeyboardEvent } from 'react'
import { Send, Bot, User, Wrench, Square, Trash2 } from 'lucide-react'
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion'
import { useRestorableState } from '../hooks/useRestorableState'
import InvestmentDisclaimer from './InvestmentDisclaimer'
import { API_BASE, authParam } from '../api/config'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  toolCalls?: { name: string; args: Record<string, unknown> }[]
  isStreaming?: boolean
}

function formatRelativeTime(timestamp: number): string {
  const diff = Math.floor((Date.now() - timestamp) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return new Date(timestamp).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function extractTimestamp(id: string): number {
  const parts = id.split('-')
  const ts = Number(parts[parts.length - 1])
  return Number.isFinite(ts) && ts > 1e12 ? ts : Date.now()
}

export default function ChatPage() {
  const [messages, setMessages] = useRestorableState<ChatMessage[]>('chat-messages', [])
  // #22: Persist chat input draft across refresh
  const [input, setInput] = useRestorableState('chat-input', '')
  const [isStreaming, setIsStreaming] = useState(false)
  const [, setTick] = useState(0)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const threadId = useRef(`chat-${Date.now()}`)
  // #2: Store EventSource ref for cleanup on unmount
  const esRef = useRef<EventSource | null>(null)
  const mountedRef = useRef(true)
  const inputRef = useRef(input)
  const reducedMotion = usePrefersReducedMotion()

  // Keep input ref current for stable sendMessage
  inputRef.current = input

  // Strip stale isStreaming from restored messages on mount
  useEffect(() => {
    setMessages((prev) => {
      const hasStale = prev.some((m) => m.isStreaming)
      if (!hasStale) return prev
      return prev.map((m) => m.isStreaming ? { ...m, isStreaming: false } : m)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      // #2: Clean up on unmount
      esRef.current?.close()
      esRef.current = null
    }
  }, [])

  // Re-render every 30s to keep relative timestamps current
  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 30_000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    // #7: Respect reduced motion for scroll behavior
    messagesEndRef.current?.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth' })
  }, [messages, reducedMotion])

  // #26: Stop streaming control
  const stopStreaming = useCallback(() => {
    esRef.current?.close()
    esRef.current = null
    setIsStreaming(false)
    setMessages((prev) => {
      const updated = [...prev]
      const last = updated[updated.length - 1]
      if (last?.role === 'assistant' && last.isStreaming) {
        updated[updated.length - 1] = { ...last, isStreaming: false }
      }
      return updated
    })
  }, [])

  const sendMessage = useCallback(() => {
    const text = inputRef.current.trim()
    if (!text || isStreaming) return

    const userMsg: ChatMessage = { id: `user-${Date.now()}`, role: 'user', content: text }
    const assistantMsg: ChatMessage = { id: `asst-${Date.now()}`, role: 'assistant', content: '', isStreaming: true, toolCalls: [] }

    setMessages((prev) => [...prev, userMsg, assistantMsg])
    setInput('')
    setIsStreaming(true)

    // Close previous connection if any
    esRef.current?.close()

    const auth = authParam()
    const url = `${API_BASE}/api/chat/stream?message=${encodeURIComponent(text)}&thread_id=${threadId.current}${auth ? '&' + auth : ''}`
    const es = new EventSource(url)
    esRef.current = es

    es.addEventListener('llm_token', (e) => {
      if (!mountedRef.current) return
      const data = JSON.parse(e.data)
      const token = data.payload?.text || ''
      setMessages((prev) => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last.role === 'assistant') {
          updated[updated.length - 1] = { ...last, content: last.content + token }
        }
        return updated
      })
    })

    es.addEventListener('tool_call', (e) => {
      if (!mountedRef.current) return
      const data = JSON.parse(e.data)
      const toolName = data.payload?.tool_name || ''
      setMessages((prev) => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last.role === 'assistant') {
          const calls = [...(last.toolCalls || []), { name: toolName, args: data.payload?.args || {} }]
          updated[updated.length - 1] = { ...last, toolCalls: calls }
        }
        return updated
      })
    })

    es.addEventListener('run_completed', () => {
      if (!mountedRef.current) return
      setMessages((prev) => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last.role === 'assistant') {
          updated[updated.length - 1] = { ...last, isStreaming: false }
        }
        return updated
      })
      setIsStreaming(false)
      es.close()
      esRef.current = null
    })

    es.onerror = () => {
      if (!mountedRef.current) return
      setIsStreaming(false)
      setMessages((prev) => {
        const updated = [...prev]
        const last = updated[updated.length - 1]
        if (last.role === 'assistant' && last.isStreaming) {
          updated[updated.length - 1] = { ...last, isStreaming: false, content: last.content || 'Connection error. Please try again.' }
        }
        return updated
      })
      es.close()
      esRef.current = null
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- setInput is identity-stable (useState setter)
  }, [isStreaming])

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6 flex flex-col h-[calc(100vh-8rem)]">
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-[var(--text-primary)]">Chat</h1>
          <p className="text-sm text-[var(--text-muted)]">
            Ask questions about stocks, portfolios, or market conditions.
          </p>
          <InvestmentDisclaimer />
        </div>
        {messages.length > 0 && (
          <button
            onClick={() => setMessages([])}
            className="flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors focus-ring rounded px-2 py-1.5 min-h-[32px]"
            aria-label="Clear chat history"
          >
            <Trash2 className="w-3.5 h-3.5" />
            Clear
          </button>
        )}
      </div>

      {/* Accessible status summary - announces state changes, not every token */}
      <p className="sr-only" aria-live="polite" aria-atomic="true">
        {isStreaming ? 'Assistant is responding...' : messages.length > 0 ? `${messages.length} messages` : ''}
      </p>

      {/* #26: Messages with aria-live off to prevent token-by-token spam */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4" role="log" aria-label="Chat messages" aria-live="off">
        {messages.length === 0 && (
          <div className="text-center py-12">
            <Bot className="w-10 h-10 text-[var(--text-muted)] mx-auto mb-3" />
            <p className="text-[var(--text-secondary)]">Ask me anything about stocks or your portfolio.</p>
            <div className="flex flex-wrap justify-center gap-2 mt-4">
              {['What is NVDA trading at?', 'Compare AAPL vs MSFT', 'Show my portfolio'].map((q) => (
                <button
                  key={q}
                  onClick={() => { setInput(q) }}
                  className="text-xs px-3 py-2 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--accent)] transition-colors focus-ring min-h-[44px]"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}>
            {msg.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full bg-[var(--accent)]/10 flex items-center justify-center shrink-0">
                <Bot className="w-4 h-4 text-[var(--accent)]" />
              </div>
            )}
            <div className="flex flex-col">
              <div className={`max-w-[80%] rounded-xl px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-[var(--accent)] text-white'
                  : 'bg-[var(--surface-elevated)] border border-[var(--border)] text-[var(--text-primary)]'
              }`}>
                {msg.toolCalls && msg.toolCalls.length > 0 && (
                  <div className="mb-2 space-y-1">
                    {msg.toolCalls.map((tc, i) => (
                      <div key={i} className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                        <Wrench className="w-3 h-3" />
                        <span className="font-mono">{tc.name}</span>
                      </div>
                    ))}
                  </div>
                )}
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                {msg.isStreaming && !msg.content && (
                  <span className="inline-flex items-center gap-1">
                    <span className="typing-dot" style={{ animationDelay: '0ms' }} />
                    <span className="typing-dot" style={{ animationDelay: '150ms' }} />
                    <span className="typing-dot" style={{ animationDelay: '300ms' }} />
                  </span>
                )}
              </div>
              <span className={`text-[10px] text-[var(--text-muted)] mt-1 ${
                msg.role === 'user' ? 'text-right' : 'ml-0'
              }`}>
                {formatRelativeTime(extractTimestamp(msg.id))}
              </span>
            </div>
            {msg.role === 'user' && (
              <div className="w-7 h-7 rounded-full bg-[var(--surface-elevated)] border border-[var(--border)] flex items-center justify-center shrink-0">
                <User className="w-4 h-4 text-[var(--text-secondary)]" />
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input with stop control */}
      <div className="border-t border-[var(--border)] pt-4">
        {/* #26: Stop generating button */}
        {isStreaming && (
          <button
            onClick={stopStreaming}
            className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] mb-2 focus-ring rounded px-2 py-1 min-h-[32px]"
          >
            <Square className="w-3 h-3" />
            Stop generating
          </button>
        )}
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about stocks, portfolio, or market conditions..."
            className="flex-1 resize-none border border-[var(--border)] bg-[var(--surface)] rounded-lg px-4 py-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)] focus:border-transparent transition-shadow min-h-[48px] max-h-40"
            rows={1}
            disabled={isStreaming}
            aria-label="Chat message input"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isStreaming}
            className="min-w-[44px] min-h-[44px] flex items-center justify-center rounded-lg bg-[var(--accent)] hover:bg-[var(--accent)]/90 disabled:opacity-50 disabled:cursor-not-allowed text-white transition-colors focus-ring active:scale-[0.98]"
            aria-label="Send message"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
