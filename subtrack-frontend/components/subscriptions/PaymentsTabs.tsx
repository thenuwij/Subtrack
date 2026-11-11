'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { History, Inbox, ListChecks, PiggyBank } from 'lucide-react'
import { getDetected } from '@/lib/api'
import { apiKeys, useApi } from '@/lib/hooks/useApi'

const TABS = [
  { href: '/subscriptions', label: 'Upcoming', hint: 'Everything you pay for', icon: ListChecks },
  { href: '/subscriptions/paid', label: 'Paid', hint: 'Paid, overdue and bills', icon: History },
  { href: '/review', label: 'Inbox', hint: 'Found in your email', icon: Inbox },
  { href: '/subscriptions/save', label: 'Save', hint: 'Cheaper options and price rises', icon: PiggyBank },
]

/** The four Payments views, shown at the top of each so none is missed. */
export function PaymentsTabs() {
  const pathname = usePathname()
  const detected = useApi(apiKeys.detected('pending'), token => getDetected(token, 'pending'))
  const pendingCount = detected.data?.length ?? 0
  return (
    <nav aria-label="Payments views" className="grid grid-cols-4 gap-2 rounded-2xl border border-border bg-card p-1.5 shadow-sm">
      {TABS.map(({ href, label, hint, icon: Icon }) => {
        const active = pathname === href
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? 'page' : undefined}
            className={`flex min-h-12 flex-col items-center justify-center gap-1 rounded-xl px-1 py-2 text-center sm:flex-row sm:justify-start sm:gap-2.5 sm:px-3 sm:text-left transition-colors ${
              active
                ? 'bg-gradient-to-br from-primary/25 to-primary/5 text-foreground ring-1 ring-primary/40'
                : 'text-foreground hover:bg-muted'
            }`}
          >
            <Icon className={`h-5 w-5 shrink-0 ${active ? 'text-primary' : 'text-muted-foreground'}`} aria-hidden="true" />
            <span className="min-w-0">
              <span className="flex items-center gap-1.5 text-sm font-semibold">
                <span className="truncate">{label}</span>
                {href === '/review' && pendingCount > 0 ? <span className="rounded-md bg-primary/10 px-1.5 py-0.5 text-[11px] tabular-nums text-primary">{pendingCount}<span className="sr-only"> waiting for review</span></span> : null}
              </span>
              <span className="hidden truncate text-xs text-muted-foreground sm:block">{hint}</span>
            </span>
          </Link>
        )
      })}
    </nav>
  )
}
