import { CalendarClock, Mail, MessageCircle } from 'lucide-react'

const EXAMPLE_COMMITMENTS = [
  { name: 'Rent', amount: '$400.00' },
  { name: 'Phone plan', amount: '$35.00' },
  { name: 'Netflix', amount: '$22.99' },
]

const FEATURES = [
  { icon: Mail, text: 'Finds bills and subscriptions in Gmail' },
  { icon: CalendarClock, text: 'Counts what’s due before your next pay' },
  { icon: MessageCircle, text: 'Answers “can I afford it?” in plain words' },
]

/** Desktop-only panel that shows what Subtrack does before someone signs in. */
export function AuthPreviewPanel() {
  return (
    <aside className="relative hidden overflow-hidden bg-gradient-to-br from-blue-600 via-indigo-600 to-violet-700 px-12 py-16 text-white lg:flex lg:flex-col lg:justify-center xl:px-20">
      <div aria-hidden="true" className="pointer-events-none absolute -right-24 -top-24 h-96 w-96 rounded-full bg-sky-400/30 blur-3xl" />
      <div aria-hidden="true" className="pointer-events-none absolute -bottom-32 -left-20 h-96 w-96 rounded-full bg-fuchsia-500/30 blur-3xl" />

      <div className="relative max-w-md">
        <h2 className="text-4xl font-semibold leading-tight tracking-tight">
          Know what you can spend until payday.
        </h2>

        <ul className="mt-6 space-y-3">
          {FEATURES.map(({ icon: Icon, text }) => (
            <li key={text} className="flex items-center gap-3 text-base text-white/90">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/15 ring-1 ring-white/20">
                <Icon className="h-4 w-4" aria-hidden="true" />
              </span>
              {text}
            </li>
          ))}
        </ul>

        <figure
          className="mt-10 rounded-2xl bg-card p-6 text-card-foreground shadow-2xl shadow-indigo-950/40"
          aria-label="Example safe-to-spend card"
        >
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-muted-foreground">Safe to spend</p>
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">Example</span>
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
