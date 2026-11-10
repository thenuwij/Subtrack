'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'
import type { PayCycle, PayCycles as PayCyclesData } from '@/types'
import { getPayCycles } from '@/lib/api'
import { apiKeys, useApi } from '@/lib/hooks/useApi'
import { formatCurrency } from '@/lib/utils/currency'
import { formatStoredDate } from '@/lib/utils/dates'

const RANGES = [{ count: 3, label: 'Last 3 pays' }, { count: 6, label: 'Last 6 pays' }, { count: 12, label: 'Last 12 pays' }]
type Result = 'all' | 'over' | 'under'
const selectClass = 'h-9 rounded-md border border-input bg-card px-3 text-sm'

function day(value: string) {
  return formatStoredDate(value, { day: 'numeric', month: 'short' })
}

function lastDay(end: string) {
  const date = new Date(`${end}T12:00:00Z`)
  date.setUTCDate(date.getUTCDate() - 1)
  return day(date.toISOString().slice(0, 10))
}

function overBudget(cycle: PayCycle) {
  return cycle.pots.some(pot => (pot.over ?? 0) > 0)
}

/** How each pay went: budgets planned against spent, savings and other spends. */
export function PayCycles() {
  const [count, setCount] = useState(6)
  const [pot, setPot] = useState('all')
  const [result, setResult] = useState<Result>('all')
  const query = useApi<PayCyclesData>(apiKeys.payCycles(count), token => getPayCycles(token, count))
  const data = query.data
  const currency = data?.base_currency ?? 'AUD'
  const potNames = useMemo(() => [...new Set(data?.cycles.flatMap(c => c.pots.map(p => p.name)) ?? [])], [data])

  const cycles = (data?.cycles ?? [])
    .filter(cycle => result === 'all' || (result === 'over') === overBudget(cycle))
    .map(cycle => pot === 'all' ? cycle : {
      ...cycle,
      pots: cycle.pots.filter(item => item.name === pot),
      savings: [],
      spends: cycle.spends.filter(spend => spend.pot === pot),
    })

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-10 sm:px-6">
      <div>
        <Link href="/dashboard" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />Home</Link>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight">Past pay cycles</h1>
        <p className="mt-2 text-muted-foreground">How each pay went: what you planned for your budgets, what you spent and what you saved.</p>
      </div>

      <div className="flex flex-wrap gap-2" aria-label="Filters">
        <select aria-label="Range" value={count} onChange={event => setCount(Number(event.target.value))} className={selectClass}>
          {RANGES.map(range => <option key={range.count} value={range.count}>{range.label}</option>)}
        </select>
        <select aria-label="Budget" value={pot} onChange={event => setPot(event.target.value)} className={selectClass}>
          <option value="all">All budgets</option>
          {potNames.map(name => <option key={name} value={name}>{name}</option>)}
        </select>
        <select aria-label="Result" value={result} onChange={event => setResult(event.target.value as Result)} className={selectClass}>
          <option value="all">Any result</option>
          <option value="under">Stayed within budgets</option>
          <option value="over">Went over a budget</option>
        </select>
      </div>

      {!data ? <div className="h-40 animate-pulse rounded-2xl bg-card" aria-label="Loading" /> : null}
      {data && data.cycles.length === 0 ? (
        <p className="rounded-2xl bg-card p-6 text-sm text-muted-foreground">Set up your payday on Home to see your pay cycles.</p>
      ) : null}
      {data && data.cycles.length > 0 && cycles.length === 0 ? (
        <p className="rounded-2xl bg-card p-6 text-sm text-muted-foreground">No pay cycles match these filters.</p>
      ) : null}

      {cycles.map(cycle => (
        <section key={cycle.start} className="rounded-2xl bg-card p-5 shadow-sm sm:p-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-[17px] font-semibold">{day(cycle.start)} – {lastDay(cycle.end)}</h2>
            <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${cycle.current ? 'bg-primary/10 text-primary' : overBudget(cycle) ? 'bg-amber-500/15 text-amber-700 dark:text-amber-300' : 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300'}`}>
              {cycle.current ? 'This pay, so far' : overBudget(cycle) ? 'Went over a budget' : 'Stayed within budgets'}
            </span>
          </div>

          {cycle.pots.length > 0 ? (
            <ul className="mt-4 space-y-3">
              {cycle.pots.map(item => {
                const share = item.planned ? Math.min(1, item.spent / item.planned) : 0
                const over = (item.over ?? 0) > 0
                return (
                  <li key={item.id}>
                    <div className="flex justify-between gap-3 text-sm">
                      <span className="font-medium">{item.name}</span>
                      <span className={`tabular-nums ${over ? 'text-amber-700 dark:text-amber-300' : ''}`}>
                        {formatCurrency(item.spent, currency)} of {item.planned != null ? formatCurrency(item.planned, currency) : '?'}
                        {over ? ` · ${formatCurrency(item.over ?? 0, currency)} over` : ''}
                      </span>
                    </div>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                      <div className={`h-full rounded-full ${over ? 'bg-amber-500' : 'bg-primary'}`} style={{ width: `${share * 100}%` }} />
                    </div>
                  </li>
                )
              })}
            </ul>
          ) : null}

          <dl className="mt-4 grid grid-cols-2 gap-3 border-t border-border pt-4 text-sm">
            {pot === 'all' ? (
              <>
                <div><dt className="text-muted-foreground">Saved</dt><dd className="font-semibold tabular-nums">{formatCurrency(cycle.saved, currency)}</dd></div>
                <div><dt className="text-muted-foreground">Other logged spends</dt><dd className="font-semibold tabular-nums">{formatCurrency(cycle.other_spent, currency)}</dd></div>
              </>
            ) : null}
          </dl>

          {cycle.spends.length > 0 ? (
            <details className="mt-3">
              <summary className="cursor-pointer text-sm text-muted-foreground">{cycle.spends.length} logged spend{cycle.spends.length === 1 ? '' : 's'}</summary>
              <ul className="mt-2 space-y-1 text-sm">
                {cycle.spends.map(spend => (
                  <li key={spend.id} className="flex justify-between gap-3">
                    <span className="truncate text-muted-foreground">{day(spend.occurred_on)} · {spend.name}{spend.pot ? ` · ${spend.pot}` : ''}</span>
                    <span className="tabular-nums">{spend.amount != null ? formatCurrency(spend.amount, currency) : 'No rate'}</span>
                  </li>
                ))}
              </ul>
            </details>
          ) : null}
        </section>
      ))}
      {data && data.cycles.length > 0 ? <p className="text-xs text-muted-foreground">{data.note}</p> : null}
    </div>
  )
}
