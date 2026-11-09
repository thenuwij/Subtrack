'use client'

import { useState } from 'react'
import { ChevronLeft, ChevronRight, Plus, Wallet } from 'lucide-react'
import { useSWRConfig } from 'swr'
import { toast } from 'sonner'
import {
  createTransaction,
  deleteTransaction,
  getTransactionSummary,
  listTransactions,
  updateTransaction,
} from '@/lib/api'
import { getAccessToken } from '@/lib/auth/session'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { formatCurrency } from '@/lib/utils/currency'
import { categoryColor } from '@/lib/utils/categories'
import { formatStoredDate, todayUtcDateKey } from '@/lib/utils/dates'
import {
  currentMonthKey, monthLabel, shiftMonth, spendingCategoryLabel,
} from '@/lib/utils/spending'
import type { CreatedTransaction, PossibleDuplicate, Transaction, TransactionInput } from '@/types'
import { EntryDialog } from '@/components/spending/EntryDialog'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

interface DuplicateNotice {
  entry: Transaction
  match: PossibleDuplicate
}

export default function SpendingPage() {
  const { mutate } = useSWRConfig()
  const thisMonth = currentMonthKey(todayUtcDateKey())
  const [month, setMonth] = useState(thisMonth)
  const [dialog, setDialog] = useState<{ entry: Transaction | null } | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [notice, setNotice] = useState<DuplicateNotice | null>(null)

  const listQuery = useApi(apiKeys.transactions(month), token => listTransactions(token, month))
  const summaryQuery = useApi(apiKeys.transactionSummary(month), token => getTransactionSummary(token, month))
  const entries = listQuery.data ?? []
  const summary = summaryQuery.data
  const loadError = errorMessage(listQuery.error ?? summaryQuery.error, 'Could not load your spending.')

  function showMonth(next: string) {
    setMonth(next)
    setNotice(null)
  }

  async function refresh() {
    await mutate(key => typeof key === 'string'
      && (key.startsWith('transactions:') || key.startsWith('transaction-summary:')))
  }

  async function authToken() {
    const token = await getAccessToken()
    if (!token) throw new Error('Your session has expired. Sign in again.')
    return token
  }

  async function handleSave(input: TransactionInput) {
    const token = await authToken()
    const editing = dialog?.entry ?? null
    if (editing) {
      const updated = await updateTransaction(token, editing.id, input)
      showMonth(updated.occurred_on.slice(0, 7))
      toast.success('Entry updated')
    } else {
      const created: CreatedTransaction = await createTransaction(token, input)
      const match = created.possible_duplicates[0]
      showMonth(created.occurred_on.slice(0, 7))
      setNotice(match ? { entry: created, match } : null)
      if (!match) toast.success('Entry added')
    }
    setDialog(null)
    await refresh()
  }

  async function handleDelete(id: string) {
    try {
      await deleteTransaction(await authToken(), id)
      if (notice?.entry.id === id) setNotice(null)
      toast.success('Entry removed')
      await refresh()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not remove this entry.')
    } finally {
      setDeletingId(null)
    }
  }

  const categories = Object.entries(summary?.expenses_by_category ?? {})
  const topCategory = Math.max(...categories.map(([, total]) => total), 0)
  const money = (value: number | undefined) =>
    summary && value !== undefined ? formatCurrency(value, summary.base_currency) : '—'

  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-8 sm:px-8 sm:py-10">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow mb-2">Spending</p>
          <h1 className="page-heading">Money in and out</h1>
        </div>
        <Button onClick={() => setDialog({ entry: null })}><Plus className="h-4 w-4" />Add entry</Button>
      </header>

      <div className="mt-6 flex items-center justify-between rounded-xl bg-card px-1 shadow-sm">
        <Button variant="ghost" size="icon" aria-label="Previous month" onClick={() => showMonth(shiftMonth(month, -1))}><ChevronLeft className="h-4 w-4" /></Button>
        <p className="text-sm font-semibold" aria-live="polite">{monthLabel(month)}</p>
        <Button variant="ghost" size="icon" aria-label="Next month" disabled={month >= thisMonth} onClick={() => showMonth(shiftMonth(month, 1))}><ChevronRight className="h-4 w-4" /></Button>
      </div>

      {loadError ? (
        <div className="mt-6 flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">{loadError}</p>
          <Button variant="outline" size="sm" onClick={() => void refresh()}>Try again</Button>
        </div>
      ) : null}

      <dl className="mt-6 grid grid-cols-3 gap-3 rounded-2xl bg-card p-5 shadow-sm">
        {[
          { label: 'Money in', value: summary?.income },
          { label: 'Money out', value: summary?.expenses },
          { label: 'Left over', value: summary?.net },
        ].map(({ label, value }) => (
          <div key={label} className="min-w-0">
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="mt-1 truncate text-base font-semibold tabular-nums sm:text-xl">
              {summaryQuery.isLoading ? <Skeleton className="h-6 w-20" /> : money(value)}
            </dd>
          </div>
        ))}
      </dl>
      {summary && summary.unconverted_count > 0 ? (
        <p className="mt-2 text-xs text-muted-foreground">
          {summary.unconverted_count === 1
            ? "1 entry in another currency isn't included yet."
            : `${summary.unconverted_count} entries in other currencies aren't included yet.`}
        </p>
      ) : null}

      {categories.length > 0 ? (
        <section aria-label="Spending by category" className="mt-8">
          <h2 className="text-sm font-semibold">Where it went</h2>
          <ul className="mt-3 space-y-3">
            {categories.map(([category, total]) => (
              <li key={category}>
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span>{spendingCategoryLabel(category)}</span>
                  <span className="tabular-nums text-muted-foreground">{money(total)}</span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full" style={{ width: `${Math.max(4, (total / topCategory) * 100)}%`, background: categoryColor(category) }} />
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section aria-label="Entries" className="mt-8">
        <h2 className="text-sm font-semibold">Entries</h2>
        {notice ? (
          <div role="status" className="mt-3 rounded-xl border border-border bg-muted/50 p-4">
            <p className="text-sm text-foreground">
              Looks like {notice.match.name} {formatCurrency(notice.match.amount, notice.match.currency)}
              {notice.match.occurred_on ? ` on ${formatStoredDate(notice.match.occurred_on, { day: 'numeric', month: 'short' })}` : ''}
              {' '}— keep both or remove this one.
            </p>
            <div className="mt-3 flex gap-2">
              <Button size="sm" variant="outline" onClick={() => setNotice(null)}>Keep</Button>
              <Button size="sm" variant="destructive" onClick={() => void handleDelete(notice.entry.id)}>Remove</Button>
            </div>
          </div>
        ) : null}

        {listQuery.isLoading ? (
          <div className="mt-3 space-y-2"><Skeleton className="h-14" /><Skeleton className="h-14" /><Skeleton className="h-14" /></div>
        ) : entries.length === 0 && !loadError ? (
          <div className="mt-3 rounded-2xl bg-card p-8 text-center shadow-sm">
            <Wallet className="mx-auto h-6 w-6 text-muted-foreground" />
            <p className="mt-3 text-sm text-muted-foreground">Nothing logged for {monthLabel(month)} yet.</p>
            <Button className="mt-4" onClick={() => setDialog({ entry: null })}>Add your first entry</Button>
            <p className="mt-3 text-xs text-muted-foreground">You can also tell the assistant, like &ldquo;I spent $20 on lunch&rdquo;.</p>
          </div>
        ) : (
          <ul className="mt-3 divide-y divide-border overflow-hidden rounded-2xl bg-card shadow-sm">
            {entries.map(entry => (
              <li key={entry.id} className="flex items-center gap-2 pr-2">
                <button type="button" onClick={() => setDialog({ entry })}
                  className="flex min-h-14 min-w-0 flex-1 items-center justify-between gap-3 px-4 py-2 text-left hover:bg-muted/40">
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">{entry.name}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {spendingCategoryLabel(entry.category)} · {formatStoredDate(entry.occurred_on, { day: 'numeric', month: 'short' })}
                    </span>
                  </span>
                  <span className={`shrink-0 text-sm font-semibold tabular-nums ${entry.kind === 'income' ? 'text-primary' : ''}`}>
                    {entry.kind === 'income' ? '+' : ''}{formatCurrency(entry.amount, entry.currency)}
                  </span>
                </button>
                {deletingId === entry.id ? (
                  <span className="flex shrink-0 gap-1">
                    <Button size="sm" variant="destructive" onClick={() => void handleDelete(entry.id)}>Delete</Button>
                    <Button size="sm" variant="ghost" onClick={() => setDeletingId(null)}>Cancel</Button>
                  </span>
                ) : (
                  <Button size="sm" variant="ghost" aria-label={`Delete ${entry.name}`} onClick={() => setDeletingId(entry.id)}>Delete</Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {dialog ? <EntryDialog entry={dialog.entry} onClose={() => setDialog(null)} onSave={handleSave} /> : null}
    </div>
  )
}
