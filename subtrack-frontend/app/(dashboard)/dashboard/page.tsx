'use client'

import { useMemo, useState } from 'react'
import Link from 'next/link'
import {
  ArrowRight,
  Mail,
  Sparkles,
} from 'lucide-react'
import {
  dismissReminder,
  restoreReminder,
  getDetected,
  getGmailStatus,
  getPreferences,
  getReminders,
  getSubscriptionForecast,
  getPaidHistory,
  getSubscriptions,
} from '@/lib/api'
import type {
  GmailStatus,
  DetectedSubscription,
  PaymentReminder,
  PaidHistory,
  Preferences,
  Subscription,
  SubscriptionForecast,
} from '@/types'
import { useCurrency } from '@/lib/context/currency'
import { DashboardSkeleton } from '@/components/dashboard/DashboardSkeleton'
import { Button } from '@/components/ui/button'
import { ReminderCenter } from '@/components/reminders/ReminderCenter'
import { useRegisterAgentPageContext } from '@/lib/agent/page-context'
import { toast } from 'sonner'
import { SafeToSpendCard } from '@/components/dashboard/SafeToSpendCard'
import { ComingUp } from '@/components/dashboard/ComingUp'
import { NeedsAttention } from '@/components/dashboard/NeedsAttention'
import { CategorySpend } from '@/components/dashboard/CategorySpend'
import { RecentChanges } from '@/components/subscriptions/RecentChanges'
import { GettingStarted } from '@/components/onboarding/GettingStarted'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { getAccessToken, useIsDemo } from '@/lib/auth/session'
import { useFeatures } from '@/lib/hooks/useFeatures'
import { FeaturePicker } from '@/components/onboarding/FeaturePicker'
import { ThisMonthCard } from '@/components/spending/ThisMonthCard'
import { GoalsCard } from '@/components/goals/GoalsCard'

export default function DashboardPage() {
  const { baseCurrency, ratesLoading, isLoading: preferencesLoading } = useCurrency()
  const { has, onboardingCompleted } = useFeatures()
  const paymentsOn = has('payments')
  const spendingOn = has('spending')
  const goalsOn = has('goals')
  const moreComing = has('workspace')

  const subscriptionsQuery = useApi<Subscription[]>(
    apiKeys.subscriptions('current'), token => getSubscriptions(token),
  )
  const preferencesQuery = useApi<Preferences>(apiKeys.preferences, getPreferences)
  const gmailQuery = useApi<GmailStatus>(apiKeys.gmailStatus, getGmailStatus)
  const remindersQuery = useApi<PaymentReminder[]>(
    apiKeys.reminders(90), token => getReminders(token, { horizonDays: 90 }),
  )
  const forecastQuery = useApi<SubscriptionForecast>(
    apiKeys.forecast(14), token => getSubscriptionForecast(token, 14),
  )
  const detectionsQuery = useApi<DetectedSubscription[]>(
    apiKeys.detected('pending'), token => getDetected(token, 'pending'),
  )

  const paidQuery = useApi<PaidHistory>(apiKeys.paid(3), token => getPaidHistory(token, 3))
  const overdueBills = (paidQuery.data?.bills ?? []).filter(bill => bill.status === 'overdue')

  const queries = [
    subscriptionsQuery, preferencesQuery, gmailQuery,
    remindersQuery, forecastQuery, detectionsQuery,
  ]
  const loading = queries.some(query => query.isLoading)

  const subscriptions = useMemo(() => subscriptionsQuery.data ?? [], [subscriptionsQuery.data])
  const reminders = useMemo(() => remindersQuery.data ?? [], [remindersQuery.data])
  const pendingDetections = useMemo(() => detectionsQuery.data ?? [], [detectionsQuery.data])
  const monthlyIncome = preferencesQuery.data?.monthly_income ?? null
  const gmail = gmailQuery.data ?? null
  const isDemo = useIsDemo()
  const forecast = forecastQuery.data ?? null

  const loadError = errorMessage(subscriptionsQuery.error, 'Could not load recurring payments.')
  const reminderError = errorMessage(remindersQuery.error, 'Could not load reminders.')
  const forecastError = errorMessage(forecastQuery.error, 'Could not calculate upcoming charges.')
  const remindersRetrying = remindersQuery.isValidating
  const forecastRetrying = forecastQuery.isValidating

  const [openedAt] = useState(() => Date.now())
  const gmailScanStale = useMemo(() => {
    const lastScanTime = gmail?.last_scanned_at
      ? new Date(gmail.last_scanned_at).getTime()
      : Number.NaN
    return Boolean(
      gmail?.connected
      && gmail.scan_status !== 'running'
      && Number.isFinite(lastScanTime)
      && openedAt - lastScanTime > 30 * 24 * 60 * 60 * 1000,
    )
  }, [gmail, openedAt])

  function refreshAll() {
    for (const query of queries) void query.mutate()
  }

  useRegisterAgentPageContext({
    visible_subscription_ids: subscriptions.slice(0, 25).map(subscription => subscription.id),
    visible_detection_ids: pendingDetections.slice(0, 25).map(detection => detection.id),
    visible_reminder_ids: reminders.slice(0, 25).map(reminder => reminder.id),
  })

  async function handleDismissReminder(id: string) {
    const accessToken = await getAccessToken()
    if (!accessToken) throw new Error('Your session has expired.')
    try {
      await dismissReminder(accessToken, id)
      void remindersQuery.mutate(
        current => current?.filter(reminder => reminder.id !== id),
        { revalidate: false },
      )
      toast.success('Reminder dismissed', {
        action: { label: 'Undo', onClick: () => void handleUndoDismissReminder(id) },
      })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not dismiss reminder.')
    }
  }

  async function handleUndoDismissReminder(id: string) {
    try {
      const accessToken = await getAccessToken()
      if (!accessToken) throw new Error('Your session has expired.')
      await restoreReminder(accessToken, id)
      void remindersQuery.mutate()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not restore reminder.')
    }
  }

  // Do not flash a base-currency-only subtotal while foreign exchange rates
  // are still loading. If the rate request fails, ratesLoading still settles
  // and the explicit exclusion message below takes over.
  const needsForeignRates = subscriptions.some(
    subscription => subscription.currency !== baseCurrency,
  )
  if (preferencesLoading || loading || (ratesLoading && needsForeignRates)) return <DashboardSkeleton />

  if (!onboardingCompleted) return <FeaturePicker />

  if (!paymentsOn) {
    return (
      <div className="mx-auto max-w-xl space-y-4 px-4 py-16 sm:px-6">
        {spendingOn ? <ThisMonthCard /> : null}
        {goalsOn ? <GoalsCard /> : null}
        {moreComing || (!spendingOn && !goalsOn) ? (
          <div className="rounded-2xl bg-card p-8 text-center shadow-sm">
            <h1 className="text-xl font-semibold text-foreground">The rest is coming soon</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {spendingOn || goalsOn
                ? 'Workspace is on its way. '
                : 'The features you picked are on their way. '}
              You can turn on monthly payments any time in Settings.
            </p>
            <Button asChild className="mt-5"><Link href="/account#features">Open Settings</Link></Button>
          </div>
        ) : null}
      </div>
    )
  }

  const hasPayments = subscriptions.length > 0

  if (loadError && !hasPayments) {
    return (
      <div className="mx-auto max-w-xl px-4 py-16 text-center sm:px-6">
        <div className="rounded-2xl border border-destructive/20 bg-card p-8 shadow-sm">
          <h1 className="text-xl font-semibold text-foreground">Couldn&apos;t load your dashboard</h1>
          <p className="mt-2 text-sm text-muted-foreground">{loadError}</p>
          <Button
            className="mt-5"
            onClick={refreshAll}
          >
            Try again
          </Button>
        </div>
      </div>
    )
  }

  // First run is the product's one chance to explain itself. A dashboard of
  // zeroes explains nothing, so the empty state sells the thing that makes
  // this worth using instead.
  if (!hasPayments) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
            <Sparkles className="h-7 w-7" />
          </div>
          <h1 className="mt-6 text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
            Let&apos;s find what you&apos;re paying for
          </h1>
          <p className="mx-auto mt-3 max-w-lg text-base text-muted-foreground">
            Subtrack reads the receipts already sitting in your inbox and works out
            which ones are recurring — so you don&apos;t have to remember them.
          </p>

          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Button asChild size="lg">
              <Link href={gmail?.connected ? '/review' : '/account#inbox'}>
                {gmail?.connected ? 'Review what we found' : 'Connect Gmail'}
                <ArrowRight className="ml-1.5 h-4 w-4" />
              </Link>
            </Button>
            <Button asChild variant="ghost" size="lg">
              <Link href="/subscriptions">Add one manually</Link>
            </Button>
          </div>
        </div>

        <div className="mx-auto mt-12 max-w-md">
          <GettingStarted
            gmailConnected={Boolean(gmail?.connected)}
            hasPayments={hasPayments}
            hasIncome={monthlyIncome !== null}
          />
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto w-full max-w-[90rem] px-5 py-8 sm:px-8 sm:py-10 lg:px-12">
      <div className="space-y-6 sm:space-y-8">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="eyebrow mb-2">Your money, at a glance</p>
            <h1 className="page-heading">A little more clarity.</h1>
            <p className="page-description">Make room for life. Keep an eye on what&apos;s coming.</p>
          </div>
          <Button asChild variant="outline" className="bg-card"><Link href="/subscriptions">View payments <ArrowRight className="h-4 w-4" /></Link></Button>
        </header>

        {loadError && (
          <div className="flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">Couldn&apos;t refresh your payments. Showing the last loaded totals.</p>
            <Button variant="outline" size="sm" onClick={refreshAll}>Retry</Button>
          </div>
        )}

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,1fr)_22rem] lg:items-start xl:gap-10">
          <div className="min-w-0 space-y-8">
            {spendingOn ? <ThisMonthCard /> : null}
            {goalsOn ? <GoalsCard /> : null}
            <SafeToSpendCard />
            <ComingUp
              forecast={forecast}
              error={forecastError}
              retrying={forecastRetrying}
              onRetry={() => void forecastQuery.mutate()}
              overdue={overdueBills}
            />
          </div>

          <aside
            className="min-w-0 divide-y divide-border overflow-hidden rounded-2xl bg-card shadow-sm lg:sticky lg:top-8"
            aria-label="Needs your attention and spending"
          >
            <NeedsAttention
              bare
              detections={pendingDetections}
              forecast={forecast}
              gmail={gmail}
              gmailScanStale={gmailScanStale}
              undatedPayments={subscriptions
                .filter(subscription => !subscription.next_due && ['active', 'cancelling'].includes(subscription.status))
                .map(({ id, name }) => ({ id, name }))}
            />

            {gmail && !gmail.connected && !isDemo && (
              <section className="px-5 py-4">
                <div className="flex items-start gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Mail className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-foreground">Find the ones you&apos;ve forgotten</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Connect Gmail to spot recurring charges. Read-only, nothing added without your approval.
                    </p>
                  </div>
                </div>
                <Button asChild size="sm" className="mt-3 w-full">
                  <Link href="/account#inbox">Connect Gmail</Link>
                </Button>
              </section>
            )}

            <CategorySpend subscriptions={subscriptions} />

            <RecentChanges bare />

            <ReminderCenter bare reminders={reminders} onDismiss={handleDismissReminder} />
            {reminderError ? (
              <section className="flex flex-col gap-3 bg-amber-500/5 px-5 py-4">
                <div>
                  <p className="text-sm font-semibold text-foreground">Reminders are unavailable</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{reminderError}</p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={remindersRetrying}
                  onClick={() => void remindersQuery.mutate()}
                  className="self-start"
                >
                  {remindersRetrying ? 'Trying again…' : 'Try again'}
                </Button>
              </section>
            ) : null}

            <GettingStarted
              bare
              gmailConnected={Boolean(gmail?.connected)}
              hasPayments={hasPayments}
              hasIncome={monthlyIncome !== null}
            />
          </aside>
        </div>
      </div>
    </div>
  )
}
