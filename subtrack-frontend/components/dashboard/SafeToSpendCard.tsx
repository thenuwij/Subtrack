'use client'

import { useEffect, useState, type FormEvent } from 'react'
import { ChevronDown, ChevronUp, Pencil } from 'lucide-react'
import { toast } from 'sonner'
import type { Preferences, SafeToSpend, SafeToSpendProfileInput } from '@/types'
import { getPreferences, getSafeToSpend, saveSafeToSpendProfile, updatePreferences } from '@/lib/api'
import { getAccessToken } from '@/lib/auth/session'
import { useCurrency } from '@/lib/context/currency'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { formatCurrency } from '@/lib/utils/currency'
import { formatStoredDate } from '@/lib/utils/dates'
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
  const [balance, setBalance] = useState(position?.profile ? String(position.profile.balance) : '')
  const [nextPayday, setNextPayday] = useState(position?.next_payday ?? '')
  const [schedule, setSchedule] = useState<PaySchedule>(scheduleOf(position))
  const [buffer, setBuffer] = useState(position?.profile ? String(position.profile.buffer) : '50')
  const [billsAfterPay, setBillsAfterPay] = useState(position?.profile?.payday_bills_after_pay ?? false)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      const token = await getAccessToken()
      if (!token) throw new Error('Your session has expired.')
      const { pay_interval_unit, pay_interval_count } = PAY_SCHEDULES[schedule]
      const input: SafeToSpendProfileInput = {
        balance: Number(balance),
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
        <Label htmlFor="safe-balance">Balance in your everyday account</Label>
        <Input id="safe-balance" type="number" step="0.01" inputMode="decimal" required value={balance} onChange={event => setBalance(event.target.value)} />
      </div>
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
      <section className="rounded-2xl bg-card p-5 shadow-sm sm:p-6">
        <h2 className="text-[17px] font-semibold text-foreground">How much can you safely spend?</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Add your balance and payday, and we&apos;ll set aside your tracked payments.
        </p>
        <ProfileForm position={position} onSaved={handleSaved} />
      </section>
    )
  }

  const currency = position.base_currency ?? position.profile?.currency ?? 'AUD'
  const payday = position.next_payday
    ? formatStoredDate(position.next_payday, { weekday: 'long', day: 'numeric', month: 'short' })
    : ''
  const balanceDate = position.balance_date
    ? formatStoredDate(position.balance_date, { day: 'numeric', month: 'short' })
    : ''
  const hasNumber = position.safe_to_spend !== null && position.per_day != null

  return (
    <section className="h-full rounded-2xl bg-card p-5 shadow-sm sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm font-medium text-muted-foreground">Safe to spend</p>
        {!editing ? (
          <button type="button" onClick={() => setEditing(true)} className="shrink-0 text-sm font-medium text-primary hover:underline">
            Update balance
          </button>
        ) : null}
      </div>

      {hasNumber && position.shortfall ? (
        <>
          <p className="mt-3 text-5xl font-semibold tracking-tight tabular-nums text-amber-600 dark:text-amber-400 sm:text-6xl">
            {formatCurrency(position.shortfall, currency)}
            <span className="ml-2 text-lg font-medium tracking-normal text-muted-foreground">short</span>
          </p>
          <p className="mt-2 text-[15px] text-muted-foreground">
            Your balance won&apos;t cover your payments and buffer before payday, {payday}.
          </p>
          {balanceDate ? (
            <p className="mt-1 text-[13px] text-muted-foreground">Balance from {balanceDate}</p>
          ) : null}
        </>
      ) : hasNumber ? (
        <>
          <p className="mt-3 text-5xl font-semibold tracking-tight tabular-nums text-foreground sm:text-6xl">
            {formatCurrency(position.per_day ?? 0, currency)}
            <span className="ml-2 text-lg font-medium tracking-normal text-muted-foreground">a day</span>
          </p>
          <p className="mt-2 text-[15px] text-muted-foreground">
            {formatCurrency(position.safe_to_spend ?? 0, currency)} until {payday}
            {balanceDate ? ` · balance from ${balanceDate}` : ''}
          </p>
        </>
      ) : (
        <p className="mt-2 text-lg font-medium text-foreground">
          {position.status === 'balance_outdated' ? 'Update your balance to see this' : 'We can’t give you a number yet'}
        </p>
      )}
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
            aria-expanded={showBreakdown}
            onClick={() => setShowBreakdown(value => !value)}
            className="flex items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground"
          >
            How this is worked out
            {showBreakdown ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
          {showBreakdown ? (
            <div className="mt-3 divide-y divide-border border-t border-border">
              <Row label="Balance" value={formatCurrency(position.balance ?? 0, currency)} />
              {position.commitments?.map(item => (
                <Row
                  key={`${item.id}-${item.due_at}`}
                  onClick={() => editPayment(item.id)}
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
          ) : null}
        </div>
      ) : null}
    </section>
  )
}
