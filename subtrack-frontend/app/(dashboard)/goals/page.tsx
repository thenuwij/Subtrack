'use client'

import { useState } from 'react'
import { ChevronLeft, ChevronRight, PiggyBank, Plus, Target } from 'lucide-react'
import { useSWRConfig } from 'swr'
import { toast } from 'sonner'
import {
  addGoalContribution, createBudget, createGoal, deleteBudget, deleteGoal,
  getBudgets, listGoals, updateBudget, updateGoal,
} from '@/lib/api'
import { getAccessToken } from '@/lib/auth/session'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { formatCurrency } from '@/lib/utils/currency'
import { todayUtcDateKey } from '@/lib/utils/dates'
import { budgetLine, budgetTone, goalStatusLine, type BudgetTone } from '@/lib/utils/goals'
import {
  currentMonthKey, EXPENSE_CATEGORIES, monthLabel, shiftMonth, spendingCategoryLabel,
} from '@/lib/utils/spending'
import type { BudgetStatus, Category, ContributionInput, Currency, Goal } from '@/types'
import { BudgetDialog } from '@/components/goals/BudgetDialog'
import { GoalDialog } from '@/components/goals/GoalDialog'
import { MoneyDialog } from '@/components/goals/MoneyDialog'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

const TONE_BAR: Record<BudgetTone, string> = {
  calm: 'bg-primary',
  near: 'bg-warning',
  over: 'bg-destructive',
}

type Dialog =
  | { kind: 'budget'; budget: BudgetStatus | null }
  | { kind: 'goal'; goal: Goal | null }
  | { kind: 'money'; goal: Goal; mode: 'add' | 'remove' }

function ProgressBar({ percent, className }: { percent: number; className: string }) {
  return (
    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
      <div className={`h-full rounded-full ${className}`} style={{ width: `${Math.min(100, Math.max(2, percent))}%` }} />
    </div>
  )
}

export default function GoalsPage() {
  const { mutate } = useSWRConfig()
  const thisMonth = currentMonthKey(todayUtcDateKey())
  const [month, setMonth] = useState(thisMonth)
  const [dialog, setDialog] = useState<Dialog | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const budgetsQuery = useApi(apiKeys.budgets(month), token => getBudgets(token, month))
  const goalsQuery = useApi(apiKeys.goals, token => listGoals(token))
  const overview = budgetsQuery.data
  const budgets = overview?.budgets ?? []
  const goals = goalsQuery.data ?? []
  const base = overview?.base_currency ?? 'AUD'
  const budgetError = errorMessage(budgetsQuery.error, 'Could not load your budgets.')
  const goalError = errorMessage(goalsQuery.error, 'Could not load your goals.')
  const used = new Set<Category>(budgets.map(budget => budget.category))
  const freeCategories = EXPENSE_CATEGORIES.filter(category => !used.has(category))

  async function refresh() {
    await mutate(key => typeof key === 'string' && (key.startsWith('budgets:') || key === 'goals'))
  }

  async function authToken() {
    const token = await getAccessToken()
    if (!token) throw new Error('Your session has expired. Sign in again.')
    return token
  }

  async function saveBudget(input: { category: Category; monthly_limit: number }) {
    const token = await authToken()
    const editing = dialog?.kind === 'budget' ? dialog.budget : null
    if (editing) {
      await updateBudget(token, editing.id, { monthly_limit: input.monthly_limit })
      toast.success('Budget updated')
    } else {
      await createBudget(token, input)
      toast.success('Budget added')
    }
    setDialog(null)
    await refresh()
  }

  async function removeBudget(id: string) {
    await deleteBudget(await authToken(), id)
    toast.success('Budget removed')
    setDialog(null)
    await refresh()
  }

  async function saveGoal(input: { name: string; target_amount: number; currency: Currency; target_date: string | null }) {
    const token = await authToken()
    const editing = dialog?.kind === 'goal' ? dialog.goal : null
    if (editing) {
      await updateGoal(token, editing.id, {
        name: input.name, target_amount: input.target_amount, target_date: input.target_date,
      })
      toast.success('Goal updated')
    } else {
      await createGoal(token, input)
      toast.success('Goal added')
    }
    setDialog(null)
    await refresh()
  }

  async function saveMoney(input: ContributionInput) {
    if (dialog?.kind !== 'money') return
    await addGoalContribution(await authToken(), dialog.goal.id, input)
    toast.success(dialog.mode === 'add' ? 'Money added' : 'Money taken out')
    setDialog(null)
    await refresh()
  }

  async function archiveGoal(goal: Goal) {
    try {
      await updateGoal(await authToken(), goal.id, { archived: true })
      toast.success('Goal archived')
      await refresh()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not archive this goal.')
    }
  }

  async function removeGoal(id: string) {
    try {
      await deleteGoal(await authToken(), id)
      toast.success('Goal removed')
      await refresh()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not remove this goal.')
    } finally {
      setDeletingId(null)
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-8 sm:px-8 sm:py-10">
      <header>
        <p className="eyebrow mb-2">Goals</p>
        <h1 className="page-heading">Goals and budgets</h1>
      </header>

      <section aria-label="Budgets" className="mt-8">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold">Budgets this month</h2>
          {freeCategories.length > 0 && budgets.length > 0 ? (
            <Button size="sm" variant="outline" onClick={() => setDialog({ kind: 'budget', budget: null })}>
              <Plus className="h-4 w-4" />Add a budget
            </Button>
          ) : null}
        </div>

        <div className="mt-3 flex items-center justify-between rounded-xl bg-card px-1 shadow-sm">
          <Button variant="ghost" size="icon" aria-label="Previous month" onClick={() => setMonth(shiftMonth(month, -1))}><ChevronLeft className="h-4 w-4" /></Button>
          <p className="text-sm font-semibold" aria-live="polite">{monthLabel(month)}</p>
          <Button variant="ghost" size="icon" aria-label="Next month" disabled={month >= thisMonth} onClick={() => setMonth(shiftMonth(month, 1))}><ChevronRight className="h-4 w-4" /></Button>
        </div>

        {budgetError ? (
          <div className="mt-3 flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">{budgetError}</p>
            <Button variant="outline" size="sm" onClick={() => void refresh()}>Try again</Button>
          </div>
        ) : null}

        {budgetsQuery.isLoading ? (
          <div className="mt-3 space-y-2"><Skeleton className="h-16" /><Skeleton className="h-16" /></div>
        ) : budgets.length === 0 && !budgetError ? (
          <div className="mt-3 rounded-2xl bg-card p-8 text-center shadow-sm">
            <PiggyBank className="mx-auto h-6 w-6 text-muted-foreground" />
            <p className="mt-3 text-sm text-muted-foreground">No budgets yet. Set a monthly limit for a category.</p>
            <Button className="mt-4" onClick={() => setDialog({ kind: 'budget', budget: null })}>Add a budget</Button>
            <p className="mt-3 text-xs text-muted-foreground">You can also tell the assistant, like &ldquo;Set a $400 food budget&rdquo;.</p>
          </div>
        ) : (
          <ul className="mt-3 divide-y divide-border overflow-hidden rounded-2xl bg-card shadow-sm">
            {budgets.map(budget => (
              <li key={budget.id}>
                <button type="button" onClick={() => setDialog({ kind: 'budget', budget })}
                  className="block min-h-14 w-full px-4 py-3 text-left hover:bg-muted/40">
                  <span className="flex items-baseline justify-between gap-3 text-sm">
                    <span className="font-medium">{spendingCategoryLabel(budget.category)}</span>
                    <span className="tabular-nums text-muted-foreground">{budgetLine(budget, base)}</span>
                  </span>
                  <ProgressBar percent={(budget.share_used ?? 0) * 100} className={TONE_BAR[budgetTone(budget)]} />
                  {budget.unconverted_count > 0 ? (
                    <span className="mt-1.5 block text-xs text-muted-foreground">
                      {budget.unconverted_count === 1
                        ? "1 amount in another currency isn't included yet."
                        : `${budget.unconverted_count} amounts in other currencies aren't included yet.`}
                    </span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Goals" className="mt-10">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold">Goals</h2>
          {goals.length > 0 ? (
            <Button size="sm" variant="outline" onClick={() => setDialog({ kind: 'goal', goal: null })}>
              <Plus className="h-4 w-4" />New goal
            </Button>
          ) : null}
        </div>

        {goalError ? (
          <div className="mt-3 flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">{goalError}</p>
            <Button variant="outline" size="sm" onClick={() => void refresh()}>Try again</Button>
          </div>
        ) : null}

        {goalsQuery.isLoading ? (
          <div className="mt-3 space-y-2"><Skeleton className="h-28" /><Skeleton className="h-28" /></div>
        ) : goals.length === 0 && !goalError ? (
          <div className="mt-3 rounded-2xl bg-card p-8 text-center shadow-sm">
            <Target className="mx-auto h-6 w-6 text-muted-foreground" />
            <p className="mt-3 text-sm text-muted-foreground">No goals yet. Pick something to save up for.</p>
            <Button className="mt-4" onClick={() => setDialog({ kind: 'goal', goal: null })}>New goal</Button>
            <p className="mt-3 text-xs text-muted-foreground">You can also tell the assistant, like &ldquo;Save $2,000 for a holiday&rdquo;.</p>
          </div>
        ) : (
          <ul className="mt-3 space-y-3">
            {goals.map(goal => (
              <li key={goal.id} className="rounded-2xl bg-card p-4 shadow-sm">
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="truncate text-sm font-semibold">{goal.name}</h3>
                  <p className="shrink-0 text-sm tabular-nums text-muted-foreground">
                    {formatCurrency(goal.saved, goal.currency)} of {formatCurrency(goal.target_amount, goal.currency)}
                  </p>
                </div>
                <ProgressBar percent={goal.percent} className="bg-primary" />
                <p className="mt-2 text-sm text-muted-foreground" aria-live="polite">{goalStatusLine(goal)}</p>

                <div className="mt-3 flex flex-wrap gap-1">
                  <Button size="sm" onClick={() => setDialog({ kind: 'money', goal, mode: 'add' })}>Add money</Button>
                  <Button size="sm" variant="ghost" disabled={goal.saved <= 0}
                    onClick={() => setDialog({ kind: 'money', goal, mode: 'remove' })}>Take money out</Button>
                  <Button size="sm" variant="ghost" onClick={() => setDialog({ kind: 'goal', goal })}>Edit</Button>
                  <Button size="sm" variant="ghost" onClick={() => void archiveGoal(goal)}>Archive</Button>
                  {deletingId === goal.id ? (
                    <span className="flex gap-1">
                      <Button size="sm" variant="destructive" onClick={() => void removeGoal(goal.id)}>Delete</Button>
                      <Button size="sm" variant="ghost" onClick={() => setDeletingId(null)}>Cancel</Button>
                    </span>
                  ) : (
                    <Button size="sm" variant="ghost" aria-label={`Delete ${goal.name}`} onClick={() => setDeletingId(goal.id)}>Delete</Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {dialog?.kind === 'budget' ? (
        <BudgetDialog budget={dialog.budget} freeCategories={freeCategories} currency={base}
          onClose={() => setDialog(null)} onSave={saveBudget} onRemove={removeBudget} />
      ) : null}
      {dialog?.kind === 'goal' ? (
        <GoalDialog goal={dialog.goal} onClose={() => setDialog(null)} onSave={saveGoal} />
      ) : null}
      {dialog?.kind === 'money' ? (
        <MoneyDialog goal={dialog.goal} mode={dialog.mode} onClose={() => setDialog(null)} onSave={saveMoney} />
      ) : null}
    </div>
  )
}
