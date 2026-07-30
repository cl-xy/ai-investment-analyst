import { Search } from 'lucide-react'

interface Props {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  'aria-label': string
  size?: 'sm' | 'xs'
  className?: string
}

export default function SearchInput({ value, onChange, placeholder = 'Search...', 'aria-label': ariaLabel, size = 'sm', className = '' }: Props) {
  const textSize = size === 'xs' ? 'text-xs' : 'text-sm'
  const iconLeft = size === 'xs' ? 'left-2.5' : 'left-3'
  const inputPl = size === 'xs' ? 'pl-8' : 'pl-9'

  return (
    <div className={`relative ${className}`}>
      <Search aria-hidden="true" className={`pointer-events-none absolute ${iconLeft} top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--text-muted)]`} />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={ariaLabel}
        className={`w-full ${textSize} border border-[var(--border)] bg-[var(--surface)] rounded-lg ${inputPl} pr-3 py-2 text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)] transition-shadow`}
      />
    </div>
  )
}
