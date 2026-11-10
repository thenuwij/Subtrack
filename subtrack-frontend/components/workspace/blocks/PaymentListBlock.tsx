import type { PaymentListData } from '@/types'
import { formatCurrency } from '@/lib/utils/currency'
import { formatCategory } from '@/lib/utils/categories'
import { BlockFrame, EmptyLine, QuietNote, plural } from './shared'

export function PaymentListBlock({ title, data, base }: { title: string; data: PaymentListData; base: string }) {
  return (
    <BlockFrame title={title}>
      {data.payments.length === 0 ? <EmptyLine>No payments to show here.</EmptyLine> : (
        <>
          <ul className="divide-y divide-border">
            {data.payments.map(payment => (
              <li key={payment.id} className="flex items-baseline justify-between gap-3 py-2 text-sm">
                <span className="min-w-0">
                  <span className="block truncate font-medium">{payment.name}</span>
                  <span className="block text-xs text-muted-foreground">{formatCategory(payment.category)} · {payment.cadence_label}</span>
                </span>
                <span className="shrink-0 text-right tabular-nums">
                  {formatCurrency(payment.amount, payment.currency)}
                  {payment.monthly_in_base !== null && payment.currency !== base ? (
                    <span className="block text-xs text-muted-foreground">{formatCurrency(payment.monthly_in_base, base)} a month</span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-sm text-muted-foreground">
            About <span className="tabular-nums">{formatCurrency(data.monthly_total_in_base, base)}</span> a month
          </p>
        </>
      )}
      {data.unconverted_count > 0 ? (
        <QuietNote>
          {data.unconverted_count} {plural(data.unconverted_count, 'payment in another currency isn’t', 'payments in other currencies aren’t')} included in the total yet.
        </QuietNote>
      ) : null}
      {data.missing_count > 0 ? (
        <QuietNote>{data.missing_count} {plural(data.missing_count, 'payment you picked was', 'payments you picked were')} deleted.</QuietNote>
      ) : null}
      {data.inactive_count > 0 ? (
        <QuietNote>{data.inactive_count} {plural(data.inactive_count, 'payment you picked is', 'payments you picked are')} cancelled or ended.</QuietNote>
      ) : null}
    </BlockFrame>
  )
}
