'use client'

import { useMemo } from 'react'
import { CheckCircle2, Circle } from 'lucide-react'
import { getPaidHistory } from '@/lib/api'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { formatCurrency } from '@/lib/utils/currency'
import { formatStoredDate } from '@/lib/utils/dates'
import { BrandLogo } from '@/components/shared/BrandLogo'
import { Button } from '@/components/ui/button'
import { PaymentsTabs } from '@/components/subscriptions/PaymentsTabs'
import type { PaidHistory, PaidPayment } from '@/types'

function monthLabel(date: string) {
  return formatStoredDate(`${date.slice(0, 7)}-01`, { month: 'long', year: 'numeric' })
}

function rowNote(row: PaidPayment) {
  if (row.kind === 'late_fee') return 'Late fee'
  if (row.kind === 'extra') return 'Extra charge'
  return row.status === 'confirmed' ? 'Receipt in Gmail' : 'Expected, no receipt seen'
}

export default function PaidPage() {
  const query = useApi<PaidHistory>(apiKeys.paid(3), token => getPaidHistory(token, 3))
  const months = useMemo(() => {
    const groups = new Map<string, PaidPayment[]>()
    for (const row of query.data?.payments ?? []) {
      const key = row.date.slice(0, 7)
      groups.set(key, [...(groups.get(key) ?? []), row])
    }
    return [...groups.entries()]
  }, [query.data])
  const base = query.data?.base_currency ?? 'AUD'

  return (
    <div className="mx-auto w-full max-w-3xl space-y-6 px-4 py-6 sm:px-6 sm:py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Paid</h1>
          <p className="mt-1 text-sm text-muted-foreground">The last 3 months, newest first.</p>
        </div>
        <PaymentsTabs />
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" aria-hidden="true" /> Confirmed by a receipt
        </span>
        <span className="inline-flex items-center gap-1.5">
          <Circle className="h-4 w-4" aria-hidden="true" /> Expected from the schedule
        </span>
      </div>

      {query.error && !query.data ? (
        <section className="flex items-center justify-between gap-3 rounded-2xl bg-card p-5 shadow-sm sm:p-6">
          <p className="text-sm text-muted-foreground">{errorMessage(query.error, 'Could not load your paid history.')}</p>
          <Button size="sm" variant="outline" onClick={() => void query.mutate()}>Try again</Button>
        </section>
      ) : !query.data ? (
        <section className="h-48 animate-pulse rounded-2xl bg-card shadow-sm" aria-label="Loading paid history" />
      ) : months.length === 0 ? (
        <section className="rounded-2xl bg-card p-6 text-center shadow-sm">
          <p className="text-[15px] font-medium text-foreground">Nothing paid yet in the last 3 months</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Payments show here once their due dates pass, and are confirmed when a receipt arrives in Gmail.
          </p>
        </section>
      ) : (
        months.map(([key, rows]) => {
          const total = rows.reduce((sum, row) => sum + (row.amount_in_base ?? 0), 0)
          const confirmed = rows.filter(row => row.status === 'confirmed').length
          return (
            <section key={key} className="rounded-2xl bg-card p-5 shadow-sm sm:p-6">
              <div className="flex items-baseline justify-between gap-4">
                <h2 className="text-[17px] font-semibold text-foreground">{monthLabel(rows[0].date)}</h2>
                <p className="text-sm text-muted-foreground tabular-nums">
                  <span className="font-semibold text-foreground">{formatCurrency(total, base)}</span>
                  {' · '}{confirmed} of {rows.length} confirmed
                </p>
              </div>
              <ul className="mt-3 divide-y divide-border">
                {rows.map((row, index) => (
                  <li key={`${row.subscription_id}-${row.date}-${row.kind}-${index}`}
                    className={`flex min-h-11 items-center gap-3 py-2.5 ${row.status === 'expected' ? 'opacity-70' : ''}`}>
                    {row.status === 'confirmed'
                      ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" aria-label="Confirmed" />
                      : <Circle className="h-4 w-4 shrink-0 text-muted-foreground" aria-label="Expected" />}
                    <BrandLogo name={row.name} category={row.category} className="h-8 w-8" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[15px] font-medium text-foreground">{row.name}</span>
                      <span className="block truncate text-[13px] text-muted-foreground">
                        {formatStoredDate(row.date, { weekday: 'short', day: 'numeric', month: 'short' })} · {rowNote(row)}
                      </span>
                    </span>
                    <span className="shrink-0 text-[15px] font-semibold tabular-nums text-foreground">
                      {row.status === 'expected' ? '≈ ' : ''}{formatCurrency(row.amount, row.currency)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )
        })
      )}
    </div>
  )
}
