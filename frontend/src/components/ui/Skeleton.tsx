interface SkeletonLineProps {
  width?: string
  height?: string
  delay?: number
}

export function SkeletonLine({ width = 'w-3/4', height = 'h-4', delay }: SkeletonLineProps) {
  return (
    <div
      className={`${width} ${height} rounded animate-shimmer skeleton-delayed`}
      style={delay ? { animationDelay: `${delay}ms` } : undefined}
      aria-hidden="true"
    />
  )
}

interface SkeletonCircleProps {
  size?: string
  delay?: number
}

export function SkeletonCircle({ size = 'w-10 h-10', delay }: SkeletonCircleProps) {
  return (
    <div
      className={`${size} rounded-full animate-shimmer skeleton-delayed`}
      style={delay ? { animationDelay: `${delay}ms` } : undefined}
      aria-hidden="true"
    />
  )
}

interface SkeletonBlockProps {
  width?: string
  height?: string
  delay?: number
}

export function SkeletonBlock({ width = 'w-full', height = 'h-32', delay }: SkeletonBlockProps) {
  return (
    <div
      className={`${width} ${height} rounded-lg animate-shimmer skeleton-delayed`}
      style={delay ? { animationDelay: `${delay}ms` } : undefined}
      aria-hidden="true"
    />
  )
}
