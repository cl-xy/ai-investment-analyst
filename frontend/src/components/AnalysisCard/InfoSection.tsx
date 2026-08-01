import type { ReactNode } from 'react'
import Markdown from '../Markdown'

interface SectionProps {
  icon: ReactNode
  title: string
  content: string
  fallback?: string
}

export default function InfoSection({ icon, title, content, fallback = 'No data available.' }: SectionProps) {
  const text = content?.trim()
  return (
    <div>
      <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2 flex items-center gap-1">
        {icon} {title}
      </h3>
      {text ? (
        <Markdown>{text}</Markdown>
      ) : (
        <p className="text-sm text-[var(--text-secondary)] leading-relaxed">{fallback}</p>
      )}
    </div>
  )
}
