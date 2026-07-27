import { useState, useRef, useEffect, type KeyboardEvent } from 'react'
import { Send, Bot, User, Loader2, Wrench } from 'lucide-react'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  toolCalls?: { name: string; args: Record<string, unknown> }[]
  isStreaming?: boolean
}

import { API_BASE, authParam } from '../api/config'

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const threadId = useRef(`chat-${Date.now()}`)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const sendMessage = () => {
    const text = input.trim()
    if (!text || isStreaming) return

    const userMsg: ChatMessage = { id: `user-${Date.now()}`, role: 'user', content: text }
    const assistantMsg: ChatMessage = { id: `asst-${Date.now()}`, role: 'assistant', content: '', isStreaming: true, toolCalls: [] }

    setMessages((prev) => [...prev, userMsg, assistantMsg])
    setInput('')
    setIsStreaming(true)

    const auth = authParam()
    const url = `${API_BASE}/api/chat/stream?message=${encodeURIComponent(text)}&thread_id=${threadId.current}${auth ? '&' + auth : ''}`
    const es = new EventSource(url)

    es.addEventListener('llm_token', (e) => {
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
    })

    es.onerror = () => {
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
    }
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-6 flex flex-col h-[calc(100vh-8rem)]">
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">Chat</h1>
        <p className="text-sm text-[var(--text-muted)]">
          Ask questions about stocks, portfolios, or market conditions.
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 && (
          <div className="text-center py-12">
            <Bot className="w-10 h-10 text-[var(--text-muted)] mx-auto mb-3" />
            <p className="text-[var(--text-secondary)]">Ask me anything about stocks or your portfolio.</p>
            <div className="flex flex-wrap justify-center gap-2 mt-4">
              {['What is NVDA trading at?', 'Compare AAPL vs MSFT', 'Show my portfolio'].map((q) => (
                <button
                  key={q}
                  onClick={() => { setInput(q); }}
                  className="text-xs px-3 py-1.5 rounded-lg bg-[var(--surface)] border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--accent)] transition-colors focus-ring"
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
                <Loader2 className="w-4 h-4 animate-spin text-[var(--text-muted)]" />
              )}
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

      {/* Input */}
      <div className="border-t border-[var(--border)] pt-4">
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about stocks, portfolio, or market conditions..."
            className="flex-1 resize-none border border-[var(--border)] bg-[var(--surface)] rounded-lg px-4 py-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)] focus:border-transparent transition-shadow"
            rows={1}
            disabled={isStreaming}
            aria-label="Chat message input"
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || isStreaming}
            className="bg-[var(--accent)] hover:bg-[var(--accent)]/90 disabled:opacity-50 disabled:cursor-not-allowed text-white p-3 rounded-lg transition-colors focus-ring"
            aria-label="Send message"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
