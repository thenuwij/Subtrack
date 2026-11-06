const EXAMPLE_COMMITMENTS = [
  { name: 'Rent', amount: '$400.00' },
  { name: 'Phone plan', amount: '$35.00' },
  { name: 'Netflix', amount: '$22.99' },
]

/** Desktop-only panel that shows what Subtrack does before someone signs in. */
export function AuthPreviewPanel() {
  return (
    <aside className="hidden flex-col justify-center bg-muted/40 px-12 py-16 lg:flex xl:px-20">
      <div className="max-w-md">
        <h2 className="text-3xl font-semibold tracking-tight text-foreground">
          Know what you can spend until payday.
        </h2>
        <p className="mt-3 text-base text-muted-foreground">
          Subtrack finds your bills and subscriptions in Gmail, subtracts what&apos;s due
          before your next pay, and tells you what&apos;s safe to spend each day.
        </p>

        <figure className="mt-10 rounded-2xl bg-card p-6 shadow-sm" aria-label="Example safe-to-spend card">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-muted-foreground">Safe to spend</p>
            <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">Example</span>
          </div>
          <p className="mt-2 text-5xl font-semibold tracking-tight tabular-nums text-foreground">
            $43.55
            <span className="ml-2 text-lg font-medium tracking-normal text-muted-foreground">a day</span>
          </p>
          <p className="mt-2 text-sm text-muted-foreground">$392.01 until payday in 9 days</p>
          <div className="mt-5 border-t border-border pt-3">
            {EXAMPLE_COMMITMENTS.map(row => (
              <div key={row.name} className="flex justify-between py-1.5 text-sm">
                <span className="text-muted-foreground">{row.name}</span>
                <span className="font-medium tabular-nums text-foreground">{row.amount}</span>
              </div>
            ))}
          </div>
        </figure>
      </div>
    </aside>
  )
}
