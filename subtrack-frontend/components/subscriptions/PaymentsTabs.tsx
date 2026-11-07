'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const TABS = [
  { href: '/subscriptions', label: 'Tracked' },
  { href: '/subscriptions/paid', label: 'History' },
]

/** Switch between your payments and what has already been paid. */
export function PaymentsTabs() {
  const pathname = usePathname()
  return (
    <nav aria-label="Payments views" className="inline-flex rounded-lg bg-muted p-0.5">
      {TABS.map(tab => {
        const active = pathname === tab.href
        return (
          <Link
            key={tab.href}
            href={tab.href}
            aria-current={active ? 'page' : undefined}
            className={`min-h-9 rounded-[7px] px-4 py-1.5 text-sm font-medium transition-colors ${
              active ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {tab.label}
          </Link>
        )
      })}
    </nav>
  )
}
