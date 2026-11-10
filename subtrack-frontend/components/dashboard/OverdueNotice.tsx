'use client'

import Link from 'next/link'
import { CircleAlert } from 'lucide-react'
import type { SafeToSpend } from '@/types'
import { getSafeToSpend } from '@/lib/api'
import { apiKeys, useApi } from '@/lib/hooks/useApi'
import { formatCurrency } from '@/lib/utils/currency'
import { formatStoredDate } from '@/lib/utils/dates'

/** Payments that fell due and aren't paid: owed now, and taken off safe to spend until marked paid. */
export function OverdueNotice() {
  const query = useApi<SafeToSpend>(apiKeys.safeToSpend, getSafeToSpend)
  const overdue = (query.data?.commitments ?? []).filter(item => item.overdue)
  if (overdue.length === 0) return null
  const currency = query.data?.base_currency ?? 'AUD'

  return (
    <section aria-labelledby="overdue-heading" className="rounded-2xl border border-amber-500/30 bg-amber-500/5 p-4 sm:p-5">
      <h2 id="overdue-heading" className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <CircleAlert className="h-4 w-4 text-amber-600 dark:text-amber-400" aria-hidden="true" />
        {overdue.length === 1 ? '1 payment is overdue' : `${overdue.length} payments are overdue`}
      </h2>
      <p className="mt-1 text-xs text-muted-foreground">They&apos;re counted as owed in safe to spend until you mark them paid.</p>
      <ul className="mt-3 space-y-2">
        {overdue.map(item => (
          <li key={`${item.id}-${item.due_at}`} className="flex items-center justify-between gap-3 text-sm">
            <span className="min-w-0 truncate">
              {item.name} · since {formatStoredDate(item.due_at, { day: 'numeric', month: 'short' })}
            </span>
            <span className="flex shrink-0 items-center gap-3">
              <span className="font-medium tabular-nums">{formatCurrency(item.amount, currency)}</span>
              <Link href="/subscriptions/paid" className="rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/20">
                Mark paid
              </Link>
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
