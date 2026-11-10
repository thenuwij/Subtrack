'use client'

import { useState, type FormEvent } from 'react'
import { ChevronDown, PiggyBank, Plus, Receipt, Trash2, Undo2, Wallet } from 'lucide-react'
import { toast } from 'sonner'
import type { SafeToSpend, SetAsideKind, SetAsidePosition } from '@/types'
import { createSetAside, deleteSetAside, getSafeToSpend, logSpend, undoSpend } from '@/lib/api'
import { getAccessToken } from '@/lib/auth/session'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { formatCurrency } from '@/lib/utils/currency'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const selectClass = 'h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm'

interface Draft { kind: SetAsideKind; name: string; amount: string }

const SUGGESTIONS: Draft[] = [
  { kind: 'pot', name: 'Eating out', amount: '60' },
  { kind: 'pot', name: 'Groceries', amount: '100' },
  { kind: 'pot', name: 'Fuel', amount: '40' },
  { kind: 'save', name: 'Savings', amount: '50' },
]

const KIND_HELP: Record<SetAsideKind, string> = {
  pot: 'Money to spend on one thing. Log spends against it to see what’s left.',
  save: 'Money you keep. It comes off every pay so you don’t spend it.',
}

async function token() {
  const value = await getAccessToken()
  if (!value) throw new Error('Your session has expired.')
  return value
}

function AddDialog({ draft, onClose, onSaved }: { draft: Draft | null; onClose: () => void; onSaved: () => Promise<unknown> }) {
  const [kind, setKind] = useState<SetAsideKind>(draft?.kind ?? 'pot')
  const [name, setName] = useState(draft?.name ?? '')
  const [amount, setAmount] = useState(draft?.amount ?? '')
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      await createSetAside(await token(), { kind, name: name.trim(), amount_per_pay: Number(amount) })
      await onSaved()
      toast.success(`${name.trim()} added`)
      onClose()
    } catch (error) {
      toast.error(errorMessage(error, 'Could not add that.'))
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid grid-cols-2 gap-2" role="radiogroup" aria-label="Type">
        {(['pot', 'save'] as SetAsideKind[]).map(option => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={kind === option}
            onClick={() => setKind(option)}
            className={`rounded-xl border p-3 text-left text-sm transition-colors ${kind === option ? 'border-primary bg-primary/5' : 'border-border hover:border-primary/40'}`}
          >
            <span className="block font-medium">{option === 'pot' ? 'Spending pot' : 'Saving'}</span>
            <span className="mt-0.5 block text-xs text-muted-foreground">{KIND_HELP[option]}</span>
          </button>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-[1fr_9rem]">
        <div className="space-y-1.5">
          <Label htmlFor="set-aside-name">Name</Label>
          <Input id="set-aside-name" required maxLength={80} autoFocus placeholder={kind === 'pot' ? 'Eating out' : 'Trip'} value={name} onChange={event => setName(event.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="set-aside-amount">Each pay</Label>
          <Input id="set-aside-amount" required type="number" step="0.01" min="0.01" inputMode="decimal" value={amount} onChange={event => setAmount(event.target.value)} />
        </div>
      </div>
      <div className="flex gap-2">
        <Button type="submit" disabled={saving}>{saving ? 'Adding…' : 'Add'}</Button>
        <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
      </div>
    </form>
  )
}

function LogDialog({ pots, currency, onClose, onSaved }: { pots: SetAsidePosition[]; currency: string; onClose: () => void; onSaved: (next: SafeToSpend) => void }) {
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [from, setFrom] = useState(pots[0]?.id ?? '')
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      onSaved(await logSpend(await token(), { name: name.trim(), amount: Number(amount), set_aside_id: from || null }))
      toast.success('Spend logged')
      onClose()
    } catch (error) {
      toast.error(errorMessage(error, 'Could not log that.'))
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-[1fr_9rem]">
        <div className="space-y-1.5">
          <Label htmlFor="spend-name">What</Label>
          <Input id="spend-name" required maxLength={200} autoFocus placeholder="Dinner with friends" value={name} onChange={event => setName(event.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="spend-amount">Amount</Label>
          <Input id="spend-amount" required type="number" step="0.01" min="0.01" inputMode="decimal" value={amount} onChange={event => setAmount(event.target.value)} />
        </div>
      </div>
      {pots.length > 0 ? (
        <div className="space-y-1.5">
          <Label htmlFor="spend-from">Comes out of</Label>
          <select id="spend-from" value={from} onChange={event => setFrom(event.target.value)} className={selectClass}>
            {pots.map(pot => <option key={pot.id} value={pot.id}>{pot.name} ({formatCurrency(pot.left ?? 0, currency)} left)</option>)}
            <option value="">Free to spend</option>
          </select>
          <p className="text-xs text-muted-foreground">A spend from a pot uses up the pot. Free to spend lowers your number.</p>
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">This comes off what&apos;s free to spend until your next balance update.</p>
      )}
      <div className="flex gap-2">
        <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Log spend'}</Button>
        <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
      </div>
    </form>
  )
}

function PotRow({ item, currency, onRemove }: { item: SetAsidePosition; currency: string; onRemove: () => void }) {
  const used = item.kind === 'pot' && item.amount > 0 ? Math.min(1, (item.spent ?? 0) / item.amount) : 0
  const over = item.kind === 'pot' && (item.spent ?? 0) > item.amount
  return (
    <li className="flex items-center gap-3 py-3">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        {item.kind === 'pot' ? <Wallet className="h-4 w-4" aria-hidden="true" /> : <PiggyBank className="h-4 w-4" aria-hidden="true" />}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <p className="truncate text-sm font-medium">{item.name}</p>
          <p className={`shrink-0 text-sm tabular-nums ${over ? 'text-amber-700 dark:text-amber-300' : ''}`}>
            {item.kind === 'pot'
              ? over
                ? `${formatCurrency((item.spent ?? 0) - item.amount, currency)} over`
                : <><span className="font-semibold">{formatCurrency(item.left ?? 0, currency)}</span><span className="text-muted-foreground"> left of {formatCurrency(item.amount, currency)}</span></>
              : <><span className="font-semibold">{formatCurrency(item.amount, currency)}</span><span className="text-muted-foreground"> saved each pay</span></>}
          </p>
        </div>
        {item.kind === 'pot' ? (
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden="true">
            <div className={`h-full rounded-full ${over ? 'bg-amber-500' : 'bg-primary'}`} style={{ width: `${used * 100}%` }} />
          </div>
        ) : null}
      </div>
      <button type="button" onClick={onRemove} aria-label={`Remove ${item.name}`} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted">
        <Trash2 className="h-4 w-4" />
      </button>
    </li>
  )
}

/** Spending pots and savings held back each pay, plus the spends logged this pay. */
export function SetAsidesCard() {
  const query = useApi<SafeToSpend>(apiKeys.safeToSpend, getSafeToSpend)
  const [adding, setAdding] = useState<Draft | null | false>(false)
  const [logging, setLogging] = useState(false)
  const [showSpends, setShowSpends] = useState(false)
  const position = query.data
  if (!position || position.status === 'needs_setup' || position.safe_to_spend === null) return null

  const currency = position.base_currency ?? 'AUD'
  const setAsides = position.set_asides ?? []
  const pots = setAsides.filter(item => item.kind === 'pot')
  const savings = setAsides.filter(item => item.kind === 'save')
  const spends = position.spends ?? []
  const potNames = new Map(setAsides.map(item => [item.id, item.name]))

  function update(next: SafeToSpend) {
    void query.mutate(next, { revalidate: false })
  }

  async function remove(item: SetAsidePosition) {
    try {
      await deleteSetAside(await token(), item.id)
      await query.mutate()
      toast.success(`${item.name} removed`)
    } catch (error) {
      toast.error(errorMessage(error, 'Could not remove that.'))
    }
  }

  async function undo(id: string) {
    try {
      update(await undoSpend(await token(), id))
    } catch (error) {
      toast.error(errorMessage(error, 'Could not undo that.'))
    }
  }

  return (
    <section className="rounded-2xl bg-card p-5 shadow-sm sm:p-6" aria-labelledby="pots-heading">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id="pots-heading" className="text-[17px] font-semibold">Your pots this pay</h2>
          <p className="mt-1 text-sm text-muted-foreground">Money held back every payday, before you see what&apos;s free.</p>
        </div>
        {setAsides.length > 0 ? (
          <Button size="sm" variant="ghost" onClick={() => setAdding(null)}><Plus className="h-4 w-4" />Add a pot</Button>
        ) : null}
      </div>

      {setAsides.length === 0 ? (
        <div className="mt-5 rounded-xl border border-dashed border-border p-4">
          <p className="text-sm">Hold money back for things you spend on, or for saving. Tap one to start:</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {SUGGESTIONS.map(suggestion => (
              <button
                key={suggestion.name}
                type="button"
                onClick={() => setAdding(suggestion)}
                className="inline-flex min-h-9 items-center gap-1.5 rounded-full border border-border bg-background px-3 text-sm hover:border-primary/40"
              >
                <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                {suggestion.name} ${suggestion.amount}
              </button>
            ))}
            <button type="button" onClick={() => setAdding(null)} className="inline-flex min-h-9 items-center rounded-full px-3 text-sm font-medium text-primary hover:underline">
              Make your own
            </button>
          </div>
        </div>
      ) : (
        <>
          {pots.length > 0 ? (
            <ul className="mt-3 divide-y divide-border" aria-label="Spending pots">
              {pots.map(item => <PotRow key={item.id} item={item} currency={currency} onRemove={() => void remove(item)} />)}
            </ul>
          ) : null}
          {savings.length > 0 ? (
            <ul className="mt-1 divide-y divide-border border-t border-border" aria-label="Savings">
              {savings.map(item => <PotRow key={item.id} item={item} currency={currency} onRemove={() => void remove(item)} />)}
            </ul>
          ) : null}
        </>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-border pt-4">
        <Button variant="outline" onClick={() => setLogging(true)}><Receipt className="h-4 w-4" />Log a spend</Button>
        {spends.length > 0 ? (
          <button
            type="button"
            aria-expanded={showSpends}
            onClick={() => setShowSpends(open => !open)}
            className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            Logged this pay ({spends.length})
            <ChevronDown className={`h-4 w-4 transition-transform ${showSpends ? 'rotate-180' : ''}`} aria-hidden="true" />
          </button>
        ) : (
          <span className="text-xs text-muted-foreground">Optional. Your balance already counts everything you spend.</span>
        )}
      </div>
      {showSpends && spends.length > 0 ? (
        <ul className="mt-2 space-y-1" aria-label="Spends this pay">
          {spends.map(spend => (
            <li key={spend.id} className="flex items-center justify-between gap-3 text-sm">
              <span className="min-w-0 truncate text-muted-foreground">
                {spend.name}{spend.set_aside_id ? ` · ${potNames.get(spend.set_aside_id) ?? 'pot'}` : ' · free to spend'}
              </span>
              <span className="flex shrink-0 items-center gap-2 tabular-nums">
                {formatCurrency(spend.amount, currency)}
                <button type="button" onClick={() => void undo(spend.id)} aria-label={`Undo ${spend.name}`} className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted">
                  <Undo2 className="h-3.5 w-3.5" />
                </button>
              </span>
            </li>
          ))}
        </ul>
      ) : null}

      <Dialog open={adding !== false} onOpenChange={open => { if (!open) setAdding(false) }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>Add a pot</DialogTitle></DialogHeader>
          <DialogDescription>It comes off what&apos;s free to spend every payday.</DialogDescription>
          {adding !== false ? (
            <AddDialog key={adding?.name ?? 'new'} draft={adding} onClose={() => setAdding(false)} onSaved={() => query.mutate()} />
          ) : null}
        </DialogContent>
      </Dialog>
      <Dialog open={logging} onOpenChange={setLogging}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader><DialogTitle>Log a spend</DialogTitle></DialogHeader>
          <DialogDescription>Only if you want to track a pot. Your balance already counts everything.</DialogDescription>
          {logging ? <LogDialog pots={pots} currency={currency} onClose={() => setLogging(false)} onSaved={update} /> : null}
        </DialogContent>
      </Dialog>
    </section>
  )
}
