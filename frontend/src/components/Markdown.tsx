import ReactMarkdown from 'react-markdown'

interface Props {
  children: string
  className?: string
}

/**
 * Renders LLM-generated markdown content with proper styling.
 * Handles tables, bold, lists, and inline formatting that models often produce.
 */
export default function Markdown({ children, className = '' }: Props) {
  return (
    <ReactMarkdown
      className={`prose-llm ${className}`}
      components={{
        // Strip wrapping <p> for single-paragraph content to avoid extra spacing
        p: ({ children: c }) => (
          <p className="text-sm text-[var(--text-secondary)] leading-relaxed mb-2 last:mb-0">{c}</p>
        ),
        strong: ({ children: c }) => (
          <strong className="font-semibold text-[var(--text-primary)]">{c}</strong>
        ),
        ul: ({ children: c }) => (
          <ul className="space-y-1 mb-2 last:mb-0">{c}</ul>
        ),
        ol: ({ children: c }) => (
          <ol className="space-y-1 mb-2 last:mb-0 list-decimal list-inside">{c}</ol>
        ),
        li: ({ children: c }) => (
          <li className="text-sm text-[var(--text-secondary)] leading-relaxed flex items-start gap-1.5">
            <span className="shrink-0 mt-2 w-1 h-1 rounded-full bg-[var(--text-muted)]" />
            <span>{c}</span>
          </li>
        ),
        table: ({ children: c }) => (
          <div className="overflow-x-auto mb-2 last:mb-0">
            <table className="w-full text-sm border-collapse">{c}</table>
          </div>
        ),
        thead: ({ children: c }) => (
          <thead className="border-b border-[var(--border)]">{c}</thead>
        ),
        th: ({ children: c }) => (
          <th className="text-left text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider px-2 py-1.5">{c}</th>
        ),
        td: ({ children: c }) => (
          <td className="text-sm text-[var(--text-secondary)] px-2 py-1.5 border-b border-[var(--border)]/50">{c}</td>
        ),
        h1: ({ children: c }) => (
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1">{c}</h3>
        ),
        h2: ({ children: c }) => (
          <h3 className="text-sm font-semibold text-[var(--text-primary)] mb-1">{c}</h3>
        ),
        h3: ({ children: c }) => (
          <h4 className="text-xs font-semibold text-[var(--text-primary)] mb-1">{c}</h4>
        ),
        // Don't render images from LLM output
        img: () => null,
        // Code inline
        code: ({ children: c }) => (
          <code className="text-xs font-mono px-1 py-0.5 rounded bg-[var(--surface)] text-[var(--text-secondary)]">{c}</code>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  )
}
