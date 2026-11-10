'use client'

import { useEffect, useState, type FormEvent } from 'react'
import { ArrowUpRight, ChevronRight, Pencil, Wallet } from 'lucide-react'
import { toast } from 'sonner'
import type { Preferences, SafeToSpend, SafeToSpendProfileInput } from '@/types'
import { getPreferences, getSafeToSpend, saveSafeToSpendProfile, updatePreferences } from '@/lib/api'
import { getAccessToken } from '@/lib/auth/session'
import { useCurrency } from '@/lib/context/currency'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { formatCurrency } from '@/lib/utils/currency'
import { formatStoredDate } from '@/lib/utils/dates'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useEditPayment } from '@/components/subscriptions/PaymentEditor'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const PAY_SCHEDULES = {
  weekly: { pay_interval_unit: 'week', pay_interval_count: 1, label: 'Weekly' },
  fortnightly: { pay_interval_unit: 'week', pay_interval_count: 2, label: 'Fortnightly' },
  monthly: { pay_interval_unit: 'month', pay_interval_count: 1, label: 'Monthly' },
} as const

type PaySchedule = keyof typeof PAY_SCHEDULES

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

function localDateKey() {
  // en-CA formats as YYYY-MM-DD in the browser's own timezone.
  return new Date().toLocaleDateString('en-CA')
}

/** One field: today's balance. Everything else (payday, buffer) stays as saved. */
function QuickBalance({ position, onSaved }: { position: SafeToSpend; onSaved: (next: SafeToSpend) => void }) {
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
    <form onSubmit={check} className="mt-4 flex items-end gap-2">
      <div className="grid flex-1 gap-1.5">
        <Label htmlFor="safe-quick-balance">Today&apos;s balance</Label>
        <Input
          id="safe-quick-balance"
          type="number"
          step="0.01"
          inputMode="decimal"
          required
          placeholder="What’s in your everyday account now?"
          value={value}
          onChange={event => setValue(event.target.value)}
        />
      </div>
      <Button type="submit" disabled={saving}>{saving ? 'Checking…' : 'Check'}</Button>
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

export function SafeToSpendCard() {
  const query = useApi<SafeToSpend>(apiKeys.safeToSpend, getSafeToSpend)
  const preferences = useApi<Preferences>(apiKeys.preferences, getPreferences)
  const [editing, setEditing] = useState(false)
  const [showBreakdown, setShowBreakdown] = useState(false)
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

  function handleSaved(next: SafeToSpend) {
    setEditing(false)
    void query.mutate(next, { revalidate: false })
  }

  if (query.error && !position) {
    return (
      <section className="flex flex-col gap-3 rounded-2xl bg-card p-5 shadow-sm sm:p-6 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-[17px] font-semibold text-foreground">Safe to spend</h2>
          <p className="mt-1 text-sm text-muted-foreground">We couldn&apos;t work this out right now.</p>
        </div>
        <Button size="sm" variant="outline" disabled={query.isValidating} onClick={() => void query.mutate()}>
          {query.isValidating ? 'Trying again…' : 'Try again'}
        </Button>
      </section>
    )
  }
  if (!position) return <section className="h-40 animate-pulse rounded-2xl bg-card shadow-sm" aria-label="Loading safe to spend" />

  if (position.status === 'needs_setup') {
    return (
      <section className="money-hero flex h-full min-h-72 flex-col items-start justify-center">
        <span className="mb-5 flex h-11 w-11 items-center justify-center rounded-2xl bg-primary/10 text-primary"><Wallet className="h-5 w-5" strokeWidth={1.7} /></span>
        <p className="eyebrow text-primary">Until next payday</p>
        <h2 className="mt-3 max-w-xs text-[28px] font-semibold leading-tight tracking-tight">Know what&apos;s yours to spend.</h2>
        <p className="mt-3 max-w-sm text-sm leading-6 text-muted-foreground">Start with your pay or today&apos;s balance. We&apos;ll set aside your bills and a little buffer.</p>
        <Button className="mt-6" onClick={() => setEditing(true)}>Set up safe to spend <ArrowUpRight className="h-4 w-4" /></Button>
        <Dialog open={editing} onOpenChange={setEditing}>
          <DialogContent className="max-h-[85dvh] overflow-y-auto sm:max-w-lg">
            <DialogHeader><DialogTitle>Your pay & payday</DialogTitle></DialogHeader>
            <DialogDescription>You enter these yourself. Subtrack doesn&apos;t connect to your bank.</DialogDescription>
            <ProfileForm position={position} onSaved={handleSaved} onCancel={() => setEditing(false)} />
          </DialogContent>
        </Dialog>
      </section>
    )
  }

  const currency = position.base_currency ?? position.profile?.currency ?? 'AUD'
  const shortPayday = position.next_payday
    ? formatStoredDate(position.next_payday, { weekday: 'short', day: 'numeric', month: 'short' })
    : ''
  const balanceDate = position.balance_date
    ? formatStoredDate(position.balance_date, { day: 'numeric', month: 'short' })
    : ''
  const hasNumber = position.safe_to_spend !== null && position.per_day != null
  const isEstimate = position.mode === 'estimate'
  // A typed-in balance can't see spending since, so the result is only "now"
  // on the day it was entered. Older results are shown dated and dimmed. An
  // estimate covers the whole pay cycle, so it is never dimmed.
  const isCurrent = isEstimate || position.balance_date === localDateKey()

  return (
    <section className="money-hero h-full">
      <div className="flex items-start justify-between gap-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
          Safe to spend
          {hasNumber && isEstimate ? <span className="rounded-full bg-foreground/5 px-2 py-0.5 text-xs font-medium text-muted-foreground">Estimate</span> : null}
        </h2>
        {!editing ? (
          <button type="button" onClick={() => setEditing(true)} className="shrink-0 text-sm font-medium text-primary hover:underline">
            {isCurrent && !isEstimate ? 'Update balance' : 'Edit details'}
          </button>
        ) : null}
      </div>

      {hasNumber ? (
        <div className={isCurrent ? '' : 'opacity-60'}>
          <p className={`mt-3 font-semibold tracking-tight tabular-nums ${
            isCurrent ? 'text-[clamp(2rem,5vw,3.75rem)]' : 'text-3xl'
          } ${position.shortfall ? 'text-amber-600 dark:text-amber-400' : 'text-foreground'}`}>
            {formatCurrency(position.shortfall || position.safe_to_spend || 0, currency)}
            <span className="ml-2 whitespace-nowrap text-lg font-medium tracking-normal text-muted-foreground">
              {position.shortfall ? 'short' : 'to spend'}
            </span>
          </p>
          <p className="mt-2 text-[15px] text-muted-foreground">
            {isEstimate ? `From your usual pay · payday ${shortPayday}` : `As of ${balanceDate} · payday ${shortPayday}`}
          </p>
        </div>
      ) : (
        <p className="mt-2 text-lg font-medium text-foreground">
          {position.status === 'balance_outdated' ? 'Enter today’s balance to see this' : 'We can’t give you a number yet'}
        </p>
      )}

      {hasNumber && isCurrent && !position.shortfall ? (
        <p className="mt-4 inline-flex items-center rounded-full bg-foreground/5 px-3 py-1.5 text-xs font-medium text-foreground">{isEstimate ? 'About ' : ''}{formatCurrency(position.per_day ?? 0, currency)} a day {isEstimate ? 'this pay cycle' : 'until payday'}</p>
      ) : null}
      {!editing && (!isCurrent || isEstimate) ? (
        <QuickBalance position={position} onSaved={handleSaved} />
      ) : null}
      {!hasNumber ? position.warnings?.map(warning => (
        <p key={warning} className="mt-2 text-xs leading-5 text-amber-700 dark:text-amber-300">{warning}</p>
      )) : null}


      {editing ? (
        <ProfileForm position={position} onSaved={handleSaved} onCancel={() => setEditing(false)} />
      ) : null}

      {hasNumber && !editing ? (
        <div className="mt-5 border-t border-border pt-4">
          <button
            type="button"
            onClick={() => setShowBreakdown(true)}
            className="flex min-h-11 items-center gap-1 text-sm font-medium text-primary hover:underline"
          >
            How this is worked out
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </button>
          <Dialog open={showBreakdown} onOpenChange={setShowBreakdown}>
            <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>How safe to spend is worked out</DialogTitle>
              </DialogHeader>
            <div className="divide-y divide-border">
              {isEstimate
                ? <Row label="Usual pay" value={formatCurrency(position.pay_amount ?? 0, currency)} />
                : <Row label="Balance" value={formatCurrency(position.balance ?? 0, currency)} />}
              {position.commitments?.map(item => (
                <Row
                  key={`${item.id}-${item.due_at}`}
                  onClick={() => { setShowBreakdown(false); editPayment(item.id) }}
                  label={`${item.name} · ${formatStoredDate(item.due_at, { day: 'numeric', month: 'short' })}`}
                  value={`${item.is_estimate ? '≈ ' : ''}−${formatCurrency(item.amount, currency)}`}
                />
              ))}
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
        </div>
      ) : null}
    </section>
  )
}
