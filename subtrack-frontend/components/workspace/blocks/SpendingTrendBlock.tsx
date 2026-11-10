import type { SpendingTrendData } from '@/types'
import { formatCurrency } from '@/lib/utils/currency'
import { monthLabel, spendingCategoryLabel } from '@/lib/utils/spending'
import { BlockFrame, EmptyLine, QuietNote } from './shared'

export function SpendingTrendBlock({ title, data }: { title: string; data: SpendingTrendData }) {
  const base = data.base_currency
  const peak = Math.max(0, ...data.months.map(month => month.logged_expenses + month.tracked_payments))
  const anyUnconverted = data.months.some(month => month.has_unconverted)
  return (
    <BlockFrame title={title}>
      {data.months.length === 0 ? <EmptyLine>No spending to show yet.</EmptyLine> : (
        <ul className="space-y-3">
          {data.months.map(month => {
            const total = month.logged_expenses + month.tracked_payments
            return (
              <li key={month.month}>
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="font-medium">{monthLabel(month.month)}</span>
                  <span className="tabular-nums text-muted-foreground">{formatCurrency(total, base)}</span>
                </div>
                <div className="mt-1.5 flex h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                  <div className="h-full bg-primary" style={{ width: `${peak > 0 ? (month.logged_expenses / peak) * 100 : 0}%` }} />
                  <div className="h-full bg-primary/50" style={{ width: `${peak > 0 ? (month.tracked_payments / peak) * 100 : 0}%` }} />
                </div>
                <p className="mt-1 text-xs text-muted-foreground tabular-nums">
                  Logged {formatCurrency(month.logged_expenses, base)} · Payments {formatCurrency(month.tracked_payments, base)}
                </p>
              </li>
            )
          })}
        </ul>
      )}
      {data.category ? <QuietNote>Only {spendingCategoryLabel(data.category)}.</QuietNote> : null}
      {anyUnconverted ? <QuietNote>Some amounts in other currencies aren&rsquo;t included yet.</QuietNote> : null}
    </BlockFrame>
  )
}
