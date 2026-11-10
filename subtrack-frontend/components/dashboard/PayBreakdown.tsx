'use client'

import { useState } from 'react'
import type { PayPlan, SetAsidePosition } from '@/types'
import { formatCategory } from '@/lib/utils/categories'
import { formatCurrency } from '@/lib/utils/currency'
import { spendingCategoryLabel } from '@/lib/utils/spending'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'

interface Part { key: string; label: string; detail: string; amount: number }

/** One entry per category (its bills and logged spends together), then each budget by name, largest first. */
function partsOf(plan: PayPlan, budgets: SetAsidePosition[]): Part[] {
  const byCategory = new Map<string, { amount: number; names: string[]; spent: number }>()
  const groupFor = (category: string) => {
    const group = byCategory.get(category) ?? { amount: 0, names: [], spent: 0 }
    byCategory.set(category, group)
    return group
  }
  for (const bill of plan.bill_list) {
    const group = groupFor(bill.category)
    group.amount += bill.amount
    if (!group.names.includes(bill.name)) group.names.push(bill.name)
  }
  for (const spend of plan.spent_by_category ?? []) {
    const group = groupFor(spend.category)
    group.amount += spend.amount
    group.spent += spend.amount
  }
  const parts: Part[] = [...byCategory].map(([category, group]) => ({
    key: `category-${category}`,
    label: group.names.length ? formatCategory(category) : spendingCategoryLabel(category),
    detail: [...group.names, ...(group.spent ? ['logged spends'] : [])].join(', '),
    amount: group.amount,
  }))
  for (const budget of budgets) {
    parts.push({
      key: `budget-${budget.id}`,
      label: budget.name,
      detail: budget.kind === 'save' ? 'Saving' : 'Budget',
      amount: budget.amount,
    })
  }
  if (plan.over_budgets) {
    parts.push({ key: 'over-budgets', label: 'Over budgets', detail: 'Spent past a budget', amount: plan.over_budgets })
  }
  return parts.filter(part => part.amount > 0).sort((a, b) => b.amount - a.amount)
}

function BarRow({ part, whole, currency, emphasis }: { part: Part; whole: number; currency: string; emphasis?: boolean }) {
  const share = whole > 0 ? part.amount / whole : 0
  return (
    <li className="py-3.5">
      <div className="flex items-baseline justify-between gap-4 text-base">
        <span className="flex min-w-0 items-baseline gap-2">
          <span className="shrink-0 font-medium text-foreground">{part.label}</span>
          {part.detail ? <span className="truncate text-xs text-muted-foreground">{part.detail}</span> : null}
        </span>
        <span className="shrink-0 tabular-nums">
          <span className="font-semibold text-foreground">{formatCurrency(part.amount, currency)}</span>
          <span className="ml-2 inline-block w-10 text-right text-xs text-muted-foreground">{Math.round(share * 100)}%</span>
        </span>
      </div>
      <div className="mt-2 h-3 overflow-hidden rounded-full bg-foreground/5" aria-hidden="true">
        <div
          className={`h-full rounded-full ${emphasis ? 'bg-primary' : 'bg-primary/55'}`}
          style={{ width: `${Math.min(share, 1) * 100}%` }}
        />
      </div>
    </li>
  )
}

const PIE_SLOTS = 6

/** At most six slices: the largest parts, the rest folded into "Other", then what's left. */
function sliceParts(parts: Part[], left: number | null): Part[] {
  const room = left != null && left > 0 ? PIE_SLOTS - 1 : PIE_SLOTS
  const named = parts.length > room ? parts.slice(0, room - 1) : parts
  const rest = parts.slice(named.length)
  const slices = [...named]
  if (rest.length) {
    slices.push({
      key: 'other',
      label: 'Other',
      detail: rest.map(part => part.label).join(', '),
      amount: rest.reduce((sum, part) => sum + part.amount, 0),
    })
  }
  if (left != null && left > 0) slices.push({ key: 'left', label: 'Balance', detail: '', amount: left })
  return slices
}

function arcPath(start: number, end: number, outer: number, inner: number) {
  const point = (angle: number, radius: number) =>
    `${100 + radius * Math.cos(angle)} ${100 + radius * Math.sin(angle)}`
  const large = end - start > Math.PI ? 1 : 0
  return [
    `M ${point(start, outer)}`,
    `A ${outer} ${outer} 0 ${large} 1 ${point(end, outer)}`,
    `L ${point(end, inner)}`,
    `A ${inner} ${inner} 0 ${large} 0 ${point(start, inner)}`,
    'Z',
  ].join(' ')
}

function PieView({ slices, whole, currency }: { slices: Part[]; whole: number; currency: string }) {
  const [active, setActive] = useState<number | null>(null)
  const total = slices.reduce((sum, slice) => sum + slice.amount, 0)
  const arcs = slices.map((slice, index) => {
    const before = slices.slice(0, index).reduce((sum, earlier) => sum + earlier.amount, 0)
    const start = -Math.PI / 2 + (before / total) * 2 * Math.PI
    // A lone slice can't be drawn as a 360° arc, so stop just short of it.
    const sweep = Math.min((slice.amount / total) * 2 * Math.PI, 2 * Math.PI - 0.0001)
    return { start, end: start + sweep }
  })
  const focus = active != null ? slices[active] : null

  return (
    <div className="flex flex-col items-center gap-8 sm:flex-row sm:items-center">
      <div className="relative h-60 w-60 shrink-0 sm:h-72 sm:w-72">
        <svg viewBox="0 0 200 200" className="h-full w-full" role="img" aria-label="Pie chart of where this pay goes">
          {slices.map((slice, index) => (
            <path
              key={slice.key}
              d={arcPath(arcs[index].start, arcs[index].end, 96, 60)}
              fill={`var(--pie-${index + 1})`}
              stroke="var(--card)"
              strokeWidth={2}
              opacity={active == null || active === index ? 1 : 0.35}
              onMouseEnter={() => setActive(index)}
              onMouseLeave={() => setActive(null)}
              className="transition-opacity"
            >
              <title>{`${slice.label}: ${formatCurrency(slice.amount, currency)}`}</title>
            </path>
          ))}
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center px-10 text-center">
          <span className="line-clamp-2 text-sm text-muted-foreground">{focus ? focus.label : 'Your pay'}</span>
          <span className="text-2xl font-semibold tabular-nums text-foreground">
            {formatCurrency(focus ? focus.amount : whole, currency)}
          </span>
        </div>
      </div>
      <ul className="w-full min-w-0 space-y-1" aria-label="Pie chart legend">
        {slices.map((slice, index) => (
          <li
            key={slice.key}
            onMouseEnter={() => setActive(index)}
            onMouseLeave={() => setActive(null)}
            className={`flex items-center justify-between gap-3 rounded-md px-3 py-2.5 text-base ${active === index ? 'bg-muted' : ''}`}
          >
            <span className="flex min-w-0 items-center gap-2">
              <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: `var(--pie-${index + 1})` }} aria-hidden="true" />
              <span className="truncate text-foreground">{slice.label}</span>
            </span>
            <span className="shrink-0 tabular-nums">
              <span className="font-semibold text-foreground">{formatCurrency(slice.amount, currency)}</span>
              <span className="ml-2 inline-block w-10 text-right text-xs text-muted-foreground">
                {Math.round((whole > 0 ? slice.amount / whole : 0) * 100)}%
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

type View = 'bars' | 'pie'
const VIEW_KEY = 'subtrack:pay-breakdown-view'

function savedView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === 'pie' ? 'pie' : 'bars'
  } catch {
    return 'bars'
  }
}

export function PayBreakdown({ open, onOpenChange, plan, budgets, currency }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  plan: PayPlan
  budgets: SetAsidePosition[]
  currency: string
}) {
  const [view, setView] = useState<View>(savedView)
  const parts = partsOf(plan, budgets)
  const spoken = plan.bills + plan.set_aside
  // Shares are of your pay when it's known; otherwise of everything listed.
  const whole = plan.pay_amount != null ? plan.pay_amount + (plan.extra_income ?? 0) : spoken
  const left = plan.left

  function choose(next: View) {
    setView(next)
    try {
      localStorage.setItem(VIEW_KEY, next)
    } catch {
      // Storage can be blocked; the choice just isn't remembered.
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-3xl sm:p-8">
        <DialogHeader>
          <DialogTitle>Where this pay goes</DialogTitle>
        </DialogHeader>
        <DialogDescription>
          {plan.pay_amount != null
            ? `Your bills by category and each budget, as a share of your ${formatCurrency(whole, currency)} pay${plan.extra_income ? ' with extra income' : ''}.`
            : 'Your bills by category and each budget. Add your usual pay to see each as a share of it.'}
        </DialogDescription>
        {parts.length > 0 ? (
          <div className="inline-flex self-start rounded-lg bg-muted p-1" role="group" aria-label="Chart type">
            {(['bars', 'pie'] as View[]).map(option => (
              <button
                key={option}
                type="button"
                aria-pressed={view === option}
                onClick={() => choose(option)}
                className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${view === option ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
              >
                {option === 'bars' ? 'Bars' : 'Pie'}
              </button>
            ))}
          </div>
        ) : null}
        {parts.length === 0 ? (
          <p className="text-sm text-muted-foreground">No bills or budgets in this pay yet.</p>
        ) : view === 'pie' ? (
          <PieView slices={sliceParts(parts, left)} whole={whole} currency={currency} />
        ) : (
          <ul className="divide-y divide-border" aria-label="Where this pay goes">
            {parts.map(part => <BarRow key={part.key} part={part} whole={whole} currency={currency} />)}
            {left != null && left > 0 ? (
              <BarRow
                part={{ key: 'left', label: 'Balance', detail: '', amount: left }}
                whole={whole}
                currency={currency}
                emphasis
              />
            ) : null}
          </ul>
        )}
        {left != null && left < 0 ? (
          <p className="rounded-xl bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-200">
            Bills and budgets come to {formatCurrency(Math.abs(left), currency)} more than this pay.
          </p>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
