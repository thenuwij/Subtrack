'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { History, ListChecks, PiggyBank } from 'lucide-react'

const TABS = [
  { href: '/subscriptions', label: 'Tracked', hint: 'Everything you pay for', icon: ListChecks },
  { href: '/subscriptions/paid', label: 'History', hint: 'Paid, overdue and bills', icon: History },
  { href: '/subscriptions/save', label: 'Ways to save', hint: 'Cheaper options and price rises', icon: PiggyBank },
]

/** The three Payments views, shown at the top of each so none is missed. */
export function PaymentsTabs() {
  const pathname = usePathname()
  return (
    <nav aria-label="Payments views" className="grid grid-cols-3 gap-2 rounded-2xl border border-border bg-card p-1.5 shadow-sm">
      {TABS.map(({ href, label, hint, icon: Icon }) => {
        const active = pathname === href
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? 'page' : undefined}
            className={`flex min-h-12 items-center gap-2.5 rounded-xl px-3 py-2 transition-colors ${
              active
                ? 'bg-gradient-to-br from-primary/25 to-primary/5 text-foreground ring-1 ring-primary/40'
                : 'text-foreground hover:bg-muted'
            }`}
          >
            <Icon className={`h-5 w-5 shrink-0 ${active ? 'text-primary' : 'text-muted-foreground'}`} aria-hidden="true" />
            <span className="min-w-0">
              <span className="block truncate text-sm font-semibold">{label}</span>
              <span className="hidden truncate text-xs text-muted-foreground sm:block">{hint}</span>
            </span>
          </Link>
        )
      })}
    </nav>
  )
}
