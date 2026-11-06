'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ChevronDown } from 'lucide-react'
import type { DetectedSubscription, GmailStatus, SubscriptionForecast } from '@/types'

interface Props {
  detections: DetectedSubscription[]
  forecast: SubscriptionForecast | null
  gmail: GmailStatus | null
  gmailScanStale: boolean
}

export function NeedsAttention({ detections, forecast, gmail, gmailScanStale }: Props) {
  const uncertainDetections = detections.filter(item =>
    item.confidence !== 'high'
    || item.cadence_confidence !== 'high'
    || (item.next_due !== null && item.due_date_confidence !== 'high')
    || (item.next_due === null && !item.cancelled && !item.trial_ends_at)
  ).length
  const unknownTrialPrices = detections.filter(item =>
    Boolean(item.trial_ends_at) && item.amount <= 0 && !item.cancelled
  ).length
  const missingDates = forecast?.missing_due_date_count ?? 0
  const unconverted = forecast?.unconverted_occurrence_count ?? 0
  const pausedWithoutResume = forecast?.paused_without_resume_count ?? 0
  const estimatedPayments = new Set(
    forecast?.charges
      .filter(charge => charge.charge_amount_is_estimate)
      .map(charge => charge.id) ?? [],
  ).size
  const scanIsPartial = Boolean(gmail?.connected && gmail.scan_partial)
  const [open, setOpen] = useState(false)
  const count = [
    uncertainDetections, unknownTrialPrices, missingDates, pausedWithoutResume,
    unconverted, estimatedPayments, scanIsPartial || gmailScanStale,
  ].filter(Boolean).length

  if (!uncertainDetections && !unknownTrialPrices && !missingDates
      && !unconverted && !pausedWithoutResume && !estimatedPayments
      && !gmailScanStale && !scanIsPartial) {
    return null
  }

  return (
    <section className="rounded-2xl bg-card px-5 py-2 shadow-sm sm:px-6" aria-labelledby="needs-attention-heading">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="needs-attention-list"
        onClick={() => setOpen(value => !value)}
        className="flex min-h-11 w-full items-center gap-3 py-2 text-left"
      >
        <span className="flex h-6 min-w-6 items-center justify-center rounded-full bg-muted px-1.5 text-[13px] font-semibold tabular-nums text-foreground">
          {count}
        </span>
        <h2 id="needs-attention-heading" className="flex-1 text-[15px] font-medium text-foreground">
          {count === 1 ? 'Thing needs' : 'Things need'} your attention
        </h2>
        <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      <ul id="needs-attention-list" hidden={!open} className="divide-y divide-border border-t border-border pb-1 text-[15px]">
        {uncertainDetections > 0 ? (
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-muted-foreground/60" aria-hidden="true" />
              Check the frequency or next date on {uncertainDetections} inbox finding{uncertainDetections === 1 ? '' : 's'}.
            </span>
            <Link href="/review" className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted">Review</Link>
          </li>
        ) : null}
        {unknownTrialPrices > 0 ? (
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-muted-foreground/60" aria-hidden="true" />
              Add the post-trial price for {unknownTrialPrices} free trial{unknownTrialPrices === 1 ? '' : 's'}.
            </span>
            <Link href="/review" className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted">Review</Link>
          </li>
        ) : null}
        {missingDates > 0 ? (
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-muted-foreground/60" aria-hidden="true" />
              {missingDates} current payment{missingDates === 1 ? '' : 's'} need a next expected date.
            </span>
            <Link href="/subscriptions" className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted">Payments</Link>
          </li>
        ) : null}
        {pausedWithoutResume > 0 ? (
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-muted-foreground/60" aria-hidden="true" />
              {pausedWithoutResume} paused payment{pausedWithoutResume === 1 ? ' has' : 's have'} no resume date.
            </span>
            <Link href="/subscriptions" className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted">Payments</Link>
          </li>
        ) : null}
        {unconverted > 0 ? (
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-muted-foreground/60" aria-hidden="true" />
              {unconverted} upcoming occurrence{unconverted === 1 ? '' : 's'} cannot be converted to your base currency yet.
            </span>
            <Link href="/subscriptions" className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted">Payments</Link>
          </li>
        ) : null}
        {estimatedPayments > 0 ? (
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-muted-foreground/60" aria-hidden="true" />
              {estimatedPayments} variable payment{estimatedPayments === 1 ? ' uses' : 's use'} the latest saved estimate.
            </span>
            <Link href="/subscriptions" className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted">Payments</Link>
          </li>
        ) : null}
        {scanIsPartial ? (
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-muted-foreground/60" aria-hidden="true" />
              The latest inbox scan ended early. Findings saved so far are ready to review.
            </span>
            <Link href="/review" className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted">Review</Link>
          </li>
        ) : gmailScanStale ? (
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-muted-foreground/60" aria-hidden="true" />
              Gmail has not been scanned in over 30 days, so recent changes may be missing.
            </span>
            <Link href="/review" className="shrink-0 rounded-md border border-border px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted">Scan</Link>
          </li>
        ) : null}
      </ul>
    </section>
  )
}
