'use client'

import { useState } from 'react'
import { ArrowDownRight, ArrowUpRight, ChevronDown, ChevronUp, Minus } from 'lucide-react'
import { getSubscriptionChanges } from '@/lib/api'
import type { SubscriptionChange } from '@/types'
import { useCurrency } from '@/lib/context/currency'
import { formatCurrency } from '@/lib/utils/currency'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { Button } from '@/components/ui/button'

const COLLAPSED_COUNT = 4

function formatDate(date: string) {
  return new Date(date).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
}

/** Price changes, additions and removals over the last 30 days. Hidden when there are none. */
export function RecentChanges({ bare = false }: { bare?: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const { baseCurrency, canConvert, convertAmount, ratesLoading } = useCurrency()
  const changesQuery = useApi<SubscriptionChange[]>(
    apiKeys.subscriptionChanges(30), token => getSubscriptionChanges(token, 30),
  )
  const changes = changesQuery.data ?? []
  const error = errorMessage(changesQuery.error, 'Could not load recent changes.')

  if (changesQuery.isLoading || (!error && changes.length === 0)) return null

  return (
    <section className={bare ? 'px-5 py-4' : 'rounded-2xl bg-card p-5 shadow-sm sm:p-6'}>
      <h2 className="text-[15px] font-medium text-foreground">What changed</h2>
      <p className="mt-0.5 text-xs text-muted-foreground">Last 30 days</p>

      {error ? (
        <div className="mt-4 flex flex-col gap-3 rounded-xl border border-amber-500/25 bg-amber-500/5 p-4">
          <div>
            <p className="text-sm font-medium text-foreground">Recent changes are unavailable</p>
            <p className="mt-0.5 text-xs text-muted-foreground">We won&apos;t guess that nothing changed.</p>
          </div>
          <Button size="sm" variant="outline" className="self-start" onClick={() => void changesQuery.mutate()}>
            Try again
          </Button>
        </div>
      ) : (
        <ul id="payments-changes-list" className="mt-3 divide-y divide-border">
          {(expanded ? changes : changes.slice(0, COLLAPSED_COUNT)).map(change => {
            const conversionAvailable = canConvert(change.currency)
            const delta = conversionAvailable
              ? convertAmount(change.delta, change.currency) ?? 0
              : change.delta
            const tone = delta > 0 ? 'var(--increase)' : delta < 0 ? 'var(--decrease)' : undefined
            const detail = !conversionAvailable
              ? `${change.currency} conversion unavailable`
              : change.kind === 'added'
                ? 'Added'
                : change.kind === 'removed'
                  ? 'Removed'
                  : `${formatCurrency(convertAmount(change.old_monthly ?? 0, change.currency) ?? 0, baseCurrency)} → ${formatCurrency(convertAmount(change.new_monthly ?? 0, change.currency) ?? 0, baseCurrency)}`

            return (
              <li key={change.id} className="flex items-center gap-2.5 py-2.5">
                <div
                  className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg"
                  style={{
                    backgroundColor: tone ? `color-mix(in oklch, ${tone} 12%, transparent)` : 'var(--muted)',
                    color: tone ?? 'var(--muted-foreground)',
                  }}
                >
                  {delta > 0 ? <ArrowUpRight className="h-3.5 w-3.5" />
                    : delta < 0 ? <ArrowDownRight className="h-3.5 w-3.5" />
                      : <Minus className="h-3.5 w-3.5" />}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-foreground">{change.name}</p>
                  <p className="truncate text-xs text-muted-foreground">{detail} · {formatDate(change.changed_at)}</p>
                </div>
                <p className="shrink-0 text-xs font-semibold tabular-nums" style={{ color: tone ?? 'var(--muted-foreground)' }}>
                  {delta > 0 ? '+' : delta < 0 ? '−' : ''}
                  {formatCurrency(Math.abs(delta), conversionAvailable ? baseCurrency : change.currency)}/mo
                </p>
              </li>
            )
          })}
          {changes.length > COLLAPSED_COUNT && (
            <li>
              <button
                type="button"
                aria-expanded={expanded}
                aria-controls="payments-changes-list"
                onClick={() => setExpanded(value => !value)}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                {expanded
                  ? <><ChevronUp className="h-4 w-4" /> Show less</>
                  : <><ChevronDown className="h-4 w-4" /> Show {changes.length - COLLAPSED_COUNT} more</>}
              </button>
            </li>
          )}
        </ul>
      )}
      {!ratesLoading && changes.some(change => change.currency !== baseCurrency) ? (
        <p className="mt-3 text-xs leading-5 text-muted-foreground">Foreign amounts use today&apos;s exchange rates.</p>
      ) : null}
    </section>
  )
}
