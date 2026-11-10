'use client'

import { useState, type FormEvent } from 'react'
import Link from 'next/link'
import { ArrowLeft, CheckCircle2, XCircle } from 'lucide-react'
import { toast } from 'sonner'
import { canIAfford, type AffordAnswer } from '@/lib/api'
import { getAccessToken } from '@/lib/auth/session'
import { useCurrency } from '@/lib/context/currency'
import { errorMessage } from '@/lib/hooks/useApi'
import { formatCurrency } from '@/lib/utils/currency'
import { formatStoredDate } from '@/lib/utils/dates'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

/** One field, opened from the home-screen shortcut: can I afford this before payday? */
export function AffordCheck() {
  const { baseCurrency } = useCurrency()
  const [value, setValue] = useState('')
  const [checking, setChecking] = useState(false)
  const [answer, setAnswer] = useState<AffordAnswer | null>(null)

  async function check(event: FormEvent) {
    event.preventDefault()
    setChecking(true)
    try {
      const token = await getAccessToken()
      if (!token) throw new Error('Your session has expired.')
      setAnswer(await canIAfford(token, Number(value)))
    } catch (error) {
      toast.error(errorMessage(error, 'Could not check that.'))
    } finally {
      setChecking(false)
    }
  }

  const currency = answer?.base_currency ?? baseCurrency
  const payday = answer?.next_payday
    ? formatStoredDate(answer.next_payday, { weekday: 'short', day: 'numeric', month: 'short' })
    : 'payday'

  return (
    <div className="mx-auto max-w-md space-y-6 px-4 py-16 sm:px-6">
      <form onSubmit={check} className="space-y-6">
        <Link href="/dashboard" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="h-4 w-4" />Home</Link>
        <h1 className="text-3xl font-semibold tracking-tight">Can I afford it?</h1>
        <div className="space-y-1.5">
          <Label htmlFor="afford-amount">How much?</Label>
          <Input
            id="afford-amount"
            type="number"
            step="0.01"
            min="0.01"
            inputMode="decimal"
            required
            autoFocus
            value={value}
            onChange={event => { setValue(event.target.value); setAnswer(null) }}
          />
        </div>
        <Button type="submit" size="lg" disabled={checking}>{checking ? 'Checking…' : 'Check'}</Button>
      </form>

      {answer ? (
        <section aria-live="polite" className="rounded-2xl bg-card p-5 shadow-sm">
          {answer.affordable === null ? (
            <>
              <p className="font-medium">We can&apos;t answer that yet.</p>
              {answer.warnings?.map(warning => <p key={warning} className="mt-1 text-sm text-muted-foreground">{warning}</p>)}
              <Button asChild variant="outline" className="mt-4"><Link href={answer.status === 'needs_setup' ? '/setup' : '/balance'}>
                {answer.status === 'needs_setup' ? 'Set up your payday' : 'Add today’s balance'}
              </Link></Button>
            </>
          ) : answer.affordable ? (
            <div className="flex gap-3">
              <CheckCircle2 className="mt-0.5 h-6 w-6 shrink-0 text-emerald-600" aria-hidden="true" />
              <div>
                <p className="text-lg font-semibold">Yes, it fits.</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  You&apos;d have {formatCurrency(answer.left_after ?? 0, currency)} left until {payday}
                  {answer.per_day_after != null ? `, about ${formatCurrency(answer.per_day_after, currency)} a day` : ''}.
                </p>
              </div>
            </div>
          ) : (
            <div className="flex gap-3">
              <XCircle className="mt-0.5 h-6 w-6 shrink-0 text-amber-600" aria-hidden="true" />
              <div>
                <p className="text-lg font-semibold">Not before {payday}.</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  You&apos;d be {formatCurrency(answer.short_by ?? 0, currency)} short after bills and what you&apos;ve set aside.
                </p>
              </div>
            </div>
          )}
          {answer.affordable !== null && answer.mode === 'estimate' ? (
            <p className="mt-3 text-xs text-muted-foreground">
              Estimate from your usual pay. <Link href="/balance" className="text-primary hover:underline">Add today&apos;s balance</Link> for an exact answer.
            </p>
          ) : null}
        </section>
      ) : null}
    </div>
  )
}
