'use client'

import { type FormEvent, useState } from 'react'
import { useSWRConfig } from 'swr'
import { toast } from 'sonner'
import { getManualDue, markPaymentPaid } from '@/lib/api'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { getAccessToken } from '@/lib/auth/session'
import { formatCurrency } from '@/lib/utils/currency'
import type { ManualDue } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

/** Caches that change once a payment is recorded as a transaction. */
const AFFECTED_KEYS = /^(manual-due|transactions:|transaction-summary:|budgets:)/

function localDateKey(): string {
  return new Date().toLocaleDateString('en-CA')
}

function dueLabel(dateKey: string): string {
  const date = new Date(`${dateKey}T12:00:00`)
  return date.toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short' })
}

/** Payments the user pays themselves that are due soon or overdue and not marked paid. */
export function ToPayList() {
  const due = useApi(apiKeys.manualDue, getManualDue)
  const [selected, setSelected] = useState<ManualDue | null>(null)
  const rows = due.data ?? []
  if (rows.length === 0) return null

  return (
    <section aria-labelledby="to-pay-heading" className="rounded-2xl border border-border bg-card p-4 shadow-sm">
      <h2 id="to-pay-heading" className="mb-3 text-sm font-semibold">To pay</h2>
      <ul className="divide-y divide-border">
        {rows.map(row => (
          <li key={`${row.payment_id}:${row.due_date}`} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
            <span className="min-w-0 text-sm">
              <span className="font-medium">{row.name}</span>
              <span className={row.overdue ? 'text-destructive' : 'text-muted-foreground'}>
                {' · '}{row.overdue ? 'was due' : 'due'} {dueLabel(row.due_date)} · not paid yet
              </span>
              <span className="ml-2 tabular-nums text-muted-foreground">{formatCurrency(row.amount, row.currency)}</span>
            </span>
            <Button size="sm" variant={row.overdue ? 'default' : 'outline'} onClick={() => setSelected(row)}>
              Mark as paid
            </Button>
          </li>
        ))}
      </ul>
      {selected ? <MarkPaidDialog row={selected} onClose={() => setSelected(null)} /> : null}
    </section>
  )
}

function MarkPaidDialog({ row, onClose }: { row: ManualDue; onClose: () => void }) {
  const { mutate } = useSWRConfig()
  const [paidOn, setPaidOn] = useState(localDateKey)
  const [amount, setAmount] = useState(String(row.amount))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const value = Number(amount)
    if (!Number.isFinite(value) || value <= 0) {
      setError('Enter an amount above zero.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const token = await getAccessToken()
      if (!token) throw new Error('Your session has expired. Sign in again.')
      await markPaymentPaid(token, row.payment_id, {
        due_date: row.due_date,
        paid_on: paidOn,
        amount: Math.round(value * 100) / 100,
        currency: row.currency,
      })
      await mutate(key => typeof key === 'string' && AFFECTED_KEYS.test(key))
      toast.success(`${row.name} marked as paid`)
      onClose()
    } catch (caught) {
      setError(errorMessage(caught, 'Could not mark this payment as paid.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={open => { if (!open) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>Mark {row.name} as paid</DialogTitle>
            <DialogDescription>Due {dueLabel(row.due_date)}. This adds it to Transactions.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <Label htmlFor="mark-paid-date">Paid on</Label>
            <Input id="mark-paid-date" type="date" value={paidOn} max={localDateKey()} onChange={event => setPaidOn(event.target.value)} required disabled={saving} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="mark-paid-amount">Amount ({row.currency})</Label>
            <Input id="mark-paid-amount" type="number" inputMode="decimal" min="0.01" step="0.01" value={amount} onChange={event => setAmount(event.target.value)} required disabled={saving} />
          </div>
          {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
            <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Mark as paid'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
