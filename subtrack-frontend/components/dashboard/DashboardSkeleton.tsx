function Bar({ className = '' }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-muted ${className}`} />
}

export function DashboardSkeleton() {
  return (
    <div className="page-shell space-y-8" aria-busy="true" role="status">
      <span className="sr-only">Loading your overview</span>
      <div className="space-y-3"><Bar className="h-3 w-36" /><Bar className="h-10 w-64 max-w-full" /><Bar className="h-4 w-80 max-w-full" /></div>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        {[0, 1].map(index => <div key={index} className="min-h-72 space-y-6 rounded-3xl bg-card p-6 shadow-sm sm:p-8"><Bar className="h-4 w-32" /><Bar className="h-14 w-52 max-w-full" /><Bar className="h-4 w-full" /><Bar className="h-10 w-40" /></div>)}
      </div>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        {[0, 1].map(index => <div key={index} className="space-y-5 rounded-2xl bg-card p-6 shadow-sm"><Bar className="h-5 w-40" />{[0, 1, 2].map(row => <div key={row} className="flex items-center gap-3"><Bar className="h-9 w-9" /><Bar className="h-4 flex-1" /><Bar className="h-4 w-16" /></div>)}</div>)}
      </div>
    </div>
  )
}
