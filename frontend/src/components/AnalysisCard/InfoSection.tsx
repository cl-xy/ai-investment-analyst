interface SectionProps {
  icon: string
  title: string
  content: string
  fallback?: string
}

export default function InfoSection({ icon, title, content, fallback = 'No data available.' }: SectionProps) {
  const text = content?.trim()
  return (
    <div>
      <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wide mb-2">
        {icon} {title}
      </h3>
      <p className="text-sm text-[var(--text-secondary)] leading-relaxed whitespace-pre-line">
        {text || fallback}
      </p>
    </div>
  )
}
