'use client'

import Link from 'next/link'
import { ArrowRight } from 'lucide-react'
import { getTransactionSummary } from '@/lib/api'
import { apiKeys, useApi } from '@/lib/hooks/useApi'
import { todayUtcDateKey } from '@/lib/utils/dates'
import { currentMonthKey } from '@/lib/utils/spending'
import { formatCurrency } from '@/lib/utils/currency'

export function ThisMonthCard() {
  const month = currentMonthKey(todayUtcDateKey())
  const { data } = useApi(apiKeys.transactionSummary(month), token => getTransactionSummary(token, month))
  const figures = [
    { label: 'In', value: data?.income },
    { label: 'Out', value: data?.expenses },
    { label: 'Left over', value: data?.net },
  ]

  return (
    <section aria-label="This month" className="rounded-2xl bg-card p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-foreground">This month</h2>
        <Link href="/spending" className="inline-flex min-h-11 items-center gap-1 text-xs font-medium text-primary">
          Spending <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
      <dl className="mt-1 grid grid-cols-3 gap-3">
        {figures.map(({ label, value }) => (
          <div key={label}>
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="mt-0.5 text-base font-semibold tabular-nums text-foreground">
              {data && value !== undefined ? formatCurrency(value, data.base_currency) : '—'}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
