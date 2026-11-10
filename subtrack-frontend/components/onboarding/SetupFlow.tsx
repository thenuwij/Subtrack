'use client'

import { useState, type FormEvent } from 'react'
import { useRouter } from 'next/navigation'
import { useSWRConfig } from 'swr'
import { Check, Plus, Sparkles, X } from 'lucide-react'
import { toast } from 'sonner'
import type { BillDraft, Category, Currency } from '@/types'
import { createSubscription, parseBillText, saveSafeToSpendProfile, updatePreferences } from '@/lib/api'
import { getAccessToken } from '@/lib/auth/session'
import { useCurrency } from '@/lib/context/currency'
import { apiKeys, errorMessage } from '@/lib/hooks/useApi'
import { PAY_SCHEDULES, type PaySchedule } from '@/lib/payday'
import { COMMON_BILLS, HOW_OFTEN, howOftenOf, type HowOften } from '@/lib/setup/commonBills'
import { formatCurrency } from '@/lib/utils/currency'
import { dateAtNoonUtc } from '@/lib/utils/dates'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

type Step = 'pay' | 'bills' | 'balance'
const STEPS: Step[] = ['pay', 'bills', 'balance']
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
  const [step, setStep] = useState<Step>('pay')
  const [schedule, setSchedule] = useState<PaySchedule>('fortnightly')
  const [nextPayday, setNextPayday] = useState('')
  const [payAmount, setPayAmount] = useState('')
  const [bills, setBills] = useState<BillRow[]>([])
  const [line, setLine] = useState('')
  const [parsing, setParsing] = useState(false)
  const [balance, setBalance] = useState('')
  const [saving, setSaving] = useState(false)
  // Bills already saved, so a retry after a failure doesn't add them twice.
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set())

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
      await Promise.all([
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
            <Button size="lg" disabled={!billsReady} onClick={() => setStep('balance')}>
              {bills.length === 0 ? 'No bills, continue' : 'Next'}
            </Button>
            <Button variant="ghost" onClick={() => setStep('pay')}>Back</Button>
            {!billsReady ? <p role="status" className="text-sm text-muted-foreground">Add an amount and next charge date for each bill.</p> : null}
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
          <p className="text-xs text-muted-foreground">
            We keep a {formatCurrency(DEFAULT_BUFFER, currency)} buffer aside. You can change it later. Subtrack never connects to your bank.
          </p>
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" size="lg" disabled={saving}>{saving ? 'Saving…' : 'See what I can spend'}</Button>
            <Button type="button" variant="ghost" disabled={saving} onClick={() => setStep('bills')}>Back</Button>
          </div>
        </form>
      ) : null}
    </div>
  )
}
