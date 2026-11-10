import type { BudgetStatus, Currency } from '@/types'
import { budgetLine, budgetTone, type BudgetTone } from '@/lib/utils/goals'
import { spendingCategoryLabel } from '@/lib/utils/spending'
import { Bar, BlockFrame, EmptyLine, QuietNote, plural } from './shared'

const TONE_BAR: Record<BudgetTone, string> = {
  calm: 'bg-primary',
  near: 'bg-warning',
  over: 'bg-destructive',
}

export function BudgetBlock({ title, budgets, base }: { title: string; budgets: BudgetStatus[]; base: Currency }) {
  return (
    <BlockFrame title={title}>
      {budgets.length === 0 ? <EmptyLine>No budgets to show here.</EmptyLine> : (
        <ul className="space-y-3">
          {budgets.map(budget => (
            <li key={budget.id}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="font-medium">{spendingCategoryLabel(budget.category)}</span>
                <span className="tabular-nums text-muted-foreground">{budgetLine(budget, base)}</span>
              </div>
              <Bar percent={(budget.share_used ?? 0) * 100} className={TONE_BAR[budgetTone(budget)]} />
              {budget.unconverted_count > 0 ? (
                <QuietNote>
                  {budget.unconverted_count} {plural(budget.unconverted_count, 'amount in another currency isn’t', 'amounts in other currencies aren’t')} included yet.
                </QuietNote>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </BlockFrame>
  )
}
