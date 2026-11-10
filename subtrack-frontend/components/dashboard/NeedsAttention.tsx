'use client'

import { useState } from 'react'
import Link from 'next/link'
import { ChevronDown } from 'lucide-react'
import { useEditPayment } from '@/components/subscriptions/PaymentEditor'
import type { DetectedSubscription, GmailStatus, SubscriptionForecast } from '@/types'

interface Props {
  detections: DetectedSubscription[]
  forecast: SubscriptionForecast | null
  gmail: GmailStatus | null
  gmailScanStale: boolean
  /** Drop the card surface when rendered inside another panel. */
  bare?: boolean
  undatedPayments?: { id: string; name: string }[]
}

export function NeedsAttention({ detections, forecast, gmail, gmailScanStale, undatedPayments = [], bare = false }: Props) {
  const editPayment = useEditPayment()
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
    <section className={bare ? 'px-5 py-2' : 'rounded-2xl bg-card px-5 py-2 shadow-sm sm:px-6'} aria-labelledby="needs-attention-heading">
      <button
        type="button"
        aria-expanded={open}
        aria-controls="needs-attention-list"
        onClick={() => setOpen(value => !value)}
        className="flex min-h-11 w-full items-center gap-3 py-2 text-left"
      >
        <span className="flex h-6 min-w-6 items-center justify-center rounded-full bg-amber-500/15 px-1.5 text-[13px] font-semibold tabular-nums text-amber-700 dark:text-amber-300">
          {count}
        </span>
        <h2 id="needs-attention-heading" className="flex-1 text-[15px] font-medium text-foreground">
          Needs your attention
        </h2>
        <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      <ul id="needs-attention-list" hidden={!open} className="divide-y divide-border border-t border-border pb-1 text-[15px]">
        {uncertainDetections > 0 ? (
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true" />
              {uncertainDetections} finding{uncertainDetections === 1 ? '' : 's'} to check in Inbox
            </span>
            <Link href="/review" className="shrink-0 rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20">Review</Link>
          </li>
        ) : null}
        {unknownTrialPrices > 0 ? (
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true" />
              {unknownTrialPrices} trial{unknownTrialPrices === 1 ? '' : 's'} need a price
            </span>
            <Link href="/review" className="shrink-0 rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20">Review</Link>
          </li>
        ) : null}
        {missingDates > 0 ? (
          <li className="py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true" />
              {missingDates} payment{missingDates === 1 ? ' needs' : 's need'} a date
            </span>
            {undatedPayments.length > 0 ? (
              <span className="mt-2 flex flex-wrap gap-2 pl-[18px]">
                {undatedPayments.map(payment => (
                  <button
                    key={payment.id}
                    type="button"
                    onClick={() => editPayment(payment.id)}
                    title={`Add a date for ${payment.name}`}
                    className="inline-flex min-h-9 max-w-full items-center gap-1.5 rounded-full bg-primary/10 px-3 text-[13px] font-medium text-primary transition-colors hover:bg-primary/20"
                  >
                    <span className="truncate">{payment.name}</span>
                    <span aria-hidden="true">+</span>
                  </button>
                ))}
              </span>
            ) : (
              <Link href="/subscriptions" className="mt-2 inline-block pl-[18px] text-[13px] font-medium text-primary hover:underline">Open payments</Link>
            )}
          </li>
        ) : null}
        {pausedWithoutResume > 0 ? (
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true" />
              {pausedWithoutResume} paused payment{pausedWithoutResume === 1 ? ' needs' : 's need'} a resume date
            </span>
            <Link href="/subscriptions" className="shrink-0 rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20">Bills</Link>
          </li>
        ) : null}
        {unconverted > 0 ? (
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true" />
              {unconverted} charge{unconverted === 1 ? '' : 's'} can&apos;t be converted yet
            </span>
            <Link href="/subscriptions" className="shrink-0 rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20">Bills</Link>
          </li>
        ) : null}
        {estimatedPayments > 0 ? (
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true" />
              {estimatedPayments} bill{estimatedPayments === 1 ? ' is' : 's are'} an estimate
            </span>
            <Link href="/subscriptions" className="shrink-0 rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20">Bills</Link>
          </li>
        ) : null}
        {scanIsPartial ? (
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true" />
              Last inbox check didn&apos;t finish
            </span>
            <Link href="/review" className="shrink-0 rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20">Review</Link>
          </li>
        ) : gmailScanStale ? (
          <li className="flex items-center justify-between gap-4 py-3">
            <span className="flex items-center gap-2.5 text-foreground">
              <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true" />
              Inbox not checked in 30+ days
            </span>
            <Link href="/review" className="shrink-0 rounded-md bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20">Scan</Link>
          </li>
        ) : null}
      </ul>
    </section>
  )
}
