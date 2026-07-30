import { SkeletonLine, SkeletonBlock } from './Skeleton'

export function AnalysisSkeleton() {
  return (
    <div role="status" className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <span className="sr-only">Loading</span>
      {/* Header bar */}
      <div className="flex items-center gap-3" aria-hidden="true">
        <SkeletonLine width="w-8" height="h-8" delay={0} />
        <SkeletonLine width="w-48" height="h-6" delay={150} />
      </div>
      {/* Event cards */}
      <SkeletonBlock width="w-full" height="h-24" delay={300} />
      <SkeletonBlock width="w-full" height="h-24" delay={450} />
      <SkeletonBlock width="w-full" height="h-24" delay={600} />
    </div>
  )
}

export function DashboardSkeleton() {
  return (
    <div role="status" className="max-w-6xl mx-auto px-4 py-8 space-y-6">
      <span className="sr-only">Loading</span>
      {/* Stat row */}
      <div className="grid grid-cols-3 gap-4" aria-hidden="true">
        <SkeletonBlock width="w-full" height="h-20" delay={0} />
        <SkeletonBlock width="w-full" height="h-20" delay={150} />
        <SkeletonBlock width="w-full" height="h-20" delay={300} />
      </div>
      {/* Chart area */}
      <SkeletonBlock width="w-full" height="h-64" delay={450} />
    </div>
  )
}

export function DefaultSkeleton() {
  return (
    <div role="status" className="max-w-4xl mx-auto px-4 py-8 space-y-6">
      <span className="sr-only">Loading</span>
      {/* Title */}
      <SkeletonLine width="w-1/3" height="h-7" delay={0} />
      {/* Paragraph lines */}
      <div className="space-y-3" aria-hidden="true">
        <SkeletonLine width="w-full" height="h-4" delay={150} />
        <SkeletonLine width="w-5/6" height="h-4" delay={300} />
        <SkeletonLine width="w-4/5" height="h-4" delay={450} />
      </div>
      {/* Second paragraph */}
      <div className="space-y-3" aria-hidden="true">
        <SkeletonLine width="w-full" height="h-4" delay={600} />
        <SkeletonLine width="w-2/3" height="h-4" delay={750} />
      </div>
      {/* Card grid */}
      <div className="grid grid-cols-2 gap-4" aria-hidden="true">
        <SkeletonBlock width="w-full" height="h-32" delay={900} />
        <SkeletonBlock width="w-full" height="h-32" delay={1050} />
      </div>
    </div>
  )
}
