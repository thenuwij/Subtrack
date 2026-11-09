'use client'

import { useState } from 'react'
import type { Category, Transaction, TransactionInput, TransactionKind } from '@/types'
import { useCurrency } from '@/lib/context/currency'
import { todayUtcDateKey } from '@/lib/utils/dates'
import { EXPENSE_CATEGORIES, spendingCategoryLabel } from '@/lib/utils/spending'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'

interface EntryDialogProps {
  /** The entry being edited, or null to add a new one. */
  entry: Transaction | null
  onClose: () => void
  onSave: (input: TransactionInput) => Promise<void>
}

const KINDS: { value: TransactionKind; label: string }[] = [
  { value: 'expense', label: 'Expense' },
  { value: 'income', label: 'Income' },
]

export function EntryDialog({ entry, onClose, onSave }: EntryDialogProps) {
  const { baseCurrency } = useCurrency()
  const [kind, setKind] = useState<TransactionKind>(entry?.kind ?? 'expense')
  const [amount, setAmount] = useState(entry ? String(entry.amount) : '')
  const [name, setName] = useState(entry?.name ?? '')
  const [category, setCategory] = useState<Category>(
    entry && entry.kind === 'expense' ? entry.category : 'other',
  )
  const [date, setDate] = useState(entry?.occurred_on.slice(0, 10) ?? todayUtcDateKey())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const currency = entry?.currency ?? baseCurrency

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const value = Number(amount)
    if (!name.trim()) return setError('Give this entry a name.')
    if (!Number.isFinite(value) || value <= 0) return setError('Enter an amount above zero.')
    setSaving(true)
    setError('')
    try {
      await onSave({
        kind,
        name: name.trim(),
        amount: Math.round(value * 100) / 100,
        currency,
        category: kind === 'income' ? 'income' : category,
        occurred_on: date,
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save this entry.')
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={open => { if (!open && !saving) onClose() }}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-md">
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{entry ? 'Edit entry' : 'Add an entry'}</DialogTitle>
            <DialogDescription>Money you spent or money that came in.</DialogDescription>
          </DialogHeader>

          <div role="group" aria-label="Kind" className="grid grid-cols-2 gap-1 rounded-xl bg-muted p-1">
            {KINDS.map(option => (
              <button key={option.value} type="button" aria-pressed={kind === option.value}
                onClick={() => setKind(option.value)}
                className={`min-h-10 rounded-lg text-sm font-medium transition-colors ${kind === option.value ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>
                {option.label}
              </button>
            ))}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="entry-amount">Amount ({currency})</Label>
            <Input id="entry-amount" inputMode="decimal" type="number" step="0.01" min="0" autoFocus
              placeholder="0.00" value={amount} onChange={event => setAmount(event.target.value)} />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="entry-name">Name</Label>
            <Input id="entry-name" maxLength={200} placeholder={kind === 'income' ? 'Salary' : 'Lunch'}
              value={name} onChange={event => setName(event.target.value)} />
          </div>

          {kind === 'expense' ? (
            <div className="space-y-1.5">
              <Label htmlFor="entry-category">Category</Label>
              <select id="entry-category" value={category} onChange={event => setCategory(event.target.value as Category)}
                className="h-11 w-full rounded-xl border border-input bg-transparent px-2.5 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 md:text-sm dark:bg-input/30">
                {EXPENSE_CATEGORIES.map(option => (
                  <option key={option} value={option} className="bg-popover text-foreground">{spendingCategoryLabel(option)}</option>
                ))}
              </select>
            </div>
          ) : null}

          <div className="space-y-1.5">
            <Label htmlFor="entry-date">Date</Label>
            <Input id="entry-date" type="date" value={date} onChange={event => setDate(event.target.value)} />
          </div>

          {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}

          <DialogFooter className="gap-2">
            <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>Cancel</Button>
            <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
