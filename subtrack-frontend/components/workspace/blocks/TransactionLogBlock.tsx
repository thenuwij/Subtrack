import type { TransactionLogData } from '@/types'
import { formatCurrency } from '@/lib/utils/currency'
import { formatStoredDate } from '@/lib/utils/dates'
import { spendingCategoryLabel } from '@/lib/utils/spending'
import { BlockFrame, EmptyLine, QuietNote, plural } from './shared'

export function TransactionLogBlock({ title, data }: { title: string; data: TransactionLogData }) {
  const base = data.base_currency
  return (
    <BlockFrame title={title}>
      {data.entries.length === 0 ? <EmptyLine>No entries in this period.</EmptyLine> : (
        <>
          <p className="text-sm text-muted-foreground">
            Spent <span className="tabular-nums">{formatCurrency(data.expenses, base)}</span> · Earned <span className="tabular-nums">{formatCurrency(data.income, base)}</span>
          </p>
          <ul className="mt-2 divide-y divide-border">
            {data.entries.map(entry => (
              <li key={entry.id} className="flex items-baseline justify-between gap-3 py-2 text-sm">
                <span className="min-w-0">
                  <span className="block truncate font-medium">{entry.name}</span>
                  <span className="block text-xs text-muted-foreground">
                    {formatStoredDate(entry.occurred_on, { day: 'numeric', month: 'short' })} · {spendingCategoryLabel(entry.category)}
                  </span>
                </span>
                <span className="shrink-0 tabular-nums">
                  {entry.kind === 'income' ? '+' : ''}{formatCurrency(entry.amount, entry.currency)}
                </span>
              </li>
            ))}
          </ul>
          {data.entry_count > data.entries.length ? (
            <QuietNote>Showing the latest {data.entries.length} of {data.entry_count}.</QuietNote>
          ) : null}
        </>
      )}
      {data.unconverted_count > 0 ? (
        <QuietNote>
          {data.unconverted_count} {plural(data.unconverted_count, 'amount in another currency isn’t', 'amounts in other currencies aren’t')} in the totals yet.
        </QuietNote>
      ) : null}
    </BlockFrame>
  )
}
