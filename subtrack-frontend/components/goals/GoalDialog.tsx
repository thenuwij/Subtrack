'use client'

import { useState } from 'react'
import type { Currency, Goal } from '@/types'
import { useCurrency } from '@/lib/context/currency'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'

interface GoalDialogProps {
  /** The goal being edited, or null to create one. */
  goal: Goal | null
  onClose: () => void
  onSave: (input: { name: string; target_amount: number; currency: Currency; target_date: string | null }) => Promise<void>
}

export function GoalDialog({ goal, onClose, onSave }: GoalDialogProps) {
  const { baseCurrency } = useCurrency()
  const [name, setName] = useState(goal?.name ?? '')
  const [target, setTarget] = useState(goal ? String(goal.target_amount) : '')
  const [date, setDate] = useState(goal?.target_date?.slice(0, 10) ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const currency = goal?.currency ?? baseCurrency

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const value = Number(target)
    if (!name.trim()) return setError('Give this goal a name.')
    if (!Number.isFinite(value) || value <= 0) return setError('Enter a target above zero.')
    setSaving(true)
    setError('')
    try {
      await onSave({
        name: name.trim(),
        target_amount: Math.round(value * 100) / 100,
        currency,
        target_date: date || null,
      })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save this goal.')
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={open => { if (!open && !saving) onClose() }}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-md">
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{goal ? 'Edit goal' : 'New goal'}</DialogTitle>
            <DialogDescription>Something you are saving up for.</DialogDescription>
          </DialogHeader>

          <div className="space-y-1.5">
            <Label htmlFor="goal-name">Name</Label>
            <Input id="goal-name" maxLength={120} autoFocus placeholder="Holiday fund"
              value={name} onChange={event => setName(event.target.value)} />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="goal-target">Target ({currency})</Label>
            <Input id="goal-target" inputMode="decimal" type="number" step="0.01" min="0"
              placeholder="2000.00" value={target} onChange={event => setTarget(event.target.value)} />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="goal-date">Target date (optional)</Label>
            <Input id="goal-date" type="date" value={date} onChange={event => setDate(event.target.value)} />
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
