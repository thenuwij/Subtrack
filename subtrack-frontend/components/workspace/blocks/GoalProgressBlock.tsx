import type { Goal } from '@/types'
import { formatCurrency } from '@/lib/utils/currency'
import { goalStatusLine } from '@/lib/utils/goals'
import { Bar, BlockFrame, EmptyLine, QuietNote, plural } from './shared'

export function GoalProgressBlock({ title, goals, missingCount }: { title: string; goals: Goal[]; missingCount: number }) {
  return (
    <BlockFrame title={title}>
      {goals.length === 0 ? <EmptyLine>No goals to show here.</EmptyLine> : (
        <ul className="space-y-4">
          {goals.map(goal => (
            <li key={goal.id}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="truncate font-medium">{goal.name}</span>
                <span className="shrink-0 tabular-nums text-muted-foreground">
                  {formatCurrency(goal.saved, goal.currency)} of {formatCurrency(goal.target_amount, goal.currency)}
                </span>
              </div>
              <Bar percent={goal.percent} className="bg-primary" />
              <p className="mt-1.5 text-xs text-muted-foreground">{goalStatusLine(goal)}</p>
            </li>
          ))}
        </ul>
      )}
      {missingCount > 0 ? (
        <QuietNote>{missingCount} {plural(missingCount, 'goal you picked was', 'goals you picked were')} deleted.</QuietNote>
      ) : null}
    </BlockFrame>
  )
}
