'use client'

import { useMemo } from 'react'
import Link from 'next/link'
import type { Subscription } from '@/types'
import { useCurrency } from '@/lib/context/currency'
import { formatCurrency } from '@/lib/utils/currency'
import { categoryColor, formatCategory } from '@/lib/utils/categories'
import { contributesToCommitment, yearlyEquivalentNative } from '@/lib/utils/recurrence'
import { useThisMonth } from '@/lib/hooks/useThisMonth'

/** This month's spend per category, as plain rows for the dashboard side panel. */
export function CategorySpend({ subscriptions }: { subscriptions: Subscription[] }) {
  const { baseCurrency, canConvert, convertAmount } = useCurrency()
  const { costOf, monthName } = useThisMonth()

  const totals = useMemo(() => {
    const byCategory = new Map<string, number>()
    for (const subscription of subscriptions) {
      if (!contributesToCommitment(subscription)) continue
      const cost = costOf(subscription)
      if (!cost) continue
      byCategory.set(subscription.category, (byCategory.get(subscription.category) ?? 0) + cost)
    }
    return [...byCategory.entries()]
      .map(([category, total]) => ({ category, total }))
      .sort((a, b) => b.total - a.total)
  }, [subscriptions, costOf])

  const grandTotal = totals.reduce((sum, entry) => sum + entry.total, 0)
  const counted = subscriptions.filter(s => contributesToCommitment(s) && canConvert(s.currency))
  const yearly = counted.reduce(
    (sum, s) => sum + (convertAmount(yearlyEquivalentNative(s), s.currency) ?? 0), 0,
  )
  const excluded = subscriptions.filter(s => contributesToCommitment(s) && !canConvert(s.currency)).length
  if (grandTotal <= 0) return null

  return (
    <section className="px-5 py-4" aria-labelledby="category-spend-heading">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="category-spend-heading" className="text-xs font-medium text-muted-foreground">
          Due in {monthName}
        </h2>
        <Link href="/subscriptions" className="text-xs font-medium text-primary hover:underline">
          Payments
        </Link>
      </div>
      <p className="mt-1 text-3xl font-semibold tracking-tight tabular-nums text-foreground">
        {formatCurrency(grandTotal, baseCurrency)}
      </p>
      <p className="mt-1 text-sm text-muted-foreground tabular-nums">
        {formatCurrency(yearly, baseCurrency)} a year · {counted.length} recurring
        {excluded ? ` · ${excluded} excluded (FX unavailable)` : ''}
      </p>
      <h3 className="mt-5 text-[15px] font-medium text-foreground">By category</h3>
      <ul className="mt-3 space-y-2.5">
        {totals.map(({ category, total }) => (
          <li key={category}>
            <span className="flex items-center justify-between gap-2 text-xs">
              <span className="truncate text-foreground">{formatCategory(category)}</span>
              <span className="shrink-0 tabular-nums text-muted-foreground">{formatCurrency(total, baseCurrency)}</span>
            </span>
            <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-muted">
              <span
                className="block h-full rounded-full"
                style={{ width: `${Math.max((total / grandTotal) * 100, 2)}%`, backgroundColor: categoryColor(category) }}
              />
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}
