import type { SharedCostsData } from '@/types'
import { formatCurrency } from '@/lib/utils/currency'
import { BlockFrame, EmptyLine } from './shared'

export function SharedCostsBlock({ title, data }: { title: string; data: SharedCostsData }) {
  return (
    <BlockFrame title={title}>
      {data.people.length === 0 ? <EmptyLine>No people added yet.</EmptyLine> : (
        <>
          <p className="text-sm text-muted-foreground">
            Total <span className="tabular-nums">{formatCurrency(data.total, data.currency)}</span>
          </p>
          <ul className="mt-2 divide-y divide-border">
            {data.people.map(person => (
              <li key={person.name} className="py-2 text-sm">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="font-medium">{person.name}</span>
                  <span className="tabular-nums">
                    {person.status === 'settled'
                      ? 'Settled'
                      : person.status === 'owes'
                        ? `Owes ${formatCurrency(Math.abs(person.net), data.currency)}`
                        : `Is owed ${formatCurrency(person.net, data.currency)}`}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground tabular-nums">
                  Paid {formatCurrency(person.paid, data.currency)} · Share {formatCurrency(person.share, data.currency)}
                </p>
              </li>
            ))}
          </ul>
        </>
      )}
    </BlockFrame>
  )
}
