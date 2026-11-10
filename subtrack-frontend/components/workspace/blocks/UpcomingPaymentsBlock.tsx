import type { UpcomingPaymentsData } from '@/types'
import { formatCurrency } from '@/lib/utils/currency'
import { formatStoredDate } from '@/lib/utils/dates'
import { BlockFrame, EmptyLine, QuietNote, plural } from './shared'

export function UpcomingPaymentsBlock({ title, data, base }: { title: string; data: UpcomingPaymentsData; base: string }) {
  return (
    <BlockFrame title={title}>
      {data.charges.length === 0 ? <EmptyLine>Nothing due in the next {data.days} days.</EmptyLine> : (
        <>
          <ul className="divide-y divide-border">
            {data.charges.map((charge, index) => (
              <li key={`${charge.id}-${charge.due_at}-${index}`} className="flex items-baseline justify-between gap-3 py-2 text-sm">
                <span className="min-w-0">
                  <span className="block truncate font-medium">{charge.name}</span>
                  <span className="block text-xs text-muted-foreground">{formatStoredDate(charge.due_at, { day: 'numeric', month: 'short' })}</span>
                </span>
                <span className="shrink-0 tabular-nums">{formatCurrency(charge.amount, charge.currency)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-sm text-muted-foreground">
            About <span className="tabular-nums">{formatCurrency(data.total_in_base, base)}</span> in the next {data.days} days
          </p>
        </>
      )}
      {data.unconverted_count > 0 ? (
        <QuietNote>
          {data.unconverted_count} {plural(data.unconverted_count, 'charge in another currency isn’t', 'charges in other currencies aren’t')} included in the total yet.
        </QuietNote>
      ) : null}
    </BlockFrame>
  )
}
