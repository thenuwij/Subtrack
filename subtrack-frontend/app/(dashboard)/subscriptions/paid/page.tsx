'use client'

import { useMemo, useState } from 'react'
import { CheckCircle2, Circle, CircleAlert } from 'lucide-react'
import { toast } from 'sonner'
import { getPaidHistory, sortCharge, updateBill } from '@/lib/api'
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
  if (row.kind === 'late_fee') return 'Late fee'
  if (row.kind === 'extra') return 'Extra charge'
  if (row.kind === 'above_plan') return 'Charged above your plan'
  return row.status === 'confirmed' ? 'Receipt in Gmail' : 'Expected, no receipt seen'
}

const BILL_STATUS: Record<PaidBill['status'], { label: string; className: string }> = {
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

function BillRow({ bill, onChanged }: { bill: PaidBill; onChanged: () => void }) {
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
    <li className="py-3">
      <div className="flex min-h-11 items-center gap-3">
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
      {!bill.due_on ? (
        <div className="mt-2 flex flex-wrap items-center gap-2 pl-11">
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
  const months = useMemo(() => {
    const groups = new Map<string, PaidPayment[]>()
    for (const row of query.data?.payments ?? []) {
      const key = row.date.slice(0, 7)
      groups.set(key, [...(groups.get(key) ?? []), row])
    }
    return [...groups.entries()]
  }, [query.data])
  const base = query.data?.base_currency ?? 'AUD'
  const refresh = () => void query.mutate()

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
    <div className="mx-auto w-full max-w-4xl space-y-7 px-5 py-8 sm:px-8 sm:py-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow mb-2">Your payment record</p><h1 className="page-heading">Payment history</h1>
          <p className="mt-1 text-sm text-muted-foreground">Receipts, bills and expected payments from the last 3 months.</p>
        </div>
        <PaymentsTabs />
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
          {query.data.bills.length > 0 ? (
            <section className="rounded-2xl bg-card p-5 shadow-sm sm:p-6">
              <h2 className="text-[17px] font-semibold text-foreground">Bills</h2>
              <p className="mt-0.5 text-[13px] text-muted-foreground">From the bills in your email. Receipts mark them paid.</p>
              <ul className="mt-2 divide-y divide-border">
                {query.data.bills.map(bill => <BillRow key={bill.id} bill={bill} onChanged={refresh} />)}
              </ul>
            </section>
          ) : null}

          <div className="flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" aria-hidden="true" /> Confirmed by a receipt
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
          ) : months.map(([key, rows]) => {
            const total = rows.filter(row => row.status !== 'unsorted').reduce((sum, row) => sum + (row.amount_in_base ?? 0), 0)
            const confirmed = rows.filter(row => row.status === 'confirmed').length
            return (
              <section key={key} className="rounded-2xl bg-card p-5 shadow-sm sm:p-6">
                <div className="flex items-baseline justify-between gap-4">
                  <h2 className="text-[17px] font-semibold text-foreground">{monthLabel(rows[0].date)}</h2>
                  <p className="text-sm text-muted-foreground tabular-nums">
                    <span className="font-semibold text-foreground">{formatCurrency(total, base)}</span>
                    {' · '}{confirmed} confirmed
                  </p>
                </div>
                <ul className="mt-3 divide-y divide-border">
                  {rows.map((row, index) => (
                    <li key={`${row.subscription_id}-${row.date}-${row.kind}-${index}`} className="py-2.5">
                      <div className={`flex min-h-11 items-center gap-3 ${row.status === 'expected' ? 'opacity-70' : ''}`}>
                        {row.status === 'confirmed'
                          ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" aria-label="Confirmed" />
                          : row.status === 'unsorted'
                            ? <CircleAlert className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-label="Needs sorting" />
                            : <Circle className="h-4 w-4 shrink-0 text-muted-foreground" aria-label="Expected" />}
                        <BrandLogo name={row.name} category={row.category} className="h-8 w-8" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[15px] font-medium text-foreground">{row.name}</span>
                          <span className="block truncate text-[13px] text-muted-foreground">
                            {formatStoredDate(row.date, { weekday: 'short', day: 'numeric', month: 'short' })} · {rowNote(row)}
                          </span>
                        </span>
                        <span className={`shrink-0 text-[15px] font-semibold tabular-nums ${
                          row.kind === 'late_fee' || row.kind === 'above_plan' ? 'text-amber-700 dark:text-amber-300' : 'text-foreground'
                        }`}>
                          {row.status === 'expected' ? '≈ ' : row.kind === 'above_plan' ? '+' : ''}
                          {formatCurrency(row.amount, row.currency)}
                        </span>
                      </div>
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
