'use client'

import Link from 'next/link'
import { ArrowRight } from 'lucide-react'
import { getBudgets, listGoals } from '@/lib/api'
import { apiKeys, useApi } from '@/lib/hooks/useApi'
import { formatCurrency } from '@/lib/utils/currency'
import { todayUtcDateKey } from '@/lib/utils/dates'
import { currentMonthKey, spendingCategoryLabel } from '@/lib/utils/spending'

export function GoalsCard() {
  const month = currentMonthKey(todayUtcDateKey())
  const budgetsQuery = useApi(apiKeys.budgets(month), token => getBudgets(token, month))
  const goalsQuery = useApi(apiKeys.goals, token => listGoals(token))
  const budgets = budgetsQuery.data?.budgets ?? []
  const flagged = budgets.filter(budget => budget.over || budget.near)
  const closest = (goalsQuery.data ?? [])
    .filter(goal => goal.status !== 'reached')
    .sort((a, b) => b.percent - a.percent)[0]

  return (
    <section aria-label="Goals and budgets" className="rounded-2xl bg-card p-5 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-foreground">Goals and budgets</h2>
        <Link href="/goals" className="inline-flex min-h-11 items-center gap-1 text-xs font-medium text-primary">
          Open <ArrowRight className="h-3.5 w-3.5" />
        </Link>
      </div>
      {budgets.length > 0 ? (
        <p className="text-sm text-muted-foreground">
          {flagged.length === 0
            ? 'All budgets on track'
            : flagged.map(budget => `${spendingCategoryLabel(budget.category)} ${budget.over ? 'is over' : 'is close to'} its limit`).join(' · ')}
        </p>
      ) : null}
      {closest ? (
        <p className="mt-1 text-sm text-muted-foreground">
          {closest.name}: {formatCurrency(closest.saved, closest.currency)} of {formatCurrency(closest.target_amount, closest.currency)}
        </p>
      ) : null}
      {budgets.length === 0 && !closest ? (
        <p className="text-sm text-muted-foreground">Set a budget or start saving for a goal.</p>
      ) : null}
    </section>
  )
}
