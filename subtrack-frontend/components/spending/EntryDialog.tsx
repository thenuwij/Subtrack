'use client'

import { useState } from 'react'
import { Mic } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { parseTransactionText } from '@/lib/api'
import type { Category, Currency, Transaction, TransactionInput, TransactionKind } from '@/types'
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
  /** Optional suggestions that prefill a new entry; the user still confirms each one. */
  draft?: TransactionInput[]
  onClose: () => void
  /** `more` is true when further drafts follow, so the caller should keep the dialog open. */
  onSave: (input: TransactionInput, more: boolean) => Promise<void>
}

const KINDS: { value: TransactionKind; label: string }[] = [
  { value: 'expense', label: 'Expense' },
  { value: 'income', label: 'Income' },
]

interface SpeechResult { 0: { transcript: string } }
interface Recognition {
  lang: string
  onresult: ((event: { results: ArrayLike<SpeechResult> }) => void) | null
  onerror: (() => void) | null
  onend: (() => void) | null
  start: () => void
}

function speechRecognitionClass(): (new () => Recognition) | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as Record<string, new () => Recognition>
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

export function EntryDialog({ entry, draft, onClose, onSave }: EntryDialogProps) {
  const { baseCurrency } = useCurrency()
  const [drafts, setDrafts] = useState<TransactionInput[]>(draft ?? [])
  const [draftIndex, setDraftIndex] = useState(0)
  const [listening, setListening] = useState(false)
  const [heard, setHeard] = useState('')
  const canSpeak = !entry && speechRecognitionClass() !== null
  const [kind, setKind] = useState<TransactionKind>(entry?.kind ?? 'expense')
  const [amount, setAmount] = useState(entry ? String(entry.amount) : '')
  const [name, setName] = useState(entry?.name ?? '')
  const [category, setCategory] = useState<Category>(
    entry && entry.kind === 'expense' ? entry.category : 'other',
  )
  const [date, setDate] = useState(entry?.occurred_on.slice(0, 10) ?? todayUtcDateKey())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [currency, setCurrency] = useState<Currency>(entry?.currency ?? baseCurrency)

  function applyDraft(item: TransactionInput) {
    setKind(item.kind)
    setAmount(String(item.amount))
    setName(item.name)
    setCategory(item.kind === 'expense' ? item.category : 'other')
    if (item.occurred_on) setDate(item.occurred_on.slice(0, 10))
    setCurrency(item.currency)
  }

  async function interpret(text: string) {
    try {
      const { data: { session } } = await createClient().auth.getSession()
      if (!session) throw new Error('Please sign in again.')
      const result = await parseTransactionText(session.access_token, text)
      setDrafts(result.drafts)
      setDraftIndex(0)
      applyDraft(result.drafts[0])
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not understand that.')
    }
  }

  function startListening() {
    const Recognition = speechRecognitionClass()
    if (!Recognition) return
    const recognition = new Recognition()
    recognition.lang = 'en-AU'
    setError('')
    setHeard('')
    setListening(true)
    recognition.onresult = event => {
      const text = event.results[0][0].transcript
      setHeard(text)
      void interpret(text)
    }
    recognition.onerror = () => setError('Could not hear that. Try again or type it.')
    recognition.onend = () => setListening(false)
    recognition.start()
  }

  function stepDraft(index: number) {
    setDraftIndex(index)
    applyDraft(drafts[index])
  }

  async function afterSave() {
    if (draftIndex + 1 < drafts.length) {
      stepDraft(draftIndex + 1)
      setSaving(false)
    }
  }

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
      }, draftIndex + 1 < drafts.length)
      await afterSave()
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

          {canSpeak ? (
            <div className="space-y-1.5">
              <Button type="button" variant="outline" onClick={startListening} disabled={listening || saving}>
                <Mic className="h-4 w-4" />{listening ? 'Listening…' : 'Say it'}
              </Button>
              {heard ? <p className="text-sm text-muted-foreground">Heard: &ldquo;{heard}&rdquo;</p> : null}
            </div>
          ) : null}
          {drafts.length > 1 ? (
            <p className="text-sm font-medium">{draftIndex + 1} of {drafts.length}</p>
          ) : null}

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
