'use client'

import { PaymentsTabs } from '@/components/subscriptions/PaymentsTabs'
import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { ArrowUpRight, Check, ChevronDown, Clock3, Mail, RotateCcw, Trash2, X } from 'lucide-react'
import {
  approveDetected,
  clearAllDismissedDetected,
  clearDismissedDetected,
  confirmSamePayment,
  dismissDetected,
  getDetected,
  getGmailStatus,
  restoreDetected,
  startGmailScan,
} from '@/lib/api'
import type { DetectedSubscription, GmailStatus } from '@/types'
import { formatCurrency } from '@/lib/utils/currency'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { formatCategory } from '@/lib/utils/categories'
import { toast } from 'sonner'
import { useRegisterAgentPageContext } from '@/lib/agent/page-context'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { GmailScanProgress } from '@/components/gmail/GmailScanProgress'
import type { AmountType, RecurrenceUnit } from '@/types'
import {
  CADENCE_PRESETS,
  exactLegacyCycle,
  formatCadence,
} from '@/lib/utils/recurrence'
import {
  dateAtNoonUtc,
  formatStoredDate,
  storedDateKey,
  todayUtcDateKey,
} from '@/lib/utils/dates'
import { getAccessToken, useIsDemo } from '@/lib/auth/session'

function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse rounded-md bg-muted ${className ?? ''}`} />
}

interface CadenceDraft {
  interval_unit: RecurrenceUnit
  interval_count: string
  preset: string
}

function presetFor(unit: RecurrenceUnit, count: number) {
  return CADENCE_PRESETS.find(
    preset => preset.interval_unit === unit && preset.interval_count === count,
  )?.key ?? 'custom'
}

function preservedSplitAmount(
  item: DetectedSubscription,
  source: 'current' | 'similar',
) {
  const amount = source === 'current' ? item.current_amount : item.similar_amount
  const mode = source === 'current' ? item.current_split_mode : item.similar_split_mode
  const ratio = source === 'current' ? item.current_share_ratio : item.similar_share_ratio
  if (mode === 'fixed' && amount !== null) return amount
  if (mode === 'ratio' && ratio !== null && ratio > 0 && ratio <= 1) {
    return Math.round(item.amount * ratio * 100) / 100
  }
  return item.amount
}

async function token() {
  const accessToken = await getAccessToken()
  return accessToken
}

/** Utilities and other variable bills almost always come monthly or quarterly. */
function suggestedCadence(item: DetectedSubscription) {
  return item.category === 'utilities' || item.amount_type === 'variable'
    ? { interval_unit: 'month' as const, interval_count: 1 }
    : null
}

export default function ReviewPage() {
  const [busy, setBusy] = useState<string | null>(null)
  const [tab, setTab] = useState<'pending' | 'dismissed'>('pending')
  const gmailQuery = useApi<GmailStatus>(apiKeys.gmailStatus, getGmailStatus, {
    refreshInterval: latest => (latest?.scan_status === 'running' ? 3000 : 0),
  })
  const scanRunning = gmailQuery.data?.scan_status === 'running'
  // Poll both status and findings: successful model batches are committed as
  // they finish, so useful results can appear before the bounded scan ends.
  const itemsQuery = useApi<DetectedSubscription[]>(
    apiKeys.detected(tab),
    t => getDetected(t, tab),
    { refreshInterval: scanRunning ? 3000 : 0 },
  )
  const items = itemsQuery.data ?? []
  const gmail = gmailQuery.data ?? null
  const isDemo = useIsDemo()
  const loading = itemsQuery.isLoading || gmailQuery.isLoading
  const loadError = [
    errorMessage(itemsQuery.error, 'Could not load inbox findings.'),
    errorMessage(gmailQuery.error, 'Could not load Gmail status.'),
  ].filter(Boolean).join(' ')
  const [shares, setShares] = useState<Record<string, number>>({})
  const [custom, setCustom] = useState<Record<string, string>>({})
  const [trialPrices, setTrialPrices] = useState<Record<string, string>>({})
  const [trialEndDates, setTrialEndDates] = useState<Record<string, string>>({})
  const [cadenceDrafts, setCadenceDrafts] = useState<Record<string, CadenceDraft>>({})
  const [editingCadence, setEditingCadence] = useState<Record<string, boolean>>({})
  const [dueDates, setDueDates] = useState<Record<string, string>>({})
  const [amountTypes, setAmountTypes] = useState<Record<string, AmountType>>({})
  const [rescanStarting, setRescanStarting] = useState(false)
  const [clearAllOpen, setClearAllOpen] = useState(false)
  const busyRef = useRef(false)
  const rescanRef = useRef(false)

  useRegisterAgentPageContext({
    visible_detection_ids: items.slice(0, 25).map(item => item.id),
    filters: { review_status: tab },
  })

  function removeItem(id: string) {
    void itemsQuery.mutate(prev => prev?.filter(i => i.id !== id), { revalidate: false })
  }

  function reload() {
    void itemsQuery.mutate()
    void gmailQuery.mutate()
  }

  // The Gmail handshake finishes on a throwaway callback page and sends the
  // user here, so the confirmation has to be picked up on arrival — otherwise
  // a connection that just succeeded looks like nothing happened.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('gmail') !== 'connected') return
    toast.success('Gmail connected')
    window.history.replaceState({}, '', window.location.pathname)
  }, [])

  // Per-detection share of the bill. A receipt shows the whole cost, but the
  // user may only pay part of it (rent split with housemates, a shared energy
  // bill), so the split is chosen at review time.
  const SPLIT_OPTIONS = [
    { label: 'All', ratio: 1 },
    { label: '½', ratio: 1 / 2 },
    { label: '⅓', ratio: 1 / 3 },
    { label: '¼', ratio: 1 / 4 },
  ]

  function setShare(id: string, ratio: number) {
    setShares(prev => ({ ...prev, [id]: ratio }))
    setCustom(prev => ({ ...prev, [id]: '' }))
  }

  // An exact amount is an agreed uneven share (rent split 320/320/410). It's
  // sent as share_amount, not a ratio, so a later increase to the bill doesn't
  // silently rescale what you pay.
  function setCustomShare(id: string, value: string) {
    setCustom(prev => ({ ...prev, [id]: value }))
    setShares(prev => ({ ...prev, [id]: 1 }))
  }

  function fixedShare(id: string, billed: number): number | null {
    const mine = parseFloat(custom[id] ?? '')
    return Number.isFinite(mine) && mine > 0 && mine < billed ? mine : null
  }

  function startCadenceEdit(item: DetectedSubscription) {
    const unit = item.interval_unit ?? item.current_interval_unit
      ?? item.similar_interval_unit ?? 'month'
    const count = item.interval_count ?? item.current_interval_count
      ?? item.similar_interval_count ?? 1
    setCadenceDrafts(previous => ({
      ...previous,
      [item.id]: {
        interval_unit: unit,
        interval_count: String(count),
        preset: unit && count
          ? presetFor(unit, count) : '',
      },
    }))
    setEditingCadence(previous => ({ ...previous, [item.id]: true }))
  }

  function chooseCadencePreset(item: DetectedSubscription, presetKey: string) {
    const existing = cadenceDrafts[item.id]
    if (presetKey === 'custom') {
      setCadenceDrafts(previous => ({
        ...previous,
        [item.id]: {
          interval_unit: existing?.interval_unit ?? item.interval_unit
            ?? item.current_interval_unit ?? item.similar_interval_unit ?? 'month',
          interval_count: existing?.interval_count ?? String(
            item.interval_count ?? item.current_interval_count
              ?? item.similar_interval_count ?? 1,
          ),
          preset: 'custom',
        },
      }))
      return
    }
    const preset = CADENCE_PRESETS.find(option => option.key === presetKey)
    if (!preset) return
    setCadenceDrafts(previous => ({
      ...previous,
      [item.id]: {
        interval_unit: preset.interval_unit,
        interval_count: String(preset.interval_count),
        preset: preset.key,
      },
    }))
  }

  function setCadenceField(
    id: string,
    field: 'interval_unit' | 'interval_count',
    value: string,
  ) {
    setCadenceDrafts(previous => ({
      ...previous,
      [id]: {
        interval_unit: previous[id]?.interval_unit ?? 'month',
        interval_count: previous[id]?.interval_count ?? '1',
        preset: 'custom',
        [field]: value,
      },
    }))
  }


  function beginBusy(id: string) {
    if (busyRef.current) return false
    busyRef.current = true
    setBusy(id)
    return true
  }

  function endBusy() {
    busyRef.current = false
    setBusy(null)
  }

  async function undoDismiss(id: string) {
    try {
      const t = await token()
      if (!t) throw new Error('Your session has expired. Sign in again to continue.')
      await restoreDetected(t, id)
      void itemsQuery.mutate()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not restore this detection.')
    }
  }

  async function restore(id: string) {
    if (!beginBusy(id)) return
    try {
      const t = await token()
      if (!t) throw new Error('Your session has expired. Sign in again to continue.')
      await restoreDetected(t, id)
      removeItem(id)
      toast.success('Detection restored')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not restore this detection.')
    } finally {
      endBusy()
    }
  }

  async function clearOne(id: string) {
    if (!beginBusy(id)) return
    try {
      const t = await token()
      if (!t) throw new Error('Your session has expired. Sign in again to continue.')
      await clearDismissedDetected(t, id)
      removeItem(id)
      toast.success('Cleared. A future scan may suggest it again.')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not clear this detection.')
    } finally {
      endBusy()
    }
  }

  async function clearAll() {
    if (!beginBusy('clear-all')) return
    try {
      const t = await token()
      if (!t) throw new Error('Your session has expired. Sign in again to continue.')
      const { cleared } = await clearAllDismissedDetected(t)
      void itemsQuery.mutate([], { revalidate: false })
      setClearAllOpen(false)
      toast.success(`Cleared ${cleared} dismissed ${cleared === 1 ? 'item' : 'items'}`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not clear dismissed detections.')
    } finally {
      endBusy()
    }
  }

  // When a detection looks like a service the user already tracks, Add becomes
  // a question rather than an action — replacing the wrong row silently would
  // be worse than an extra one.
  const [choosing, setChoosing] = useState<string | null>(null)
  // Findings where the user said "No, it's a different payment" to the name match.
  const [notSame, setNotSame] = useState<Set<string>>(() => new Set())

  async function samePayment(id: string, subscriptionId: string, kind: 'regular' | 'extra' | 'new_price') {
    if (!beginBusy(id)) return
    try {
      const t = await token()
      if (!t) throw new Error('Your session has expired. Sign in again to continue.')
      const result = await confirmSamePayment(t, id, { subscription_id: subscriptionId, kind })
      removeItem(id)
      toast.success(
        kind === 'extra' && result.extra_amount
          ? `Recorded a ${formatCurrency(result.extra_amount, items.find(i => i.id === id)?.currency ?? 'AUD')} extra charge`
          : kind === 'new_price' ? 'Price updated' : 'Linked to your payment',
      )
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not link this payment.')
    } finally {
      endBusy()
    }
  }

  async function approveWith(id: string, replaceId?: string) {
    if (!beginBusy(id)) return
    try {
      const t = await token()
      if (!t) throw new Error('Your session has expired. Sign in again to continue.')
      const item = items.find(i => i.id === id)
      if (!item) throw new Error('This review item is no longer available.')
      const cadenceDraft = cadenceDrafts[id]
      const suggested = suggestedCadence(item)
      const intervalUnit = cadenceDraft?.interval_unit ?? item.interval_unit
        ?? item.current_interval_unit ?? item.similar_interval_unit ?? suggested?.interval_unit
      const intervalCount = Number(
        cadenceDraft?.interval_count ?? item.interval_count
          ?? item.current_interval_count ?? item.similar_interval_count ?? suggested?.interval_count,
      )
      if (!intervalUnit || !Number.isInteger(intervalCount)
          || intervalCount < 1 || intervalCount > 1200) {
        toast.error('Choose how often this payment repeats before approving it.')
        return
      }
      const enteredTrialPrice = parseFloat(trialPrices[id] ?? '')
      if (item.trial_ends_at && !item.cancelled && item.amount <= 0
          && (!Number.isFinite(enteredTrialPrice) || enteredTrialPrice <= 0)) {
        toast.error('Enter the price that will be charged after the trial.')
        return
      }
      const fixed = fixedShare(id, item.amount)
      if ((custom[id] ?? '').trim() && fixed === null) {
        toast.error('Your exact share must be greater than 0 and less than the full bill.')
        return
      }
      const ratio = shares[id]
      const targetId = replaceId ?? item.existing_subscription_id
      const detectedDueIsPast = Boolean(
        item.next_due && storedDateKey(item.next_due) < todayUtcDateKey(),
      )
      const dueDateWasEdited = Object.prototype.hasOwnProperty.call(dueDates, id)
      const correctedDueDate = dueDateWasEdited ? dueDates[id] : undefined
      const detectedTrialIsPast = Boolean(
        item.trial_ends_at && storedDateKey(item.trial_ends_at) < todayUtcDateKey(),
      )
      const trialDateWasEdited = Object.prototype.hasOwnProperty.call(trialEndDates, id)
      const correctedTrialDate = trialDateWasEdited
        ? trialEndDates[id] : detectedTrialIsPast ? '' : undefined
      const legacyCycle = exactLegacyCycle(intervalUnit, intervalCount)
      await approveDetected(t, id, {
        interval_unit: intervalUnit,
        interval_count: intervalCount,
        ...(legacyCycle ? { cycle: legacyCycle } : {}),
        amount_type: amountTypes[id] ?? item.amount_type,
        ...(correctedDueDate !== undefined || (detectedDueIsPast && !targetId)
          ? { next_due: correctedDueDate ? dateAtNoonUtc(correctedDueDate) : null }
          : {}),
        ...(correctedTrialDate !== undefined
          ? {
              trial_ends_at: correctedTrialDate
                ? dateAtNoonUtc(correctedTrialDate) : null,
            }
          : {}),
        ...(fixed !== null
          ? { share_amount: fixed }
          : ratio && ratio < 1
            ? { share_ratio: ratio }
            : {}),
        ...(replaceId ? { replace_subscription_id: replaceId } : {}),
        ...(item.trial_ends_at && !item.cancelled && item.amount <= 0
          ? { amount: enteredTrialPrice }
          : {}),
      })
      removeItem(id)
      setChoosing(null)
      toast.success('Review item approved')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not add this payment.')
    } finally {
      endBusy()
    }
  }

  async function resolve(id: string, action: 'approve' | 'dismiss') {
    if (action === 'approve') {
      await approveWith(id)
      return
    }
    if (!beginBusy(id)) return
    try {
      const t = await token()
      if (!t) throw new Error('Your session has expired. Sign in again to continue.')
      await dismissDetected(t, id)
      // Drop it locally rather than refetching — the row is gone either way.
      removeItem(id)
      toast.success('Detection dismissed', {
        action: { label: 'Undo', onClick: () => void undoDismiss(id) },
      })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not dismiss this detection.')
    } finally {
      endBusy()
    }
  }

  async function rescan() {
    if (rescanRef.current) return
    rescanRef.current = true
    setRescanStarting(true)
    try {
      const t = await token()
      if (!t) throw new Error('Your session has expired. Sign in again to continue.')
      await startGmailScan(t)
      void gmailQuery.mutate(g => (g ? {
        ...g,
        scan_status: 'running',
        scan_error: null,
        scan_stage: 'queued',
        scan_processed: 0,
        scan_total: 0,
        scan_partial: false,
        scan_message: null,
      } : g), { revalidate: false })
    } catch (e) {
      // Leave the button usable and say why — a silently ignored click reads
      // as the app being broken.
      const message = e instanceof Error ? e.message : 'Could not start the inbox scan.'
      toast.error(message)
    } finally {
      rescanRef.current = false
      setRescanStarting(false)
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-10">
        <div className="space-y-6">
          <Skeleton className="h-9 w-56" />
          <Skeleton className="h-24 rounded-2xl" />
          <Skeleton className="h-40 rounded-2xl" />
        </div>
      </div>
    )
  }

  const scanning = gmail?.scan_status === 'running'

  return (
    <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8 sm:py-10">
      <div className="space-y-6">
        <PaymentsTabs />
        {loadError && (
          <div className="flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">{loadError}</p>
            <Button variant="outline" size="sm" onClick={reload}>Try again</Button>
          </div>
        )}

        <section className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="space-y-2">
            <p className="eyebrow">Found in your email</p><h1 className="page-heading">
              Inbox
            </h1>
            <p className="max-w-2xl text-sm text-muted-foreground">
              Payments found in your email. Nothing is added until you approve it.
            </p>
          </div>

          {gmail?.connected && (
            <Button
              variant="outline"
              onClick={rescan}
              disabled={scanning || rescanStarting || busy !== null || !gmail.available}
              className="shrink-0"
            >
              {scanning || rescanStarting
                ? 'Scanning…'
                // "Rescan" to someone who has never scanned reads as though
                // they missed a step — and arriving straight from connecting
                // Gmail, they always have.
                : gmail.last_scanned_at ? 'Rescan inbox' : 'Scan inbox'}
            </Button>
          )}
        </section>

        {/* Dismissing is deliberately sticky — a rescan won't resurface it —
            so there has to be a way back to what you rejected. */}
        {(gmail?.connected || isDemo) && (
          <div className="flex gap-1 border-b border-border" role="tablist" aria-label="Review status">
            {([
              { key: 'pending', label: 'To review' },
              { key: 'dismissed', label: 'Dismissed' },
            ] as const).map(t => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={tab === t.key}
                onClick={() => {
                  if (t.key === tab) return
                  setTab(t.key)
                }}
                disabled={busy !== null}
                className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
                  tab === t.key
                    ? 'border-primary text-foreground'
                    : 'border-transparent text-muted-foreground hover:text-foreground'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        )}

        {isDemo ? (
          <p className="flex items-center gap-2 text-xs leading-5 text-muted-foreground"><Mail className="h-4 w-4 shrink-0 text-primary" />Sample findings. Try adding or dismissing a payment.</p>
        ) : gmail && !gmail.connected ? (
          <div className="rounded-2xl bg-card p-5 shadow-sm sm:p-6">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Mail className="h-5 w-5" />
              </div>
              <div>
                <p className="font-medium text-foreground">
                  {gmail.available ? 'No inbox connected' : 'No bills forwarded yet'}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {gmail.available
                    ? 'Connect Gmail and Subtrack will find recurring payments from receipt emails instead of you entering them by hand.'
                    : 'Forward your bills from Gmail and Subtrack will find recurring payments from them instead of you entering them by hand.'}
                </p>
                {gmail.available && (
                  <Link
                    href="/account"
                    className="mt-3 inline-block text-sm text-primary underline underline-offset-4"
                  >
                    Connect Gmail on the account page
                  </Link>
                )}
                <Link
                  href="/account#forwarding"
                  className="mt-3 block text-sm text-primary underline underline-offset-4"
                >
                  {gmail.available ? 'Or forward your bills from Gmail instead' : 'Set up forwarding'}
                </Link>
              </div>
            </div>
          </div>
        ) : gmail?.scan_error ? (
          <div className="rounded-2xl border border-destructive/20 bg-destructive/5 p-6">
            <p className="text-sm font-medium text-destructive">Last scan failed</p>
            <p className="mt-1 text-sm text-muted-foreground">{gmail.scan_error}</p>
          </div>
        ) : null}

        {gmail && (scanning || gmail.scan_partial) && (
          <GmailScanProgress gmail={gmail} />
        )}

        {tab === 'dismissed' && items.length > 0 && (
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              {items.length} dismissed {items.length === 1 ? 'item' : 'items'}
            </p>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setClearAllOpen(true)}
              disabled={busy !== null}
              className="text-muted-foreground hover:text-destructive"
            >
              <Trash2 className="mr-1 h-3.5 w-3.5" />
              Clear all
            </Button>
          </div>
        )}

        {items.length === 0 && !scanning && gmail?.connected ? (
          <div className="flex min-h-[200px] items-center justify-center rounded-2xl border border-dashed border-border bg-muted/30">
            <div className="text-center">
              <p className="text-sm font-medium text-foreground">
                {tab === 'dismissed' ? 'Nothing dismissed' : 'Nothing to review'}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                {tab === 'dismissed'
                  ? "Detections you dismiss show up here so you can check or restore them."
                  : gmail.last_scanned_at
                    ? 'Everything found has been approved or dismissed.'
                    : 'Run a scan to look for recurring payments in your email.'}
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {items.map(item => {
              const ratio = shares[item.id]
                ?? (item.current_split_mode === 'ratio' && item.current_share_ratio
                  ? item.current_share_ratio : 1)
              const fixed = fixedShare(item.id, item.amount)
              const splitWasEdited = Object.prototype.hasOwnProperty.call(shares, item.id)
                || Boolean((custom[item.id] ?? '').trim())
              const myAmount = fixed ?? (splitWasEdited
                ? Math.round(item.amount * ratio * 100) / 100
                : item.existing_subscription_id
                  ? preservedSplitAmount(item, 'current') : item.amount)
              const isShared = myAmount < item.amount
              const isIntro = item.intro_amount != null && item.trial_ends_at !== null
              const isPriceChange = item.existing_subscription_id !== null && !isIntro
              const rose =
                item.previous_amount !== null && item.amount > item.previous_amount
              const isTrial = item.trial_ends_at !== null && !isIntro
              const detectedTrialIsPast = Boolean(
                item.trial_ends_at
                  && storedDateKey(item.trial_ends_at) < todayUtcDateKey(),
              )
              const trialEndDateValue = Object.prototype.hasOwnProperty.call(
                trialEndDates, item.id,
              )
                ? trialEndDates[item.id]
                : detectedTrialIsPast ? '' : storedDateKey(item.trial_ends_at)
              const trialWillBeSaved = isTrial && Boolean(trialEndDateValue)
              const cadenceDraft = cadenceDrafts[item.id]
              const suggested = suggestedCadence(item)
              const usingSuggestion = !cadenceDraft && !item.interval_unit
                && !item.current_interval_unit && !item.similar_interval_unit && suggested !== null
              const effectiveUnit = cadenceDraft?.interval_unit ?? item.interval_unit
                ?? item.current_interval_unit ?? item.similar_interval_unit ?? suggested?.interval_unit
              const effectiveCount = Number(
                cadenceDraft?.interval_count ?? item.interval_count
                  ?? item.current_interval_count ?? item.similar_interval_count ?? suggested?.interval_count,
              )
              const cadenceKnown = Boolean(
                effectiveUnit && Number.isInteger(effectiveCount) && effectiveCount > 0,
              )
              const cadenceNeedsChoice = item.cadence_confidence === 'unknown'
                || !item.interval_unit || !item.interval_count
              const showCadenceEditor = tab === 'pending'
                && (cadenceNeedsChoice || editingCadence[item.id])
              const cadenceText = cadenceKnown && effectiveUnit
                ? formatCadence(effectiveUnit, effectiveCount)
                : 'Frequency needed'
              const detectedDueIsPast = Boolean(
                item.next_due && storedDateKey(item.next_due) < todayUtcDateKey(),
              )
              const approvePossible = !item.cancelled
                || Boolean(item.existing_subscription_id || item.similar_subscription_id)
              // "Is this your X payment?" — offered for a name match the user hasn't
              // rejected, and for an already-linked payment whose charge was higher.
              const askSame = tab === 'pending' && !item.cancelled && !isIntro
                && Boolean(item.similar_subscription_id) && !item.existing_subscription_id
                && !notSame.has(item.id)
              const linkedRegular = item.existing_subscription_id
                ? (item.current_full_amount ?? item.current_amount) : null
              const askWhyHigher = tab === 'pending' && !item.cancelled && !isIntro
                && Boolean(item.existing_subscription_id)
                && linkedRegular !== null && item.amount > linkedRegular + 0.005
              const sameTargetId = askSame ? item.similar_subscription_id : item.existing_subscription_id
              const sameTargetName = askSame ? item.similar_name : item.current_name
              const sameRegular = askSame ? (item.similar_full_amount ?? item.similar_amount) : linkedRegular
              const sameCadence = askSame ? item.similar_cadence_label : item.current_cadence_label
              const extraAmount = sameRegular !== null ? Math.round((item.amount - sameRegular) * 100) / 100 : 0

              return (
                <div
                  key={item.id}
                  className="rounded-2xl bg-card p-5 shadow-sm sm:p-6"
                >
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 flex-1 space-y-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-semibold text-foreground">{item.merchant}</p>
                        {item.intro_amount != null && item.trial_ends_at ? (
                          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary tabular-nums">
                            {formatCurrency(item.intro_amount, item.currency)} until{' '}
                            {formatStoredDate(item.trial_ends_at, { day: 'numeric', month: 'short' })}, then{' '}
                            {formatCurrency(item.amount, item.currency)}
                          </span>
                        ) : null}

                        {isPriceChange && (
                          <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">
                            {item.cancelled ? 'Matched payment' : 'Price change'}
                          </span>
                        )}
                        {isTrial && (
                          <span className="inline-flex items-center gap-1 rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
                            <Clock3 className="h-3 w-3" />
                            {detectedTrialIsPast ? 'Trial ended' : 'Free trial'}
                          </span>
                        )}
                        {item.cancelled && (
                          <span className="rounded-full border border-border bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                            Cancelled
                          </span>
                        )}
                        {item.amount_type === 'variable' && !item.cancelled ? (
                          <span className="rounded-full border border-border bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                            Variable amount
                          </span>
                        ) : null}
                        {item.confidence === 'medium' && (
                          <span className="rounded-full border border-border bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                            Less certain
                          </span>
                        )}
                      </div>

                      {item.cancelled ? (
                        <p className="text-sm text-muted-foreground">
                          Cancellation notice
                          {item.current_amount !== null ? (
                            <> · currently {formatCurrency(
                              item.current_amount, item.current_currency ?? item.currency,
                            )}</>
                          ) : null}
                        </p>
                      ) : isIntro ? (
                        <p className="text-sm text-muted-foreground">{formatCurrency(item.intro_amount!, item.currency)} · {cadenceText.toLowerCase()} during the offer</p>
                      ) : isTrial && item.amount <= 0 ? (
                        <div className="max-w-xs space-y-1.5">
                          <label htmlFor={`trial-price-${item.id}`} className="text-xs font-medium text-foreground">
                            Price after trial ({item.currency})
                          </label>
                          <input
                            id={`trial-price-${item.id}`}
                            type="number"
                            min="0.01"
                            step="0.01"
                            inputMode="decimal"
                            value={trialPrices[item.id] ?? ''}
                            onChange={event => setTrialPrices(current => ({
                              ...current,
                              [item.id]: event.target.value,
                            }))}
                            placeholder="Required before approval"
                            className="w-full rounded-md border border-border bg-background px-2.5 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                          />
                        </div>
                      ) : (
                        <p className="text-sm text-muted-foreground">
                          {item.amount_type === 'variable' ? '≈ ' : ''}
                          {isShared ? (
                            <>
                              <span className="line-through opacity-60">
                                {formatCurrency(item.amount, item.currency)}
                              </span>{' '}
                              <span className="font-medium text-foreground">
                                {formatCurrency(myAmount, item.currency)}
                              </span>
                            </>
                          ) : (
                            formatCurrency(item.amount, item.currency)
                          )}
                          {' · '}{cadenceText.toLowerCase()}
                          {item.amount_type === 'variable' ? ' estimate' : ''}
                        </p>
                      )}

                      {isIntro && item.existing_subscription_id ? <p className="text-xs leading-5 text-muted-foreground">Saves this introductory offer on your existing {item.current_name ?? 'payment'}. The higher price is scheduled for later; it is not a receipt for that amount.</p> : null}
                      {isTrial || isIntro ? (
                        <div className="grid max-w-sm gap-1.5 rounded-xl border border-border bg-muted/20 p-3">
                          <Label htmlFor={`detected-trial-end-${item.id}`}>{isIntro ? 'Introductory price ends' : 'Trial end date'}</Label>
                          {tab === 'pending' ? (
                            <Input
                              id={`detected-trial-end-${item.id}`}
                              type="date"
                              min={todayUtcDateKey()}
                              value={trialEndDateValue}
                              onChange={event => setTrialEndDates(previous => ({
                                ...previous,
                                [item.id]: event.target.value,
                              }))}
                              disabled={busy !== null}
                            />
                          ) : (
                            <p className="text-sm text-muted-foreground">
                              {formatStoredDate(item.trial_ends_at!)}
                            </p>
                          )}
                          <p className={`text-xs leading-5 ${
                            detectedTrialIsPast
                              ? 'text-amber-700 dark:text-amber-300'
                              : 'text-muted-foreground'
                          }`}>
                            {detectedTrialIsPast
                              ? 'The detected date has passed. Enter a corrected future date, or leave it blank to approve this as an already-converted recurring payment.'
                              : isIntro
                                ? 'Keep paying the introductory price until this date. The regular price applies afterwards.'
                                : trialWillBeSaved
                                ? 'Approving creates a dashboard cancellation reminder 7 days before this date.'
                                : 'Leave this blank only if the trial has already converted.'}
                          </p>
                        </div>
                      ) : null}

                      <details className="group/schedule rounded-xl border border-border p-3" open={cadenceNeedsChoice || detectedDueIsPast || item.due_date_confidence === 'unknown' || undefined}>
                        <summary className="-m-3 flex min-h-14 cursor-pointer list-none items-center justify-between gap-3 rounded-xl p-3 text-primary transition-colors hover:bg-primary/5 [&::-webkit-details-marker]:hidden">
                          <span>
                            <span className="block text-sm font-medium">Review details & schedule</span>
                            {item.next_due && !detectedDueIsPast ? <span className="mt-1 block text-xs text-muted-foreground">Next payment {formatStoredDate(item.next_due, { day: 'numeric', month: 'short' })}</span> : null}
                          </span>
                          <ChevronDown className="h-5 w-5 shrink-0 transition-transform group-open/schedule:rotate-180" aria-hidden="true" />
                        </summary>
                        <div className="mt-4 space-y-3">
                      <div className="rounded-xl border border-border bg-muted/20 p-3">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-xs font-medium text-foreground">Billing frequency</p>
                            {!showCadenceEditor ? (
                              <p className="mt-0.5 text-sm text-muted-foreground">{cadenceText}</p>
                            ) : null}
                          </div>
                          {!showCadenceEditor && tab === 'pending' ? (
                            <button
                              type="button"
                              onClick={() => startCadenceEdit(item)}
                              className="text-xs font-medium text-primary hover:underline"
                            >
                              Change
                            </button>
                          ) : null}
                        </div>

                        {showCadenceEditor ? (
                          <div className="mt-2 grid gap-2">
                            <Label htmlFor={`detected-cadence-${item.id}`} className="sr-only">
                              Billing frequency for {item.merchant}
                            </Label>
                            <Select
                              value={cadenceDraft?.preset
                                ?? (cadenceKnown && effectiveUnit
                                  ? presetFor(effectiveUnit, effectiveCount) : '')}
                              onValueChange={value => chooseCadencePreset(item, value)}
                              disabled={busy !== null}
                            >
                              <SelectTrigger id={`detected-cadence-${item.id}`}>
                                <SelectValue placeholder="Choose a frequency" />
                              </SelectTrigger>
                              <SelectContent>
                                {CADENCE_PRESETS.map(preset => (
                                  <SelectItem key={preset.key} value={preset.key}>{preset.label}</SelectItem>
                                ))}
                                <SelectItem value="custom">Custom interval…</SelectItem>
                              </SelectContent>
                            </Select>

                            {(cadenceDraft?.preset === 'custom'
                              || (!cadenceDraft && cadenceKnown && effectiveUnit
                                && presetFor(effectiveUnit, effectiveCount) === 'custom')) ? (
                              <div className="grid grid-cols-2 gap-2">
                                <Input
                                  type="number"
                                  min="1"
                                  max="1200"
                                  step="1"
                                  aria-label={`Billing interval count for ${item.merchant}`}
                                  value={cadenceDraft?.interval_count ?? String(effectiveCount || 1)}
                                  onChange={event => setCadenceField(item.id, 'interval_count', event.target.value)}
                                  disabled={busy !== null}
                                />
                                <Select
                                  value={cadenceDraft?.interval_unit ?? effectiveUnit ?? 'month'}
                                  onValueChange={value => setCadenceField(item.id, 'interval_unit', value)}
                                  disabled={busy !== null}
                                >
                                  <SelectTrigger aria-label={`Billing interval unit for ${item.merchant}`}>
                                    <SelectValue />
                                  </SelectTrigger>
                                  <SelectContent>
                                    {(['day', 'week', 'month', 'year'] as const).map(unit => (
                                      <SelectItem key={unit} value={unit}>{unit[0].toUpperCase() + unit.slice(1)}s</SelectItem>
                                    ))}
                                  </SelectContent>
                                </Select>
                              </div>
                            ) : null}
                          </div>
                        ) : null}

                        {usingSuggestion ? (
                          <p className="mt-2 text-xs leading-5 text-muted-foreground">
                            Suggested: monthly. Energy and water bills usually come monthly or
                            quarterly, so check your bill and change it if needed. Each new bill
                            then updates the estimate on its own.
                          </p>
                        ) : null}
                        {cadenceNeedsChoice && !cadenceKnown ? (
                          <p role="alert" className="mt-2 text-xs font-medium text-amber-700 dark:text-amber-300">
                            Gmail could not infer this safely. Choose a frequency before approving.
                          </p>
                        ) : null}
                        {item.cadence_evidence ? (
                          <p className="mt-2 text-xs leading-5 text-muted-foreground">
                            Evidence: {item.cadence_evidence}
                          </p>
                        ) : null}
                      </div>

                      {!item.cancelled && !trialWillBeSaved ? (
                        <div className="grid gap-3 rounded-xl border border-border bg-muted/20 p-3 sm:grid-cols-2">
                          <div className="grid gap-1.5">
                            <Label htmlFor={`detected-due-${item.id}`}>Next expected payment</Label>
                            {tab === 'pending' ? (
                              <Input
                                id={`detected-due-${item.id}`}
                                type="date"
                                min={todayUtcDateKey()}
                                value={dueDates[item.id]
                                  ?? (detectedDueIsPast ? '' : storedDateKey(item.next_due))}
                                onChange={event => setDueDates(previous => ({
                                  ...previous,
                                  [item.id]: event.target.value,
                                }))}
                                disabled={busy !== null}
                              />
                            ) : (
                              <p className="text-sm text-muted-foreground">
                                {item.next_due
                                  ? formatStoredDate(item.next_due)
                                  : 'Not found'}
                              </p>
                            )}
                            {detectedDueIsPast ? (
                              <p className="text-xs leading-5 text-amber-700 dark:text-amber-300">
                                The date found in the email has passed. Choose the next expected date or leave it blank.
                              </p>
                            ) : item.due_date_evidence ? (
                              <p className="text-xs leading-5 text-muted-foreground">
                                Evidence: {item.due_date_evidence}
                              </p>
                            ) : item.due_date_confidence === 'unknown' ? (
                              <p className="text-xs leading-5 text-muted-foreground">No reliable date found. You can leave this blank.</p>
                            ) : null}
                          </div>

                          <div className="grid content-start gap-1.5">
                            <Label htmlFor={`detected-amount-type-${item.id}`}>Amount behaviour</Label>
                            {tab === 'pending' ? (
                              <Select
                                value={amountTypes[item.id] ?? item.amount_type}
                                onValueChange={value => setAmountTypes(previous => ({
                                  ...previous,
                                  [item.id]: value as AmountType,
                                }))}
                                disabled={busy !== null}
                              >
                                <SelectTrigger id={`detected-amount-type-${item.id}`}><SelectValue /></SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="fixed">Usually fixed</SelectItem>
                                  <SelectItem value="variable">Varies each bill</SelectItem>
                                </SelectContent>
                              </Select>
                            ) : (
                              <p className="text-sm text-muted-foreground">
                                {item.amount_type === 'variable' ? 'Varies each bill' : 'Usually fixed'}
                              </p>
                            )}
                          </div>
                        </div>
                      ) : null}

                        </div>
                      </details>

                      {/* The evidence. You're being asked to trust a guess, so
                          show what it's based on. */}
                      <p className="text-xs text-muted-foreground">
                        {item.charge_count > 0
                          ? `${item.charge_count} charge${item.charge_count === 1 ? '' : 's'} found`
                          : isTrial
                            ? 'No charge yet — detected from a trial email'
                            : 'No charges found — detected from cancellation notice'}
                        {' · '}
                        <span>{formatCategory(item.category)}</span>
                        {' · via '}
                        {item.sender_domain}
                      </p>

                      {item.previous_amount !== null && !item.cancelled && !isIntro && (
                        <p
                          className="flex items-center gap-1 text-xs font-medium"
                          style={{ color: rose ? 'var(--increase)' : 'var(--decrease)' }}
                        >
                          {rose && <ArrowUpRight className="h-3 w-3" />}
                          {formatCurrency(item.previous_amount, item.currency)} →{' '}
                          {formatCurrency(item.amount, item.currency)}
                          {isPriceChange && ' — updates your existing payment'}
                        </p>
                      )}

                      {isPriceChange && (
                        <p className="text-xs text-muted-foreground">
                          {item.cancelled ? 'Marks your existing ' : 'Updates your existing '}
                          <span className="font-medium text-foreground">
                            {item.current_name ?? 'payment'}
                          </span>
                          {!item.cancelled && item.current_amount !== null && (
                            <>
                              {' — '}
                              {formatCurrency(
                                item.current_amount, item.current_currency ?? item.currency,
                              )}
                              {' → '}
                              <span className="font-medium text-foreground">
                                {formatCurrency(myAmount, item.currency)}
                              </span>
                            </>
                          )}
                          {item.cancelled
                            ? ' as cancelled and removes it from current totals.'
                            : '. No duplicate is created.'}
                        </p>
                      )}

                      {item.cancelled && !approvePossible ? (
                        <p className="text-xs leading-5 text-muted-foreground">
                          No tracked payment matched this notice, so there is nothing to cancel. Dismiss it after checking the merchant.
                        </p>
                      ) : null}

                      {(askSame || askWhyHigher) && sameTargetId ? (
                        <div className="rounded-xl border border-primary/25 bg-primary/5 p-3">
                          <p className="text-sm font-medium text-foreground">
                            {askSame ? (
                              <>Is this your {sameTargetName} payment?</>
                            ) : (
                              <>Why was this {sameTargetName} charge higher?</>
                            )}
                          </p>
                          {sameRegular !== null ? (
                            <p className="mt-0.5 text-xs text-muted-foreground">
                              You normally pay {formatCurrency(sameRegular, item.currency)}
                              {sameCadence ? ` · ${sameCadence.toLowerCase()}` : ''}. This charge was{' '}
                              {formatCurrency(item.amount, item.currency)}
                              {extraAmount > 0 ? ` (+${formatCurrency(extraAmount, item.currency)})` : ''}.
                            </p>
                          ) : null}
                          <div className="mt-2.5 flex flex-wrap gap-2">
                            {extraAmount > 0 ? (
                              <>
                                <Button size="sm" disabled={busy !== null}
                                  onClick={() => void samePayment(item.id, sameTargetId, 'extra')}>
                                  Late fee or extra charge
                                </Button>
                                <Button size="sm" variant="outline" disabled={busy !== null}
                                  onClick={() => void samePayment(item.id, sameTargetId, 'new_price')}>
                                  New regular price
                                </Button>
                              </>
                            ) : extraAmount < 0 ? (
                              <>
                                <Button size="sm" disabled={busy !== null}
                                  onClick={() => void samePayment(item.id, sameTargetId, 'new_price')}>
                                  Yes, new price
                                </Button>
                                <Button size="sm" variant="outline" disabled={busy !== null}
                                  onClick={() => void samePayment(item.id, sameTargetId, 'regular')}>
                                  Yes, one-off discount
                                </Button>
                              </>
                            ) : (
                              <Button size="sm" disabled={busy !== null}
                                onClick={() => void samePayment(item.id, sameTargetId, 'regular')}>
                                Yes, same payment
                              </Button>
                            )}
                            {askSame ? (
                              <Button size="sm" variant="ghost" disabled={busy !== null}
                                className="text-muted-foreground"
                                onClick={() => setNotSame(previous => new Set(previous).add(item.id))}>
                                No, it&apos;s different
                              </Button>
                            ) : null}
                          </div>
                          <p className="mt-2 text-[11px] text-muted-foreground">
                            Subtrack will remember this, so future receipts link on their own.
                          </p>
                        </div>
                      ) : null}

                      {item.similar_subscription_id && item.cancelled && (
                        <div className="rounded-lg border border-amber-500/25 bg-amber-500/5 p-3">
                          <p className="text-xs text-foreground">
                            Looks like{' '}
                            <span className="font-medium">{item.similar_name}</span>
                            {item.similar_amount !== null && (
                              <>
                                {' '}({formatCurrency(
                                  item.similar_amount, item.similar_currency ?? item.currency,
                                )} ·{' '}
                                {item.similar_cadence_label ?? item.similar_cycle ?? 'frequency unknown'})
                              </>
                            )}
                            , which you already track.
                          </p>
                          {item.similar_reason && (
                            <p className="mt-0.5 text-xs text-muted-foreground">
                              {item.similar_reason}
                            </p>
                          )}
                          {choosing === item.id && (
                            <div className="mt-2 space-y-2">
                              {!item.cancelled && item.similar_split_mode
                                  && item.similar_split_mode !== 'full'
                                  && !splitWasEdited ? (
                                <p className="text-xs text-muted-foreground">
                                  Replacing keeps its saved split, so the updated payment will be{' '}
                                  <span className="font-medium text-foreground">
                                    {formatCurrency(
                                      preservedSplitAmount(item, 'similar'), item.currency,
                                    )}
                                  </span>
                                  {' '}of the detected {formatCurrency(item.amount, item.currency)} bill.
                                </p>
                              ) : null}
                              <div className="flex flex-wrap gap-2">
                                <Button
                                  size="sm"
                                  onClick={() =>
                                    approveWith(item.id, item.similar_subscription_id!)
                                  }
                                  disabled={busy !== null}
                                >
                                  {item.cancelled ? 'Cancel' : 'Replace'} {item.similar_name}
                                </Button>
                                {!item.cancelled ? (
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() => approveWith(item.id)}
                                    disabled={busy !== null}
                                  >
                                    Keep both
                                  </Button>
                                ) : null}
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  onClick={() => setChoosing(null)}
                                  disabled={busy !== null}
                                  className="text-muted-foreground"
                                >
                                  Cancel
                                </Button>
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* An agreed uneven split doesn't rescale on its own —
                          who covers an increase is for the housemates to
                          decide, so say what happens if they do nothing. */}
                      {isPriceChange && item.current_split_mode
                          && item.current_split_mode !== 'full' && !splitWasEdited && (
                        <p className="text-xs text-muted-foreground">
                          Your saved {item.current_split_mode === 'fixed' ? 'exact' : 'percentage'} split
                          {' '}will be kept. With this bill, you will pay{' '}
                          <span className="font-medium text-foreground">
                            {formatCurrency(myAmount, item.currency)}
                          </span>{' '}
                          unless you choose a new split below.
                        </p>
                      )}

                      {/* Receipts show the whole bill. Shared costs — rent,
                          household utilities — need only the user's portion. */}
                      <details className={tab === 'dismissed' || item.amount <= 0 ? 'hidden' : 'group/sharing rounded-xl border border-border p-3'} open={isShared || undefined}>
                        <summary className="-m-3 flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 rounded-xl p-3 text-sm font-medium text-primary transition-colors hover:bg-primary/5 [&::-webkit-details-marker]:hidden">
                          <span>{isShared ? 'Edit your share of this bill' : 'Split this bill'}</span>
                          <ChevronDown className="h-5 w-5 shrink-0 transition-transform group-open/sharing:rotate-180" aria-hidden="true" />
                        </summary>
                      <div className={`mt-4 flex-wrap items-center gap-1.5 pt-1 ${
                        tab === 'dismissed' || item.amount <= 0 ? 'hidden' : 'flex'
                      }`}>
                        <span className="mr-1 text-xs text-muted-foreground">
                          I pay
                        </span>
                        {SPLIT_OPTIONS.map(option => {
                          const active = Math.abs(ratio - option.ratio) < 0.001
                            && !custom[item.id]
                            && !(item.current_split_mode === 'fixed' && !splitWasEdited)
                          return (
                            <button
                              key={option.label}
                              type="button"
                              onClick={() => setShare(item.id, option.ratio)}
                              disabled={busy !== null}
                              className={`rounded-md border px-2 py-1 text-xs font-medium transition-colors ${
                                active
                                  ? 'border-primary bg-primary/10 text-primary'
                                  : 'border-border text-muted-foreground hover:bg-muted hover:text-foreground'
                              }`}
                            >
                              {option.label}
                            </button>
                          )
                        })}
                        <div className="flex items-center gap-1">
                          <span className="text-xs text-muted-foreground">or</span>
                          <input
                            type="number"
                            min="0"
                            max={item.amount}
                            step="0.01"
                            inputMode="decimal"
                            placeholder="exact"
                            value={custom[item.id] ?? ''}
                            onChange={e => setCustomShare(item.id, e.target.value)}
                            disabled={busy !== null}
                            className="w-20 rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                          />
                        </div>
                        {isShared && (
                          <span className="text-xs text-muted-foreground">
                            of {formatCurrency(item.amount, item.currency)}
                          </span>
                        )}
                      </div>
                      </details>
                    </div>

                    <div className="flex shrink-0 gap-2">
                      {tab === 'dismissed' ? (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => restore(item.id)}
                            disabled={busy !== null}
                          >
                            <RotateCcw className="mr-1 h-3.5 w-3.5" />
                            Restore
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => clearOne(item.id)}
                            disabled={busy !== null}
                            aria-label={`Clear ${item.merchant}`}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            <Trash2 className="mr-1 h-3.5 w-3.5" />
                            Clear
                          </Button>
                        </>
                      ) : (
                        <>
                          {approvePossible ? (
                            <Button
                              size="sm"
                              onClick={() =>
                                item.similar_subscription_id && item.cancelled && choosing !== item.id
                                  ? setChoosing(item.id)
                                  : resolve(item.id, 'approve')
                              }
                              disabled={busy !== null}
                            >
                              <Check className="mr-1 h-3.5 w-3.5" />
                              {item.cancelled ? 'Cancel payment' : item.existing_subscription_id ? isIntro ? 'Save offer' : 'Update' : 'Add'}
                            </Button>
                          ) : null}
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => resolve(item.id, 'dismiss')}
                            disabled={busy !== null}
                            className="text-muted-foreground hover:text-foreground"
                          >
                            <X className="mr-1 h-3.5 w-3.5" />
                            Dismiss
                          </Button>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {items.length > 0 && (
          <p className="text-xs text-muted-foreground">
            {tab === 'dismissed'
              ? "Dismissed items won't be suggested again on future scans. Cleared items may be."
              : "Dismissed items won't be suggested again on future scans."}
          </p>
        )}
      </div>

      <Dialog
        open={clearAllOpen}
        onOpenChange={open => {
          if (busy === 'clear-all') return
          setClearAllOpen(open)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Clear all dismissed items?</DialogTitle>
            <DialogDescription>
              This permanently removes {items.length} dismissed {items.length === 1 ? 'item' : 'items'}. If those payments still appear in your email, a future scan may suggest them again.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setClearAllOpen(false)}
              disabled={busy === 'clear-all'}
            >
              Keep them
            </Button>
            <Button
              variant="destructive"
              onClick={clearAll}
              disabled={busy === 'clear-all'}
            >
              {busy === 'clear-all' ? 'Clearing…' : 'Clear all'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
