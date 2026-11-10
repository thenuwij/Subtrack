'use client'

import { useEffect, useState, type FormEvent } from 'react'
import Link from 'next/link'
import { ArrowUpRight, ChevronDown, ChevronRight, Clock, Pencil, Plus, Wallet, X } from 'lucide-react'
import { toast } from 'sonner'
import type { BillRow, PayPlan, Preferences, SafeToSpend, SafeToSpendProfileInput } from '@/types'
import { getPreferences, getSafeToSpend, logIncome, saveSafeToSpendProfile, trackEvent, undoSpend, updatePreferences } from '@/lib/api'
import { getAccessToken } from '@/lib/auth/session'
import { useCurrency } from '@/lib/context/currency'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { formatCurrency } from '@/lib/utils/currency'
import { PAY_SCHEDULES, type PaySchedule } from '@/lib/payday'
import { formatStoredDate } from '@/lib/utils/dates'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useEditPayment } from '@/components/subscriptions/PaymentEditor'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

function scheduleOf(position: SafeToSpend | undefined): PaySchedule {
  const profile = position?.profile
  if (profile?.pay_interval_unit === 'month') return 'monthly'
  return profile?.pay_interval_count === 1 ? 'weekly' : 'fortnightly'
}

function ProfileForm({ position, onSaved, onCancel }: {
  position: SafeToSpend | undefined
  onSaved: (position: SafeToSpend) => void
  onCancel?: () => void
}) {
  const { baseCurrency } = useCurrency()
  const [balance, setBalance] = useState(position?.profile?.balance != null ? String(position.profile.balance) : '')
  const [payAmount, setPayAmount] = useState(position?.profile?.pay_amount != null ? String(position.profile.pay_amount) : '')
  const [nextPayday, setNextPayday] = useState(position?.next_payday ?? '')
  const [schedule, setSchedule] = useState<PaySchedule>(scheduleOf(position))
  const [buffer, setBuffer] = useState(position?.profile ? String(position.profile.buffer) : '50')
  const [billsAfterPay, setBillsAfterPay] = useState(position?.profile?.payday_bills_after_pay ?? false)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (balance.trim() === '' && payAmount.trim() === '') {
      toast.error('Enter your usual pay or today’s balance.')
      return
    }
    setSaving(true)
    try {
      const token = await getAccessToken()
      if (!token) throw new Error('Your session has expired.')
      const { pay_interval_unit, pay_interval_count } = PAY_SCHEDULES[schedule]
      const input: SafeToSpendProfileInput = {
        balance: balance.trim() === '' ? null : Number(balance),
        pay_amount: payAmount.trim() === '' ? null : Number(payAmount),
        currency: position?.profile?.currency ?? baseCurrency,
        next_payday: nextPayday,
        pay_interval_unit,
        pay_interval_count,
        buffer: Number(buffer),
        payday_bills_after_pay: billsAfterPay,
      }
      onSaved(await saveSafeToSpendProfile(token, input))
    } catch (error) {
      toast.error(errorMessage(error, 'Could not save your details.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="mt-4 grid gap-4 sm:grid-cols-2">
      <div className="space-y-1.5">
        <Label htmlFor="safe-pay">Usual pay after tax</Label>
        <Input id="safe-pay" type="number" step="0.01" min="0.01" inputMode="decimal" value={payAmount} onChange={event => setPayAmount(event.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="safe-balance">Today&apos;s balance <span className="font-normal text-muted-foreground">(optional)</span></Label>
        <Input id="safe-balance" type="number" step="0.01" inputMode="decimal" value={balance} onChange={event => setBalance(event.target.value)} />
      </div>
      <p className="-mt-2 text-xs text-muted-foreground sm:col-span-2">
        With just your pay, we estimate. Add today&apos;s balance for an exact number.
      </p>
      <div className="space-y-1.5">
        <Label htmlFor="safe-payday">Next payday</Label>
        <Input id="safe-payday" type="date" required value={nextPayday} onChange={event => setNextPayday(event.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="safe-schedule">How often you&apos;re paid</Label>
        <select
          id="safe-schedule"
          value={schedule}
          onChange={event => setSchedule(event.target.value as PaySchedule)}
          className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
        >
          {Object.entries(PAY_SCHEDULES).map(([value, option]) => (
            <option key={value} value={value}>{option.label}</option>
          ))}
        </select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="safe-buffer">Buffer to keep untouched</Label>
        <Input id="safe-buffer" type="number" step="0.01" min="0" inputMode="decimal" required value={buffer} onChange={event => setBuffer(event.target.value)} />
      </div>
      <label className="flex items-start gap-2 text-sm sm:col-span-2">
        <input
          type="checkbox"
          className="mt-0.5 h-4 w-4 accent-primary"
          checked={billsAfterPay}
          onChange={event => setBillsAfterPay(event.target.checked)}
        />
        <span>
          My pay arrives before bills due on payday
          <span className="block text-xs text-muted-foreground">
            Bills due on payday will come out of your next pay instead of this balance.
          </span>
        </span>
      </label>
      <div className="flex gap-2 sm:col-span-2">
        <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
        {onCancel ? <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button> : null}
      </div>
    </form>
  )
}

/** One field: today's balance. Everything else (payday, buffer) stays as saved. */
function QuickBalance({ position, onSaved, onCancel }: {
  position: SafeToSpend
  onSaved: (next: SafeToSpend) => void
  onCancel: () => void
}) {
  const [value, setValue] = useState('')
  const [saving, setSaving] = useState(false)
  const profile = position.profile

  async function check(event: FormEvent) {
    event.preventDefault()
    if (!profile || !position.next_payday || value.trim() === '') return
    setSaving(true)
    try {
      const token = await getAccessToken()
      if (!token) throw new Error('Your session has expired.')
      onSaved(await saveSafeToSpendProfile(token, {
        balance: Number(value),
        pay_amount: profile.pay_amount,
        currency: profile.currency,
        next_payday: position.next_payday,
        pay_interval_unit: profile.pay_interval_unit,
        pay_interval_count: profile.pay_interval_count,
        buffer: profile.buffer,
        payday_bills_after_pay: profile.payday_bills_after_pay,
      }))
    } catch (error) {
      toast.error(errorMessage(error, 'Could not check your balance.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={check} className="flex flex-wrap items-end gap-2">
      <div className="grid min-w-48 flex-1 gap-1.5">
        <Label htmlFor="safe-quick-balance">What&apos;s in your everyday account right now?</Label>
        <Input
          id="safe-quick-balance"
          type="number"
          step="0.01"
          inputMode="decimal"
          required
          autoFocus
          placeholder="Today’s balance"
          value={value}
          onChange={event => setValue(event.target.value)}
        />
      </div>
      <Button type="submit" disabled={saving}>{saving ? 'Checking…' : 'Check'}</Button>
      <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
    </form>
  )
}

function Row({ label, value, onClick }: { label: string; value: string; onClick?: () => void }) {
  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        title="Edit this payment"
        className="group -mx-2 flex w-[calc(100%+1rem)] items-center justify-between gap-4 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted"
      >
        <span className="min-w-0 truncate text-muted-foreground group-hover:text-foreground">{label}</span>
        <span className="flex shrink-0 items-center gap-2 font-medium tabular-nums text-foreground">
          {value}
          <Pencil className="h-3.5 w-3.5 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" aria-hidden="true" />
        </span>
      </button>
    )
  }
  return (
    <div className="flex items-center justify-between gap-4 py-1.5 text-sm">
      <span className="min-w-0 truncate text-muted-foreground">{label}</span>
      <span className="shrink-0 font-medium tabular-nums text-foreground">{value}</span>
    </div>
  )
}

function billLabel(bill: BillRow) {
  const day = formatStoredDate(bill.due_at, { day: 'numeric', month: 'short' })
  return `${bill.name} · ${bill.overdue ? `overdue since ${day}` : day}`
}

/** "today, 2:14 pm" or "Mon 10 Nov, 2:14 pm", in the browser's own timezone. */
function checkedLabel(iso: string) {
  const at = new Date(iso)
  const time = at.toLocaleTimeString('en-AU', { hour: 'numeric', minute: '2-digit' })
  if (at.toDateString() === new Date().toDateString()) return `today, ${time}`
  return `${at.toLocaleDateString('en-AU', { weekday: 'short', day: 'numeric', month: 'short' })}, ${time}`
}

/** Where this pay goes: bills from tracked payments, budgets, and what's left. Never goes stale. */
function IncomeForm({ onSaved, onCancel }: { onSaved: (next: SafeToSpend) => void; onCancel: () => void }) {
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      const token = await getAccessToken()
      if (!token) throw new Error('Your session has expired.')
      onSaved(await logIncome(token, { name: name.trim(), amount: Number(amount) }))
      toast.success('Extra income added')
    } catch (error) {
      toast.error(errorMessage(error, 'Could not add that.'))
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-[1fr_9rem]">
        <div className="space-y-1.5">
          <Label htmlFor="income-name">What</Label>
          <Input id="income-name" required maxLength={200} autoFocus placeholder="Extra shift" value={name} onChange={event => setName(event.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="income-amount">Amount</Label>
          <Input id="income-amount" required type="number" step="0.01" min="0.01" inputMode="decimal" value={amount} onChange={event => setAmount(event.target.value)} />
        </div>
      </div>
      <div className="flex gap-2">
        <Button type="submit" disabled={saving}>{saving ? 'Adding…' : 'Add income'}</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  )
}

function PayPlanSummary({ plan, budgetNames, currency, onEditPay, onEditBill, onAddIncome, onUndoIncome }: {
  plan: PayPlan
  budgetNames: string[]
  currency: string
  onEditPay: () => void
  onEditBill: (id: string) => void
  onAddIncome: () => void
  onUndoIncome: (id: string) => void
}) {
  const [showBills, setShowBills] = useState(false)
  const pay = plan.pay_amount
  const extra = plan.extra_income ?? 0
  const short = plan.left != null && plan.left < 0
  const segments = pay
    ? [
        { key: 'bills', amount: plan.bills, className: 'bg-foreground/55' },
        { key: 'set-aside', amount: plan.set_aside, className: 'bg-primary/35' },
        { key: 'spent', amount: plan.spent ?? 0, className: 'bg-foreground/25' },
        { key: 'left', amount: Math.max(plan.left ?? 0, 0), className: 'bg-primary' },
      ].filter(segment => segment.amount > 0)
    : []
  const total = Math.max((pay ?? 0) + extra, plan.bills + plan.set_aside + (plan.spent ?? 0))

  return (
    <div className="mt-4">
      {pay ? (
        <>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-sm text-muted-foreground">Your pay</p>
              <p className="mt-0.5 text-3xl font-semibold tracking-tight tabular-nums text-foreground">
                {formatCurrency(pay, currency)}
                {extra > 0 ? (
                  <span className="ml-2 text-lg font-medium tracking-normal text-primary">+ {formatCurrency(extra, currency)} extra</span>
                ) : null}
              </p>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={onAddIncome}
              className="border-primary/40 text-primary hover:bg-primary/10 hover:text-primary dark:border-primary/40"
            >
              <Plus className="h-4 w-4" />Add extra income
            </Button>
          </div>
          {plan.incomes?.length ? (
            <ul className="mt-2 flex flex-wrap gap-2" aria-label="Extra income this pay">
              {plan.incomes.map(income => (
                <li key={income.id} className="inline-flex items-center gap-1 rounded-full bg-primary/10 py-0.5 pl-3 pr-1 text-xs text-foreground">
                  {income.name} · <span className="tabular-nums">{formatCurrency(income.amount, currency)}</span>
                  <button
                    type="button"
                    onClick={() => onUndoIncome(income.id)}
                    aria-label={`Remove ${income.name}`}
                    className="flex h-6 w-6 items-center justify-center rounded-full text-muted-foreground hover:bg-primary/15 hover:text-foreground"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <div className="mt-4 flex h-2.5 w-full gap-0.5 overflow-hidden rounded-full bg-foreground/5" aria-hidden="true">
            {segments.map(segment => (
              <span key={segment.key} className={segment.className} style={{ width: `${(segment.amount / total) * 100}%` }} />
            ))}
          </div>
        </>
      ) : null}

      <dl className="mt-4 flex flex-wrap gap-x-10 gap-y-4 text-sm [&>div]:whitespace-nowrap">
        <div>
          <dt className="flex items-center gap-1.5 text-muted-foreground">
            {pay ? <span className="h-2 w-2 rounded-full bg-foreground/55" aria-hidden="true" /> : null}
            Bills this pay
          </dt>
          <dd>
            <button
              type="button"
              onClick={() => setShowBills(open => !open)}
              aria-expanded={showBills}
              className="flex items-center gap-1 text-xl font-semibold tabular-nums text-foreground hover:text-primary"
            >
              {formatCurrency(plan.bills, currency)}
              <span className="text-xs font-normal text-muted-foreground">({plan.bill_list.length})</span>
              <ChevronDown className={`h-3.5 w-3.5 text-muted-foreground transition-transform ${showBills ? 'rotate-180' : ''}`} aria-hidden="true" />
            </button>
          </dd>
        </div>
        {plan.set_aside > 0 ? (
          <div>
            <dt className="flex items-center gap-1.5 text-muted-foreground">
              <span className="h-2 w-2 rounded-full bg-primary/35" aria-hidden="true" />
              Budgets
            </dt>
            <dd className="text-xl font-semibold tabular-nums text-foreground">{formatCurrency(plan.set_aside, currency)}</dd>
            {budgetNames.length ? (
              <dd className="max-w-48 truncate text-xs text-muted-foreground">{budgetNames.join(', ')}</dd>
            ) : null}
          </div>
        ) : null}
        {plan.spent > 0 ? (
          <div>
            <dt className="flex items-center gap-1.5 text-muted-foreground">
              <span className="h-2 w-2 rounded-full bg-foreground/25" aria-hidden="true" />
              Spent
            </dt>
            <dd className="text-xl font-semibold tabular-nums text-foreground">{formatCurrency(plan.spent, currency)}</dd>
            <dd className="text-xs text-muted-foreground">Outside or over budgets</dd>
          </div>
        ) : null}
        {plan.left != null ? (
          <div>
            <dt className="flex items-center gap-1.5 text-muted-foreground">
              <span className={`h-2 w-2 rounded-full ${short ? 'bg-amber-500' : 'bg-primary'}`} aria-hidden="true" />
              {short ? 'Short this pay' : 'Balance'}
            </dt>
            <dd className={`text-xl font-semibold tabular-nums ${short ? 'text-amber-600 dark:text-amber-400' : 'text-primary'}`}>
              {formatCurrency(Math.abs(plan.left), currency)}
            </dd>
          </div>
        ) : (
          <div>
            <button type="button" onClick={onEditPay} className="text-sm font-medium text-primary hover:underline">
              Add your usual pay to see what&apos;s left
            </button>
          </div>
        )}
      </dl>

      {showBills ? (
        <div className="mt-3 divide-y divide-border rounded-xl bg-foreground/[0.03] px-3 py-1">
          {plan.bill_list.length === 0 ? (
            <p className="py-2 text-sm text-muted-foreground">No tracked bills land in this pay.</p>
          ) : plan.bill_list.map(bill => (
            <Row
              key={`${bill.id}-${bill.due_at}`}
              label={billLabel(bill)}
              value={`${bill.is_estimate ? '≈ ' : ''}${formatCurrency(bill.amount, currency)}`}
              onClick={() => onEditBill(bill.id)}
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}

export function SafeToSpendCard() {
  const query = useApi<SafeToSpend>(apiKeys.safeToSpend, getSafeToSpend)
  const preferences = useApi<Preferences>(apiKeys.preferences, getPreferences)
  const [editing, setEditing] = useState(false)
  const [checking, setChecking] = useState(false)
  // The free-to-spend number is a one-off answer: shown right after a check, then put away.
  const [justChecked, setJustChecked] = useState(false)
  const [showBreakdown, setShowBreakdown] = useState(false)
  const [addingIncome, setAddingIncome] = useState(false)
  const editPayment = useEditPayment()
  const { mutate: refreshPosition } = query
  const { mutate: refreshPreferences } = preferences
  const savedTimezone = preferences.data?.timezone

  useEffect(() => {
    const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone
    if (!savedTimezone || !browserTimezone || savedTimezone === browserTimezone) return
    void (async () => {
      const token = await getAccessToken()
      if (!token) return
      await updatePreferences(token, { timezone: browserTimezone })
      await Promise.all([refreshPreferences(), refreshPosition()])
    })().catch(() => undefined)
  }, [savedTimezone, refreshPosition, refreshPreferences])

  const position = query.data
  const showsNumber = position?.pay_plan != null || position?.safe_to_spend != null
  // Counted once per person on the server; this only avoids repeat requests.
  useEffect(() => {
    if (!showsNumber) return
    try {
      if (localStorage.getItem('subtrack:first-number-seen')) return
      localStorage.setItem('subtrack:first-number-seen', '1')
    } catch {
      // Storage can be blocked; the server still counts it once.
    }
    trackEvent('first_number_seen')
  }, [showsNumber])

  function handleSaved(next: SafeToSpend) {
    setEditing(false)
    void query.mutate(next, { revalidate: false })
  }

  function handleIncomeAdded(next: SafeToSpend) {
    setAddingIncome(false)
    void query.mutate(next, { revalidate: false })
  }

  async function undoIncome(id: string) {
    try {
      const token = await getAccessToken()
      if (!token) throw new Error('Your session has expired.')
      void query.mutate(await undoSpend(token, id), { revalidate: false })
    } catch (error) {
      toast.error(errorMessage(error, 'Could not remove that.'))
    }
  }

  function handleChecked(next: SafeToSpend) {
    setChecking(false)
    setJustChecked(true)
    void query.mutate(next, { revalidate: false })
  }

  if (query.error && !position) {
    return (
      <section className="flex flex-col gap-3 rounded-2xl bg-card p-5 shadow-sm sm:p-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-[17px] font-semibold text-foreground">This pay</h2>
          <p className="mt-1 text-sm text-muted-foreground">We couldn&apos;t work this out right now.</p>
        </div>
        <Button size="sm" variant="outline" disabled={query.isValidating} onClick={() => void query.mutate()}>
          {query.isValidating ? 'Trying again…' : 'Try again'}
        </Button>
      </section>
    )
  }
  if (!position) return <section className="h-40 animate-pulse rounded-2xl bg-card shadow-sm" aria-label="Loading this pay" />

  const profileDialog = (
    <Dialog open={editing} onOpenChange={setEditing}>
      <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader><DialogTitle>Your pay & payday</DialogTitle></DialogHeader>
        <DialogDescription>You enter these yourself. Subtrack doesn&apos;t connect to your bank.</DialogDescription>
        <ProfileForm position={position} onSaved={handleSaved} onCancel={() => setEditing(false)} />
      </DialogContent>
    </Dialog>
  )

  if (position.status === 'needs_setup') {
    return (
      <section className="money-hero flex h-full min-h-72 flex-col items-start justify-center">
        <span className="mb-5 flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary"><Wallet className="h-5 w-5" strokeWidth={1.7} /></span>
        <p className="eyebrow text-primary">Until next payday</p>
        <h2 className="mt-3 max-w-xs text-[28px] font-semibold leading-tight tracking-tight">Know what&apos;s yours to spend.</h2>
        <p className="mt-3 max-w-sm text-sm leading-6 text-muted-foreground">Start with your pay or today&apos;s balance. We&apos;ll set aside your bills and a little buffer.</p>
        <Button className="mt-6" onClick={() => setEditing(true)}>Set up safe to spend <ArrowUpRight className="h-4 w-4" /></Button>
        {profileDialog}
      </section>
    )
  }

  const currency = position.base_currency ?? position.profile?.currency ?? 'AUD'
  const shortPayday = position.next_payday
    ? formatStoredDate(position.next_payday, { weekday: 'short', day: 'numeric', month: 'short' })
    : ''
  const cycleStart = position.pay_cycle_start
    ? formatStoredDate(position.pay_cycle_start, { day: 'numeric', month: 'short' })
    : ''
  // Only a balance gives an exact "right now" answer; the pay estimate is what the plan above shows.
  const hasBalanceResult = position.mode === 'balance' && position.safe_to_spend != null
  const lastChecked = position.balance_checked_at ? checkedLabel(position.balance_checked_at) : null
  const freeAmount = position.shortfall || position.safe_to_spend || 0

  return (
    <section className="money-hero" data-tour="free-to-spend">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-[17px] font-semibold text-foreground">
          This pay
          {cycleStart && position.next_payday ? (
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              {cycleStart} – {formatStoredDate(position.next_payday, { day: 'numeric', month: 'short' })}
            </span>
          ) : null}
        </h2>
        <div className="flex shrink-0 items-center gap-4">
          <button type="button" onClick={() => setEditing(true)} className="text-sm font-medium text-primary hover:underline">
            Edit pay
          </button>
        </div>
      </div>

      {position.pay_plan ? (
        <PayPlanSummary
          plan={position.pay_plan}
          budgetNames={(position.set_asides ?? []).map(item => item.name)}
          currency={currency}
          onEditPay={() => setEditing(true)}
          onEditBill={editPayment}
          onAddIncome={() => setAddingIncome(true)}
          onUndoIncome={id => void undoIncome(id)}
        />
      ) : (
        <p className="mt-4 text-sm text-muted-foreground">Some amounts couldn&apos;t be converted, so this pay can&apos;t be worked out right now.</p>
      )}

      <div className="mt-5 border-t border-border pt-4">
        {checking ? (
          <QuickBalance position={position} onSaved={handleChecked} onCancel={() => setChecking(false)} />
        ) : justChecked && hasBalanceResult ? (
          <div>
            <p className="text-sm font-semibold text-foreground">Free to spend right now</p>
            <p className={`mt-1 text-4xl font-semibold tracking-tight tabular-nums ${position.shortfall ? 'text-amber-600 dark:text-amber-400' : 'text-foreground'}`}>
              {formatCurrency(freeAmount, currency)}
              <span className="ml-2 text-base font-medium tracking-normal text-muted-foreground">{position.shortfall ? 'short' : 'free'}</span>
            </p>
            {!position.shortfall ? (
              <p className="mt-1 text-sm text-muted-foreground">
                About {formatCurrency(position.per_day ?? 0, currency)} a day until {shortPayday}
              </p>
            ) : null}
            <p className="mt-3 text-xs leading-5 text-muted-foreground">
              Worked out just now from your balance of {formatCurrency(position.balance ?? 0, currency)}. It won&apos;t change as you spend, so check again next time.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1">
              <button type="button" onClick={() => setShowBreakdown(true)} className="flex min-h-11 items-center gap-1 text-sm font-medium text-primary hover:underline">
                How this is worked out <ChevronRight className="h-4 w-4" aria-hidden="true" />
              </button>
              <Button size="sm" variant="outline" onClick={() => setJustChecked(false)}>Done</Button>
            </div>
          </div>
        ) : (
          <div>
            {lastChecked && hasBalanceResult ? (
              <p className="mb-3 flex items-start gap-1.5 text-xs leading-5 text-muted-foreground">
                <Clock className="mt-0.5 h-3 w-3 shrink-0" aria-hidden="true" />
                <span>Last checked {lastChecked}: {formatCurrency(freeAmount, currency)} {position.shortfall ? 'short' : 'was free'} then. Anything spent since isn&apos;t counted.</span>
              </p>
            ) : null}
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => setChecking(true)} disabled={!position.profile}>Check my balance</Button>
              <Button asChild variant="outline" className="border-primary/40 text-primary hover:bg-primary/10 hover:text-primary dark:border-primary/40">
                <Link href="/afford">Can I afford it?</Link>
              </Button>
            </div>
          </div>
        )}
      </div>

      {profileDialog}

      <Dialog open={addingIncome} onOpenChange={setAddingIncome}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>Add extra income</DialogTitle></DialogHeader>
          <DialogDescription>Money you got this pay on top of your usual pay, like an extra shift or a refund. It counts for this pay only.</DialogDescription>
          {addingIncome ? <IncomeForm onSaved={handleIncomeAdded} onCancel={() => setAddingIncome(false)} /> : null}
        </DialogContent>
      </Dialog>

      <Dialog open={showBreakdown} onOpenChange={setShowBreakdown}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>How free to spend is worked out</DialogTitle>
          </DialogHeader>
          <div className="divide-y divide-border">
            <Row label="Balance" value={formatCurrency(position.balance ?? 0, currency)} />
            {position.commitments?.map(item => (
              <Row
                key={`${item.id}-${item.due_at}`}
                onClick={() => { setShowBreakdown(false); editPayment(item.id) }}
                label={billLabel(item)}
                value={`${item.is_estimate ? '≈ ' : ''}−${formatCurrency(item.amount, currency)}`}
              />
            ))}
            {position.set_aside ? <Row label="Budgets" value={`−${formatCurrency(position.set_aside, currency)}`} /> : null}
            {position.extra_income ? <Row label="Extra income you added" value={`+${formatCurrency(position.extra_income, currency)}`} /> : null}
            {position.spent ? <Row label="Spends you logged" value={`−${formatCurrency(position.spent, currency)}`} /> : null}
            <Row label="Buffer" value={`−${formatCurrency(position.buffer ?? 0, currency)}`} />
            {position.warnings?.map(warning => (
              <p key={warning} className="pt-3 text-[13px] leading-5 text-muted-foreground">{warning}</p>
            ))}
            <p className="pt-3 text-xs leading-5 text-muted-foreground">
              Click a payment to change its date or amount. {position.scope}
            </p>
          </div>
        </DialogContent>
      </Dialog>
    </section>
  )
}
