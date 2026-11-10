'use client'

import { useState } from 'react'
import Link from 'next/link'
import { X } from 'lucide-react'
import type { PayCycles } from '@/types'
import { getPayCycles } from '@/lib/api'
import { apiKeys, useApi } from '@/lib/hooks/useApi'
import { formatCurrency } from '@/lib/utils/currency'

const SHOW_FOR_DAYS = 3

function dismissedKey(start: string) {
  return `subtrack:payday-banner:${start}`
}

/** For the first few days of a new pay cycle: how the last one went, with a link to the details. */
export function PaydayBanner() {
  const query = useApi<PayCycles>(apiKeys.payCycles(1), token => getPayCycles(token, 1))
  const [hidden, setHidden] = useState(false)
  const [openedAt] = useState(() => Date.now())
  const [current, previous] = query.data?.cycles ?? []
  if (!current || !previous || hidden) return null
  const daysIn = (openedAt - new Date(`${current.start}T00:00:00`).getTime()) / 86_400_000
  if (daysIn > SHOW_FOR_DAYS) return null
  try {
    if (localStorage.getItem(dismissedKey(current.start))) return null
  } catch {
    // Storage can be blocked; the banner just shows until dismissed this visit.
  }
  if (previous.pots.length === 0 && previous.saved === 0 && previous.spends.length === 0) return null

  const currency = query.data?.base_currency ?? 'AUD'
  const summary = [
    ...previous.pots.map(pot => `${pot.name} ${formatCurrency(pot.spent, currency)} of ${formatCurrency(pot.planned ?? 0, currency)}`),
    ...(previous.saved ? [`saved ${formatCurrency(previous.saved, currency)}`] : []),
  ].join(' · ')

  function dismiss() {
    setHidden(true)
    try {
      localStorage.setItem(dismissedKey(current.start), '1')
    } catch {
      // Ignore blocked storage.
    }
  }

  return (
    <section className="flex items-start justify-between gap-3 rounded-2xl bg-primary/5 p-4 ring-1 ring-primary/15">
      <div className="text-sm">
        <p className="font-semibold">New pay cycle. Your pots are full again.</p>
        {summary ? <p className="mt-1 text-muted-foreground">Last pay: {summary}</p> : null}
        <Link href="/cycles" className="mt-2 inline-block font-medium text-primary hover:underline">See how it went</Link>
      </div>
      <button type="button" onClick={dismiss} aria-label="Dismiss" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-muted">
        <X className="h-4 w-4" />
      </button>
    </section>
  )
}
