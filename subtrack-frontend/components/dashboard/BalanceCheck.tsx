'use client'

import { useEffect, useState, type FormEvent } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import type { SafeToSpend } from '@/types'
import { getSafeToSpend, saveSafeToSpendProfile, trackEvent } from '@/lib/api'
import { getAccessToken } from '@/lib/auth/session'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

/** One field, opened from the payday email: today's balance, then Home. */
export function BalanceCheck() {
  const router = useRouter()
  const query = useApi<SafeToSpend>(apiKeys.safeToSpend, getSafeToSpend)
  const [value, setValue] = useState('')
  const [saving, setSaving] = useState(false)
  const position = query.data
  const profile = position?.profile

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('from') === 'payday') trackEvent('payday_link_clicked')
  }, [])

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!profile || !position?.next_payday || value.trim() === '') return
    setSaving(true)
    try {
      const token = await getAccessToken()
      if (!token) throw new Error('Your session has expired.')
      const next = await saveSafeToSpendProfile(token, {
        balance: Number(value),
        pay_amount: profile.pay_amount,
        currency: profile.currency,
        next_payday: position.next_payday,
        pay_interval_unit: profile.pay_interval_unit,
        pay_interval_count: profile.pay_interval_count,
        buffer: profile.buffer,
        payday_bills_after_pay: profile.payday_bills_after_pay,
      })
      await query.mutate(next, { revalidate: false })
      router.push('/dashboard')
    } catch (error) {
      toast.error(errorMessage(error, 'Could not save your balance.'))
      setSaving(false)
    }
  }

  if (query.error && !position) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 sm:px-6">
        <p className="text-sm text-muted-foreground">We couldn&apos;t load your details.</p>
        <Button className="mt-4" variant="outline" onClick={() => void query.mutate()}>Try again</Button>
      </div>
    )
  }
  if (!position) return <div className="mx-auto mt-16 h-40 max-w-md animate-pulse rounded-2xl bg-card" aria-label="Loading" />
  if (!profile) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 sm:px-6">
        <h1 className="text-2xl font-semibold tracking-tight">Set up your payday first</h1>
        <Button asChild className="mt-6"><Link href="/setup">Set up</Link></Button>
      </div>
    )
  }

  return (
    <form onSubmit={save} className="mx-auto max-w-md space-y-6 px-4 py-16 sm:px-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">What&apos;s in your account today?</h1>
        <p className="mt-2 text-muted-foreground">Your everyday account. This makes what&apos;s free to spend exact.</p>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="balance-today">Today&apos;s balance ({profile.currency})</Label>
        <Input id="balance-today" type="number" step="0.01" inputMode="decimal" required autoFocus value={value} onChange={event => setValue(event.target.value)} />
      </div>
      <Button type="submit" size="lg" disabled={saving}>{saving ? 'Saving…' : 'See what I can spend'}</Button>
    </form>
  )
}
