'use client'

import { useState, type FormEvent } from 'react'
import { PiggyBank, Plus, Trash2, Undo2, Utensils } from 'lucide-react'
import { toast } from 'sonner'
import type { SafeToSpend, SetAsideKind } from '@/types'
import { createSetAside, deleteSetAside, getSafeToSpend, logSpend, undoSpend } from '@/lib/api'
import { getAccessToken } from '@/lib/auth/session'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { formatCurrency } from '@/lib/utils/currency'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const selectClass = 'h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm'

async function token() {
  const value = await getAccessToken()
  if (!value) throw new Error('Your session has expired.')
  return value
}

function AddSetAside({ onDone }: { onDone: () => Promise<unknown> }) {
  const [kind, setKind] = useState<SetAsideKind>('pot')
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      await createSetAside(await token(), { kind, name: name.trim(), amount_per_pay: Number(amount) })
      setName('')
      setAmount('')
      await onDone()
    } catch (error) {
      toast.error(errorMessage(error, 'Could not add that.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[9rem_1fr_8rem_auto] sm:items-end">
      <div className="space-y-1">
        <Label htmlFor="set-aside-kind" className="text-xs">Type</Label>
        <select id="set-aside-kind" value={kind} onChange={event => setKind(event.target.value as SetAsideKind)} className={selectClass}>
          <option value="pot">Spending pot</option>
          <option value="save">Saving</option>
        </select>
      </div>
      <div className="space-y-1">
        <Label htmlFor="set-aside-name" className="text-xs">Name</Label>
        <Input id="set-aside-name" required maxLength={80} placeholder={kind === 'pot' ? 'Eating out' : 'Trip'} value={name} onChange={event => setName(event.target.value)} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="set-aside-amount" className="text-xs">Each pay</Label>
        <Input id="set-aside-amount" required type="number" step="0.01" min="0.01" inputMode="decimal" value={amount} onChange={event => setAmount(event.target.value)} />
      </div>
      <Button type="submit" disabled={saving}>{saving ? 'Adding…' : 'Add'}</Button>
    </form>
  )
}

function LogSpend({ position, onSaved }: { position: SafeToSpend; onSaved: (next: SafeToSpend) => void }) {
  const pots = (position.set_asides ?? []).filter(item => item.kind === 'pot')
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [from, setFrom] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      onSaved(await logSpend(await token(), { name: name.trim(), amount: Number(amount), set_aside_id: from || null }))
      setName('')
      setAmount('')
    } catch (error) {
      toast.error(errorMessage(error, 'Could not log that.'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[1fr_7rem_10rem_auto] sm:items-end">
      <div className="space-y-1">
        <Label htmlFor="spend-name" className="text-xs">What</Label>
        <Input id="spend-name" required maxLength={200} placeholder="Dinner with friends" value={name} onChange={event => setName(event.target.value)} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="spend-amount" className="text-xs">Amount</Label>
        <Input id="spend-amount" required type="number" step="0.01" min="0.01" inputMode="decimal" value={amount} onChange={event => setAmount(event.target.value)} />
      </div>
      <div className="space-y-1">
        <Label htmlFor="spend-from" className="text-xs">From</Label>
        <select id="spend-from" value={from} onChange={event => setFrom(event.target.value)} className={selectClass}>
          <option value="">Free to spend</option>
          {pots.map(pot => <option key={pot.id} value={pot.id}>{pot.name}</option>)}
        </select>
      </div>
      <Button type="submit" variant="outline" disabled={saving}>{saving ? 'Saving…' : 'Log'}</Button>
    </form>
  )
}

/** Savings and spending pots taken off each pay, plus spends logged this cycle. */
export function SetAsidesCard() {
  const query = useApi<SafeToSpend>(apiKeys.safeToSpend, getSafeToSpend)
  const [adding, setAdding] = useState(false)
  const position = query.data
  if (!position || position.status === 'needs_setup' || position.safe_to_spend === null) return null

  const currency = position.base_currency ?? 'AUD'
  const setAsides = position.set_asides ?? []
  const spends = position.spends ?? []
  const potNames = new Map(setAsides.map(item => [item.id, item.name]))

  function update(next: SafeToSpend) {
    void query.mutate(next, { revalidate: false })
  }

  async function remove(id: string, name: string) {
    try {
      await deleteSetAside(await token(), id)
      await query.mutate()
      toast.success(`${name} removed`)
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
    <section className="rounded-2xl bg-card p-5 shadow-sm sm:p-6" aria-labelledby="set-asides-heading">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 id="set-asides-heading" className="text-[17px] font-semibold">Set aside each pay</h2>
          <p className="mt-1 text-sm text-muted-foreground">Taken off what&apos;s free to spend, every payday.</p>
        </div>
        <button type="button" onClick={() => setAdding(open => !open)} className="flex shrink-0 items-center gap-1 text-sm font-medium text-primary hover:underline">
          <Plus className="h-4 w-4" aria-hidden="true" />{adding ? 'Close' : 'Add'}
        </button>
      </div>

      {adding ? <div className="mt-4"><AddSetAside onDone={async () => { setAdding(false); await query.mutate() }} /></div> : null}

      {setAsides.length === 0 && !adding ? (
        <p className="mt-4 text-sm text-muted-foreground">
          Add a spending pot like &ldquo;Eating out, $60 a pay&rdquo; or a saving like &ldquo;Trip, $100 a pay&rdquo;.
        </p>
      ) : null}

      {setAsides.length > 0 ? (
        <ul className="mt-4 divide-y divide-border">
          {setAsides.map(item => {
            const Icon = item.kind === 'pot' ? Utensils : PiggyBank
            const usedShare = item.kind === 'pot' && item.amount > 0 ? Math.min(1, (item.spent ?? 0) / item.amount) : 0
            return (
              <li key={item.id} className="flex items-center gap-3 py-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary"><Icon className="h-4 w-4" aria-hidden="true" /></span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-3">
                    <p className="truncate text-sm font-medium">{item.name}</p>
                    <p className="shrink-0 text-sm tabular-nums">
                      {item.kind === 'pot'
                        ? `${formatCurrency(item.left ?? 0, currency)} left of ${formatCurrency(item.amount, currency)}`
                        : `${formatCurrency(item.amount, currency)} saved each pay`}
                    </p>
                  </div>
                  {item.kind === 'pot' ? (
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted" aria-hidden="true">
                      <div className={`h-full rounded-full ${usedShare >= 1 ? 'bg-amber-500' : 'bg-primary'}`} style={{ width: `${usedShare * 100}%` }} />
                    </div>
                  ) : null}
                </div>
                <button type="button" onClick={() => void remove(item.id, item.name)} aria-label={`Remove ${item.name}`} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted">
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            )
          })}
        </ul>
      ) : null}

      <div className="mt-5 border-t border-border pt-4">
        <h3 className="text-sm font-semibold">Spent something?</h3>
        <p className="mt-0.5 mb-3 text-xs text-muted-foreground">Only if you want to. It comes off a pot, or off what&apos;s free.</p>
        <LogSpend position={position} onSaved={update} />
        {spends.length > 0 ? (
          <ul className="mt-3 space-y-1" aria-label="Spends this pay cycle">
            {spends.map(spend => (
              <li key={spend.id} className="flex items-center justify-between gap-3 text-sm">
                <span className="min-w-0 truncate text-muted-foreground">
                  {spend.name}{spend.set_aside_id ? ` · ${potNames.get(spend.set_aside_id) ?? 'pot'}` : ''}
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
      </div>
    </section>
  )
}
