'use client'

import { useMemo, useState } from 'react'
import { CheckCircle2, Circle, CircleAlert } from 'lucide-react'
import { toast } from 'sonner'
import { decidePayment, getPaidHistory, sortCharge, updateBill } from '@/lib/api'
import { getAccessToken } from '@/lib/auth/session'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { formatCurrency } from '@/lib/utils/currency'
import { formatStoredDate } from '@/lib/utils/dates'
import { BrandLogo } from '@/components/shared/BrandLogo'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PaymentsTabs } from '@/components/subscriptions/PaymentsTabs'
import type { PaidBill, PaidHistory, PaidPayment } from '@/types'

function shortDate(value: string) {
  return formatStoredDate(value, { day: 'numeric', month: 'short' })
}

function monthLabel(date: string) {
  return formatStoredDate(`${date.slice(0, 7)}-01`, { month: 'long', year: 'numeric' })
}

function rowNote(row: PaidPayment) {
  if (row.manual === 'paid') return row.paid_amount ? 'You entered what you paid' : 'You marked this paid'
  if (row.status === 'skipped') return 'You said this didn’t happen'
  if (row.kind === 'late_fee') return 'Late fee'
  if (row.kind === 'extra') return 'Extra charge'
  if (row.kind === 'above_plan') return 'Charged above your plan'
  return row.status === 'confirmed' ? 'Receipt in Gmail' : 'Expected, no receipt seen'
}

const OWING = new Set<PaidBill['status']>(['overdue', 'part_paid', 'due'])

const BILL_STATUS: Record<PaidBill['status'], { label: string; className: string }> = {
  carried: { label: 'Carried into next bill', className: 'bg-muted text-muted-foreground' },
  paid: { label: 'Paid', className: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' },
  credit: { label: 'Paid, in credit', className: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' },
  part_paid: { label: 'Part paid', className: 'bg-amber-500/10 text-amber-700 dark:text-amber-300' },
  overdue: { label: 'Overdue', className: 'bg-destructive/10 text-destructive' },
  due: { label: 'Not paid yet', className: 'bg-muted text-muted-foreground' },
  unknown: { label: 'Amount unknown', className: 'bg-muted text-muted-foreground' },
}

async function withToken<T>(run: (token: string) => Promise<T>) {
  const token = await getAccessToken()
  if (!token) throw new Error('Your session has expired.')
  return run(token)
}

function BillRow({ bill, onChanged, onDecide }: { bill: PaidBill; onChanged: () => void; onDecide: Decide }) {
  const [due, setDue] = useState('')
  const [saving, setSaving] = useState(false)
  const status = BILL_STATUS[bill.status]

  async function saveDue() {
    if (!due) return
    setSaving(true)
    try {
      await withToken(token => updateBill(token, bill.id, { due_on: due }))
      onChanged()
    } catch (error) {
      toast.error(errorMessage(error, 'Could not save the due date.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <li className="py-2.5">
      <div className="flex min-h-11 items-center gap-3">
        {['paid', 'credit', 'carried'].includes(bill.status)
          ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" aria-label="Paid" />
          : bill.status === 'overdue' || bill.status === 'part_paid'
            ? <CircleAlert className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-label="Owing" />
            : <Circle className="h-4 w-4 shrink-0 text-muted-foreground" aria-label="Not paid yet" />}
        <BrandLogo name={bill.name} category={bill.category} className="h-8 w-8" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-medium text-foreground">{bill.name}</span>
          <span className="block truncate text-[13px] text-muted-foreground">
            Bill {shortDate(bill.issued_on)}
            {bill.due_on ? ` · due ${shortDate(bill.due_on)}` : ''}
            {bill.status === 'part_paid' && bill.owing ? ` · ${formatCurrency(bill.owing, bill.currency)} still owing` : ''}
            {bill.status === 'overdue' && bill.owing ? ` · ${formatCurrency(bill.owing, bill.currency)} owing` : ''}
            {bill.paid_on ? ` · paid ${shortDate(bill.paid_on)}` : ''}
            {bill.late_fee ? ` · includes ${formatCurrency(bill.late_fee, bill.currency)} late fee` : ''}
          </span>
        </span>
        <span className="shrink-0 text-right">
          <span className="block text-[15px] font-semibold tabular-nums text-foreground">
            {bill.amount !== null ? formatCurrency(bill.amount, bill.currency) : '—'}
          </span>
          <span className={`mt-0.5 inline-block rounded-full px-2 py-0.5 text-[11px] font-medium ${status.className}`}>
            {status.label}
          </span>
        </span>
      </div>
      {bill.target ? <DecisionButtons target={bill.target} manual={bill.manual} amount={bill.owing || bill.amount || undefined} currency={bill.currency} bill onDecide={onDecide} /> : null}
      {!bill.due_on ? (
        <div className="mt-2 flex flex-wrap items-center gap-2 pl-[3.25rem]">
          <span className="text-[13px] text-muted-foreground">The email didn&apos;t say when this is due.</span>
          <Input type="date" value={due} onChange={event => setDue(event.target.value)}
            className="h-9 w-auto" aria-label={`Due date for ${bill.name} bill`} />
          <Button size="sm" variant="outline" disabled={!due || saving} onClick={() => void saveDue()}>
            {saving ? 'Saving…' : 'Add due date'}
          </Button>
        </div>
      ) : null}
    </li>
  )
}

export default function PaidPage() {
  const query = useApi<PaidHistory>(apiKeys.paid(3), token => getPaidHistory(token, 3))
  const [busy, setBusy] = useState<string | null>(null)
  const owing = useMemo(
    () => (query.data?.bills ?? []).filter(bill => OWING.has(bill.status)),
    [query.data],
  )
  const months = useMemo(() => {
    const groups = new Map<string, { payments: PaidPayment[]; bills: PaidBill[] }>()
    const group = (key: string) => {
      if (!groups.has(key)) groups.set(key, { payments: [], bills: [] })
      return groups.get(key)!
    }
    for (const row of query.data?.payments ?? []) group(row.date.slice(0, 7)).payments.push(row)
    for (const bill of query.data?.bills ?? []) {
      if (!OWING.has(bill.status)) group((bill.due_on ?? bill.issued_on).slice(0, 7)).bills.push(bill)
    }
    return [...groups.entries()].sort(([a], [b]) => b.localeCompare(a))
  }, [query.data])
  const base = query.data?.base_currency ?? 'AUD'
  const refresh = () => void query.mutate()

  // Show the answer straight away, then save it and reload the real figures.
  async function decide(target: string, decision: 'paid' | 'skipped' | 'undo', amount?: number) {
    const manual = decision === 'undo' ? null : decision
    void query.mutate(current => current && {
      ...current,
      payments: current.payments.map(row => row.target !== target ? row : {
        ...row,
        manual,
        paid_amount: amount ?? null,
        amount: amount ?? row.amount,
        status: decision === 'paid' ? 'confirmed' : decision === 'skipped' ? 'skipped' : row.status,
      }),
      bills: current.bills.map(bill => bill.target !== target ? bill : {
        ...bill,
        manual,
        status: decision !== 'paid' ? bill.status
          : amount !== undefined && bill.amount !== null && amount < bill.amount - 0.01 ? 'part_paid' : 'paid',
      }),
    }, { revalidate: false })
    try {
      await withToken(token => decidePayment(token, target, decision, amount))
    } catch (error) {
      toast.error(errorMessage(error, 'Could not save your answer.'))
    } finally {
      refresh()
    }
  }

  async function sort(row: PaidPayment, kind: 'late_fee' | 'not_fee') {
    const key = `${row.subscription_id}-${row.date}`
    setBusy(key)
    try {
      await withToken(token => sortCharge(token, {
        subscription_id: row.subscription_id, date: row.date, amount: row.amount, kind,
      }))
      toast.success(kind === 'late_fee' ? 'Counted as a late fee' : 'Marked as not a fee')
      refresh()
    } catch (error) {
      toast.error(errorMessage(error, 'Could not save that.'))
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl space-y-7 px-5 py-8 sm:px-8 sm:py-10 lg:px-10">
      <PaymentsTabs />
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow mb-2">Your payment record</p><h1 className="page-heading">Payment history</h1>
          <p className="mt-1 text-sm text-muted-foreground">Receipts, bills and expected payments from the last 3 months.</p>
        </div>
      </div>

      {query.data && (query.data.late_fees_total > 0 || query.data.above_plan_total > 0) ? (
        <section className="grid gap-4 rounded-2xl border border-amber-500/25 bg-amber-500/5 p-5 sm:grid-cols-2 sm:p-6">
          <div>
            <p className="text-[13px] font-medium text-amber-700 dark:text-amber-300">Lost to late fees</p>
            <p className="mt-1 text-3xl font-semibold tracking-tight tabular-nums text-foreground">
              {formatCurrency(query.data.late_fees_total, base)}
            </p>
            <p className="mt-1 text-[13px] text-muted-foreground">From bills that list a fee, and fees you&apos;ve confirmed.</p>
          </div>
          {query.data.above_plan_total > 0 ? (
            <div>
              <p className="text-[13px] font-medium text-muted-foreground">Charged above your plan</p>
              <p className="mt-1 text-3xl font-semibold tracking-tight tabular-nums text-foreground">
                {formatCurrency(query.data.above_plan_total, base)}
              </p>
              <p className="mt-1 text-[13px] text-muted-foreground">Not sorted yet. Mark each one below as a late fee or not.</p>
            </div>
          ) : null}
        </section>
      ) : null}

      {query.error && !query.data ? (
        <section className="flex items-center justify-between gap-3 rounded-2xl bg-card p-5 shadow-sm sm:p-6">
          <p className="text-sm text-muted-foreground">{errorMessage(query.error, 'Could not load your paid history.')}</p>
          <Button size="sm" variant="outline" onClick={refresh}>Try again</Button>
        </section>
      ) : !query.data ? (
        <section className="h-48 animate-pulse rounded-2xl bg-card shadow-sm" aria-label="Loading paid history" />
      ) : (
        <>
          {owing.length > 0 ? (
            <section className="rounded-2xl bg-card p-5 shadow-sm sm:p-6">
              <h2 className="text-[17px] font-semibold text-foreground">Still to pay</h2>
              <ul className="mt-3 divide-y divide-border">
                {owing.map(bill => <BillRow key={bill.id} bill={bill} onChanged={refresh} onDecide={decide} />)}
              </ul>
            </section>
          ) : null}

          <div className="flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" aria-hidden="true" /> Confirmed by a receipt or you
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Circle className="h-4 w-4" aria-hidden="true" /> Expected from the schedule
            </span>
          </div>

          {months.length === 0 ? (
            <section className="rounded-2xl bg-card p-6 text-center shadow-sm">
              <p className="text-[15px] font-medium text-foreground">Nothing paid yet in the last 3 months</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Payments show here once their due dates pass, and are confirmed when a receipt arrives in Gmail.
              </p>
            </section>
          ) : months.map(([key, { payments: rows, bills }]) => {
            const total = rows.filter(row => row.status !== 'unsorted' && row.status !== 'skipped').reduce((sum, row) => sum + (row.amount_in_base ?? 0), 0)
              + bills.filter(bill => bill.currency === base).reduce((sum, bill) => sum + bill.paid, 0)
            const confirmed = rows.filter(row => row.status === 'confirmed').length
              + bills.filter(bill => bill.status !== 'due' && bill.status !== 'unknown').length
            return (
              <section key={key} className="rounded-2xl bg-card p-5 shadow-sm sm:p-6">
                <div className="flex items-baseline justify-between gap-4">
                  <h2 className="text-[17px] font-semibold text-foreground">{monthLabel(`${key}-01`)}</h2>
                  <p className="text-sm text-muted-foreground tabular-nums">
                    <span className="font-semibold text-foreground">{formatCurrency(total, base)}</span>
                    {' · '}{confirmed} confirmed
                  </p>
                </div>
                <ul className="mt-3 divide-y divide-border">
                  {bills.map(bill => <BillRow key={bill.id} bill={bill} onChanged={refresh} onDecide={decide} />)}
                  {rows.map((row, index) => (
                    <li key={`${row.subscription_id}-${row.date}-${row.kind}-${index}`} className="py-2.5">
                      <div className={`flex min-h-11 items-center gap-3 ${row.status === 'expected' ? 'opacity-70' : ''}`}>
                        {row.status === 'confirmed'
                          ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" aria-label="Confirmed" />
                          : row.status === 'unsorted'
                            ? <CircleAlert className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-label="Needs sorting" />
                            : <Circle className="h-4 w-4 shrink-0 text-muted-foreground" aria-label={row.status === 'skipped' ? 'Skipped' : 'Expected'} />}
                        <BrandLogo name={row.name} category={row.category} className="h-8 w-8" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[15px] font-medium text-foreground">{row.name}</span>
                          <span className="block truncate text-[13px] text-muted-foreground">
                            {formatStoredDate(row.date, { weekday: 'short', day: 'numeric', month: 'short' })} · {rowNote(row)}
                          </span>
                        </span>
                        <span className={`shrink-0 text-[15px] font-semibold tabular-nums ${
                          row.status === 'skipped' ? 'line-through text-muted-foreground' : row.kind === 'late_fee' || row.kind === 'above_plan' ? 'text-amber-700 dark:text-amber-300' : 'text-foreground'
                        }`}>
                          {row.status === 'expected' ? '≈ ' : row.kind === 'above_plan' ? '+' : ''}
                          {formatCurrency(row.amount, row.currency)}
                        </span>
                      </div>
                      {row.target ? <DecisionButtons target={row.target} manual={row.manual} amount={row.amount} currency={row.currency} onDecide={decide} /> : null}
                      {row.kind === 'above_plan' ? (
                        <div className="mt-1.5 flex flex-wrap items-center gap-2 pl-[3.25rem]">
                          <span className="text-[13px] text-muted-foreground">Was this extra a late fee?</span>
                          <Button size="sm" variant="outline" disabled={busy !== null}
                            onClick={() => void sort(row, 'late_fee')}>Late fee</Button>
                          <Button size="sm" variant="ghost" disabled={busy !== null}
                            onClick={() => void sort(row, 'not_fee')}>Not a fee</Button>
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </section>
            )
          })}
        </>
      )}
    </div>
  )
}

type Decide = (target: string, decision: 'paid' | 'skipped' | 'undo', amount?: number) => Promise<void>

function DecisionButtons({ target, manual, amount, currency, bill = false, onDecide }: {
  target: string
  manual?: string | null
  amount?: number
  currency?: string
  bill?: boolean
  onDecide: Decide
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const value = Number(draft)
  const valid = draft.trim() !== '' && Number.isFinite(value) && value > 0

  function openEditor() {
    setDraft(amount ? amount.toFixed(2) : '')
    setEditing(true)
  }

  if (editing) {
    return (
      <form
        className="mt-2 flex flex-wrap items-center gap-2 pl-[3.25rem]"
        onSubmit={event => {
          event.preventDefault()
          if (!valid) return
          setEditing(false)
          void onDecide(target, 'paid', Math.round(value * 100) / 100)
        }}
      >
        <label className="text-[13px] text-muted-foreground" htmlFor={`paid-${target}`}>
          You paid{currency ? ` (${currency})` : ''}
        </label>
        <Input
          id={`paid-${target}`}
          autoFocus
          inputMode="decimal"
          value={draft}
          onChange={event => setDraft(event.target.value)}
          onKeyDown={event => { if (event.key === 'Escape') setEditing(false) }}
          className="h-9 w-28"
        />
        <Button size="sm" type="submit" disabled={!valid}>Save</Button>
        <Button size="sm" type="button" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
      </form>
    )
  }

  return (
    <div className="mt-2 flex flex-wrap gap-2 pl-[3.25rem]">
      {manual ? (
        <>
          {manual === 'paid' ? (
            <Button size="sm" variant="outline" onClick={openEditor}>Change amount</Button>
          ) : null}
          <Button size="sm" variant="ghost" onClick={() => void onDecide(target, 'undo')}>Undo your answer</Button>
        </>
      ) : (
        <>
          <Button size="sm" variant="outline" onClick={() => void onDecide(target, 'paid')}>Paid</Button>
          <Button size="sm" variant="outline" onClick={openEditor}>Paid a different amount</Button>
          {!bill ? <Button size="sm" variant="ghost" onClick={() => void onDecide(target, 'skipped')}>Didn&apos;t happen</Button> : null}
        </>
      )}
    </div>
  )
}
