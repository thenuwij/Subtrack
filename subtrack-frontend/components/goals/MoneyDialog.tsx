'use client'

import { useState } from 'react'
import type { ContributionInput, Goal } from '@/types'
import { todayUtcDateKey } from '@/lib/utils/dates'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'

interface MoneyDialogProps {
  goal: Goal
  /** Put money in, or take it back out. */
  mode: 'add' | 'remove'
  onClose: () => void
  onSave: (input: ContributionInput) => Promise<void>
}

export function MoneyDialog({ goal, mode, onClose, onSave }: MoneyDialogProps) {
  const adding = mode === 'add'
  const [amount, setAmount] = useState('')
  const [date, setDate] = useState(todayUtcDateKey())
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const value = Number(amount)
    if (!Number.isFinite(value) || value <= 0) return setError('Enter an amount above zero.')
    setSaving(true)
    setError('')
    try {
      const rounded = Math.round(value * 100) / 100
      await onSave({
        amount: adding ? rounded : -rounded,
        occurred_on: date,
        note: note.trim() || null,
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save this.')
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={open => { if (!open && !saving) onClose() }}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-md">
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{adding ? 'Add money' : 'Take money out'}</DialogTitle>
            <DialogDescription>{goal.name}</DialogDescription>
          </DialogHeader>

          <div className="space-y-1.5">
            <Label htmlFor="money-amount">Amount ({goal.currency})</Label>
            <Input id="money-amount" inputMode="decimal" type="number" step="0.01" min="0" autoFocus
              placeholder="0.00" value={amount} onChange={event => setAmount(event.target.value)} />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="money-date">Date</Label>
            <Input id="money-date" type="date" value={date} onChange={event => setDate(event.target.value)} />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="money-note">Note (optional)</Label>
            <Input id="money-note" maxLength={500} value={note} onChange={event => setNote(event.target.value)} />
          </div>

          {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}

          <DialogFooter className="gap-2">
            <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>Cancel</Button>
            <Button type="submit" disabled={saving}>{saving ? 'Saving…' : adding ? 'Add' : 'Take out'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
