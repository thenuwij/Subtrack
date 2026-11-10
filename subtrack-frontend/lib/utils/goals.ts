import { formatCurrency } from '@/lib/utils/currency'
import { formatStoredDate } from '@/lib/utils/dates'
import type { BudgetStatus, Goal } from '@/types'

export type BudgetTone = 'calm' | 'near' | 'over'

/** The tone comes from the server's flags; spent is never recalculated here. */
export function budgetTone(budget: BudgetStatus): BudgetTone {
  if (budget.over) return 'over'
  if (budget.near) return 'near'
  return 'calm'
}

/** "$120 left of $400", "$20 over", or just the spend when the limit can't be converted. */
export function budgetLine(budget: BudgetStatus, base: string): string {
  const limit = budget.limit_in_base
  if (limit === null || budget.left === null) {
    return `${formatCurrency(budget.monthly_limit, budget.currency)} a month, not converted yet`
  }
  if (budget.over) return `${formatCurrency(Math.abs(budget.left), base)} over ${formatCurrency(limit, base)}`
  return `${formatCurrency(budget.left, base)} left of ${formatCurrency(limit, base)}`
}

/** A plain sentence about where the goal stands, using the server's figures. */
export function goalStatusLine(goal: Goal): string {
  const date = goal.target_date
    ? formatStoredDate(goal.target_date, { day: 'numeric', month: 'short' })
    : ''
  switch (goal.status) {
    case 'reached':
      return 'Reached — nice work'
    case 'on_the_way':
      return goal.needed_per_week !== null
        ? `${formatCurrency(goal.needed_per_week, goal.currency)} a week to reach it by ${date}`
        : `Aiming for ${date}`
    case 'due_today':
      return `Due today — ${formatCurrency(goal.remaining, goal.currency)} to go`
    case 'target_date_passed':
      return 'Target date has passed'
    default:
      return `${formatCurrency(goal.remaining, goal.currency)} to go`
  }
}
