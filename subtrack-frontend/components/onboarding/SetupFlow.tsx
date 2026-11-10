'use client'

import { useEffect, useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { useSWRConfig } from 'swr'
import { Check, Plus, Sparkles, X } from 'lucide-react'
import { toast } from 'sonner'
import type { BillDraft, Category, Currency, SetAsideKind } from '@/types'
import {
  createSetAside,
  createSubscription,
  getEmailReminders,
  parseBillText,
  saveSafeToSpendProfile,
  setEmailReminders,
  trackEvent,
  updatePreferences,
  type EmailSettings,
} from '@/lib/api'
import { getAccessToken, useIsDemo } from '@/lib/auth/session'
import { useCurrency } from '@/lib/context/currency'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { PAY_SCHEDULES, type PaySchedule } from '@/lib/payday'
import { COMMON_BILLS, HOW_OFTEN, howOftenOf, type HowOften } from '@/lib/setup/commonBills'
import { formatCurrency } from '@/lib/utils/currency'
import { dateAtNoonUtc } from '@/lib/utils/dates'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

type Step = 'intro' | 'pay' | 'bills' | 'pots' | 'balance'
const STEPS: Step[] = ['pay', 'bills', 'pots', 'balance']
const POT_SUGGESTIONS: { kind: SetAsideKind; name: string; amount: string }[] = [
  { kind: 'pot', name: 'Eating out', amount: '60' },
  { kind: 'pot', name: 'Groceries', amount: '100' },
  { kind: 'pot', name: 'Fuel', amount: '40' },
  { kind: 'save', name: 'Savings', amount: '50' },
]
const DEFAULT_BUFFER = 50

interface BillRow {
  id: string
  name: string
  category: Category
  currency: Currency
  howOften: HowOften
  amount: string
  nextDue: string
}

const selectClass = 'h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm'

function newId() {
  return Math.random().toString(36).slice(2)
}

function billIsComplete(bill: BillRow) {
  return Number(bill.amount) > 0 && bill.nextDue !== ''
}

/** First-run setup: pay, then bills, then an optional balance, then Home. */
export function SetupFlow() {
  const router = useRouter()
  const { mutate } = useSWRConfig()
  const { baseCurrency } = useCurrency()
  const [step, setStep] = useState<Step>('intro')
  const [potAmounts, setPotAmounts] = useState<Record<string, string>>({})
  const [schedule, setSchedule] = useState<PaySchedule>('fortnightly')
  const [nextPayday, setNextPayday] = useState('')
  const [payAmount, setPayAmount] = useState('')
  const [bills, setBills] = useState<BillRow[]>([])
  const [line, setLine] = useState('')
  const [parsing, setParsing] = useState(false)
  const [balance, setBalance] = useState('')
  const [paydayEmail, setPaydayEmail] = useState(false)
  const emailSettings = useApi<EmailSettings>(apiKeys.emailSettings, getEmailReminders)
  const demo = useIsDemo()
  const canEmail = !demo && Boolean(emailSettings.data?.configured)
  const [saving, setSaving] = useState(false)
  // Bills already saved, so a retry after a failure doesn't add them twice.
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set())

  useEffect(() => trackEvent('setup_started'), [])

  const currency = baseCurrency as Currency
  const picked = new Set(bills.map(bill => bill.name.toLowerCase()))

  function addBill(bill: Omit<BillRow, 'id'>) {
    setBills(current => [...current, { ...bill, id: newId() }])
  }

  function updateBill(id: string, changes: Partial<BillRow>) {
    setBills(current => current.map(bill => (bill.id === id ? { ...bill, ...changes } : bill)))
  }

  function toggleCommon(name: string, category: Category, howOften: HowOften) {
    if (picked.has(name.toLowerCase())) {
      setBills(current => current.filter(bill => bill.name.toLowerCase() !== name.toLowerCase()))
    } else {
      addBill({ name, category, howOften, currency, amount: '', nextDue: '' })
    }
  }

  async function handleParse(event: FormEvent) {
    event.preventDefault()
    if (!line.trim()) return
    setParsing(true)
    try {
      const token = await getAccessToken()
      if (!token) throw new Error('Your session has expired.')
      const { bills: drafts } = await parseBillText(token, line.trim())
      drafts.forEach((draft: BillDraft) => addBill({
        name: draft.name,
        category: draft.category,
        currency: draft.currency,
        howOften: howOftenOf(draft.interval_unit, draft.interval_count),
        amount: String(draft.amount),
        nextDue: draft.next_due ?? '',
      }))
      setLine('')
    } catch (error) {
      toast.error(errorMessage(error, 'Could not read that. Pick from the list instead.'))
    } finally {
      setParsing(false)
    }
  }

  async function finish() {
    setSaving(true)
    try {
      const token = await getAccessToken()
      if (!token) throw new Error('Your session has expired.')
      const { pay_interval_unit, pay_interval_count } = PAY_SCHEDULES[schedule]
      await saveSafeToSpendProfile(token, {
        balance: balance.trim() === '' ? null : Number(balance),
        pay_amount: Number(payAmount),
        currency,
        next_payday: nextPayday,
        pay_interval_unit,
        pay_interval_count,
        buffer: DEFAULT_BUFFER,
        payday_bills_after_pay: false,
      })
      const saved = new Set(savedIds)
      for (const bill of bills) {
        if (saved.has(bill.id)) continue
        const { interval_unit, interval_count } = HOW_OFTEN[bill.howOften]
        await createSubscription(token, {
          name: bill.name,
          category: bill.category,
          amount: Number(bill.amount),
          currency: bill.currency,
          interval_unit,
          interval_count,
          next_due: dateAtNoonUtc(bill.nextDue),
        })
        saved.add(bill.id)
        setSavedIds(new Set(saved))
      }
      for (const pot of POT_SUGGESTIONS) {
        const amount = Number(potAmounts[pot.name])
        if (amount > 0) await createSetAside(token, { kind: pot.kind, name: pot.name, amount_per_pay: amount })
      }
      if (paydayEmail && canEmail) {
        // Setup is saved either way; the switch is also in Account.
        await setEmailReminders(token, { payday: true }).catch(() => {
          toast.error('Could not turn on the payday email. You can turn it on in Account.')
        })
      }
      trackEvent('setup_finished')
      await Promise.all([
        mutate(apiKeys.emailSettings),
        mutate(apiKeys.safeToSpend),
        mutate(apiKeys.subscriptions('current')),
        mutate(apiKeys.preferences),
      ])
      router.push('/dashboard')
    } catch (error) {
      toast.error(errorMessage(error, 'Could not save. Try again.'))
      setSaving(false)
    }
  }

  async function skip() {
    try {
      const token = await getAccessToken()
      if (token) await updatePreferences(token, { onboarding_completed: true })
      await mutate(apiKeys.preferences)
    } finally {
      router.push('/dashboard')
    }
  }

  const payReady = nextPayday !== '' && Number(payAmount) > 0
  const billsReady = bills.every(billIsComplete)
  const stepIndex = STEPS.indexOf(step)

  if (step === 'intro') {
    return (
      <div className="mx-auto max-w-2xl px-4 py-12 sm:px-6">
        <p className="eyebrow text-primary">Welcome to Subtrack</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">Know what&apos;s yours to spend until payday.</h1>
        <ol className="mt-8 grid gap-3 sm:grid-cols-3">
          {[
            ['1', 'Your pay comes in', 'Tell us when you’re paid and roughly how much.'],
            ['2', 'Bills and pots come off', 'Rent, phone, subscriptions, plus money you hold back for eating out or saving.'],
            ['3', 'What’s left is yours', 'One number on Home, and how much that is per day.'],
          ].map(([number, title, body]) => (
            <li key={number} className="rounded-2xl bg-card p-5 shadow-sm">
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-sm font-semibold text-primary">{number}</span>
              <p className="mt-3 font-semibold">{title}</p>
              <p className="mt-1 text-sm text-muted-foreground">{body}</p>
            </li>
          ))}
        </ol>
        <p className="mt-6 text-sm text-muted-foreground">No bank login. Setup takes about three minutes.</p>
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <Button size="lg" onClick={() => setStep('pay')}>Get started</Button>
          <Button variant="ghost" onClick={() => void skip()}>Skip for now</Button>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-10 sm:px-6">
      <div className="flex items-center justify-between gap-4">
        <p className="eyebrow text-primary">Step {stepIndex + 1} of {STEPS.length}</p>
        <button type="button" onClick={() => void skip()} className="text-sm text-muted-foreground hover:text-foreground">
          Skip for now
        </button>
      </div>

      {step === 'pay' ? (
        <form
          className="mt-4 space-y-6"
          onSubmit={event => { event.preventDefault(); if (payReady) setStep('bills') }}
        >
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">When do you get paid?</h1>
            <p className="mt-2 text-muted-foreground">We work out what&apos;s free to spend until each payday.</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="setup-schedule">How often</Label>
              <select id="setup-schedule" value={schedule} onChange={event => setSchedule(event.target.value as PaySchedule)} className={selectClass}>
                {Object.entries(PAY_SCHEDULES).map(([value, option]) => <option key={value} value={value}>{option.label}</option>)}
              </select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="setup-payday">Next payday</Label>
              <Input id="setup-payday" type="date" required value={nextPayday} onChange={event => setNextPayday(event.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="setup-pay">Usual pay after tax</Label>
              <Input id="setup-pay" type="number" step="0.01" min="0.01" inputMode="decimal" required value={payAmount} onChange={event => setPayAmount(event.target.value)} />
            </div>
          </div>
          <Button type="submit" size="lg" disabled={!payReady}>Next</Button>
        </form>
      ) : null}

      {step === 'bills' ? (
        <div className="mt-4 space-y-6">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">What bills come out regularly?</h1>
            <p className="mt-2 text-muted-foreground">Tap the ones you pay, or type them in one line.</p>
          </div>

          <div className="flex flex-wrap gap-2" role="group" aria-label="Common bills">
            {COMMON_BILLS.map(bill => {
              const on = picked.has(bill.name.toLowerCase())
              return (
                <button
                  key={bill.name}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggleCommon(bill.name, bill.category, bill.howOften)}
                  className={`flex min-h-9 items-center gap-1.5 rounded-full border px-3 text-sm transition-colors ${on ? 'border-primary bg-primary/10 text-primary' : 'border-border bg-card hover:border-primary/40'}`}
                >
                  {on ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : <Plus className="h-3.5 w-3.5" aria-hidden="true" />}
                  {bill.name}
                </button>
              )
            })}
          </div>

          <form onSubmit={handleParse} className="flex items-end gap-2">
            <div className="grid flex-1 gap-1.5">
              <Label htmlFor="setup-line">Or type them</Label>
              <Input id="setup-line" maxLength={500} placeholder="Rent 400 weekly, phone 35 monthly on the 15th" value={line} onChange={event => setLine(event.target.value)} />
            </div>
            <Button type="submit" variant="outline" disabled={parsing || !line.trim()}>
              <Sparkles className="h-4 w-4" aria-hidden="true" />{parsing ? 'Reading…' : 'Add'}
            </Button>
          </form>

          {bills.length > 0 ? (
            <ul className="divide-y divide-border rounded-2xl bg-card shadow-sm" aria-label="Your bills">
              {bills.map(bill => (
                <li key={bill.id} className="grid gap-3 p-4 sm:grid-cols-[1fr_7rem_8rem_9rem_auto] sm:items-end">
                  <p className="text-sm font-medium sm:pb-2">{bill.name}</p>
                  <div className="space-y-1">
                    <Label htmlFor={`amount-${bill.id}`} className="text-xs">Amount ({bill.currency})</Label>
                    <Input id={`amount-${bill.id}`} type="number" step="0.01" min="0.01" inputMode="decimal" value={bill.amount} onChange={event => updateBill(bill.id, { amount: event.target.value })} />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor={`often-${bill.id}`} className="text-xs">How often</Label>
                    <select id={`often-${bill.id}`} value={bill.howOften} onChange={event => updateBill(bill.id, { howOften: event.target.value as HowOften })} className={selectClass}>
                      {Object.entries(HOW_OFTEN).map(([value, option]) => <option key={value} value={value}>{option.label}</option>)}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor={`due-${bill.id}`} className="text-xs">Next charge</Label>
                    <Input id={`due-${bill.id}`} type="date" value={bill.nextDue} onChange={event => updateBill(bill.id, { nextDue: event.target.value })} />
                  </div>
                  <button
                    type="button"
                    onClick={() => setBills(current => current.filter(row => row.id !== bill.id))}
                    aria-label={`Remove ${bill.name}`}
                    className="flex h-9 w-9 items-center justify-center justify-self-end rounded-md text-muted-foreground hover:bg-muted"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          ) : null}

          <div className="flex flex-wrap items-center gap-3">
            <Button size="lg" disabled={!billsReady} onClick={() => setStep('pots')}>
              {bills.length === 0 ? 'No bills, continue' : 'Next'}
            </Button>
            <Button variant="ghost" onClick={() => setStep('pay')}>Back</Button>
            {!billsReady ? <p role="status" className="text-sm text-muted-foreground">Add an amount and next charge date for each bill.</p> : null}
          </div>
        </div>
      ) : null}

      {step === 'pots' ? (
        <div className="mt-4 space-y-6">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">Hold some money back each pay?</h1>
            <p className="mt-2 text-muted-foreground">Pots keep money aside for things you spend on, or for saving. Optional, and you can change them on Home.</p>
          </div>
          <ul className="divide-y divide-border rounded-2xl bg-card shadow-sm">
            {POT_SUGGESTIONS.map(pot => (
              <li key={pot.name} className="flex items-center justify-between gap-4 p-4">
                <div>
                  <p className="text-sm font-medium">{pot.name}</p>
                  <p className="text-xs text-muted-foreground">{pot.kind === 'pot' ? 'Spending pot' : 'Saving'} · each pay</p>
                </div>
                <div className="flex items-center gap-2">
                  <Label htmlFor={`pot-${pot.name}`} className="sr-only">{pot.name} each pay</Label>
                  <Input
                    id={`pot-${pot.name}`}
                    type="number"
                    step="0.01"
                    min="0"
                    inputMode="decimal"
                    placeholder={pot.amount}
                    value={potAmounts[pot.name] ?? ''}
                    onChange={event => setPotAmounts(current => ({ ...current, [pot.name]: event.target.value }))}
                    className="w-28"
                  />
                </div>
              </li>
            ))}
          </ul>
          <p className="text-xs text-muted-foreground">Leave a box empty to skip that pot.</p>
          <div className="flex flex-wrap items-center gap-3">
            <Button size="lg" onClick={() => setStep('balance')}>Next</Button>
            <Button variant="ghost" onClick={() => setStep('bills')}>Back</Button>
          </div>
        </div>
      ) : null}

      {step === 'balance' ? (
        <form className="mt-4 space-y-6" onSubmit={event => { event.preventDefault(); void finish() }}>
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">What&apos;s in your account today?</h1>
            <p className="mt-2 text-muted-foreground">Optional. Without it, we estimate from your pay. With it, the number is exact.</p>
          </div>
          <div className="max-w-xs space-y-1.5">
            <Label htmlFor="setup-balance">Everyday account balance</Label>
            <Input id="setup-balance" type="number" step="0.01" inputMode="decimal" value={balance} onChange={event => setBalance(event.target.value)} />
          </div>
          {canEmail ? (
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 accent-primary"
                checked={paydayEmail}
                onChange={event => setPaydayEmail(event.target.checked)}
              />
              <span>
                Email me on payday
                <span className="block text-xs text-muted-foreground">
                  Bills before your next pay and what&apos;s free to spend, plus a heads-up if bills won&apos;t fit. Turn it off any time in Account.
                </span>
              </span>
            </label>
          ) : null}
          <p className="text-xs text-muted-foreground">
            We keep a {formatCurrency(DEFAULT_BUFFER, currency)} buffer aside. You can change it later. Subtrack never connects to your bank.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" size="lg" disabled={saving}>{saving ? 'Saving…' : 'See what I can spend'}</Button>
            <Button type="button" variant="ghost" disabled={saving} onClick={() => setStep('pots')}>Back</Button>
          </div>
        </form>
      ) : null}
    </div>
  )
}
