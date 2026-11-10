'use client'

import { useState } from 'react'
import type { BudgetStatus, Category } from '@/types'
import { spendingCategoryLabel } from '@/lib/utils/spending'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'

interface BudgetDialogProps {
  /** The budget being edited, or null to add one. */
  budget: BudgetStatus | null
  /** Categories that don't have a budget yet. */
  freeCategories: Category[]
  currency: string
  onClose: () => void
  onSave: (input: { category: Category; monthly_limit: number }) => Promise<void>
  onRemove: (id: string) => Promise<void>
}

export function BudgetDialog({ budget, freeCategories, currency, onClose, onSave, onRemove }: BudgetDialogProps) {
  const [category, setCategory] = useState<Category>(budget?.category ?? freeCategories[0])
  const [limit, setLimit] = useState(budget ? String(budget.monthly_limit) : '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function run(action: () => Promise<void>, fallback: string) {
    setSaving(true)
    setError('')
    try {
      await action()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : fallback)
      setSaving(false)
    }
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const value = Number(limit)
    if (!Number.isFinite(value) || value <= 0) return setError('Enter a limit above zero.')
    void run(() => onSave({ category, monthly_limit: Math.round(value * 100) / 100 }), 'Could not save this budget.')
  }

  return (
    <Dialog open onOpenChange={open => { if (!open && !saving) onClose() }}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-md">
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{budget ? `${spendingCategoryLabel(budget.category)} budget` : 'Add a budget'}</DialogTitle>
            <DialogDescription>How much you want to spend on this category each month.</DialogDescription>
          </DialogHeader>

          {budget ? null : (
            <div className="space-y-1.5">
              <Label htmlFor="budget-category">Category</Label>
              <select id="budget-category" value={category} onChange={event => setCategory(event.target.value as Category)}
                className="h-11 w-full rounded-xl border border-input bg-transparent px-2.5 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 md:text-sm dark:bg-input/30">
                {freeCategories.map(option => (
                  <option key={option} value={option} className="bg-popover text-foreground">{spendingCategoryLabel(option)}</option>
                ))}
              </select>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="budget-limit">Monthly limit ({currency})</Label>
            <Input id="budget-limit" inputMode="decimal" type="number" step="0.01" min="0" autoFocus
              placeholder="400.00" value={limit} onChange={event => setLimit(event.target.value)} />
          </div>

          {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}

          <DialogFooter className="gap-2">
            {budget ? (
              <Button type="button" variant="ghost" disabled={saving}
                onClick={() => void run(() => onRemove(budget.id), 'Could not remove this budget.')}>Remove</Button>
            ) : null}
            <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>Cancel</Button>
            <Button type="submit" disabled={saving}>{saving ? 'Saving…' : 'Save'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
