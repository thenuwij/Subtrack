'use client'

import { useState } from 'react'
import { DropdownMenu } from 'radix-ui'
import type { PaymentExtrasSummary, Subscription } from '@/types'
import { Button } from '@/components/ui/button'
import { Bell, Clock3, Trash2, Pencil, Sparkles, Ellipsis } from 'lucide-react'
import { useThisMonth } from '@/lib/hooks/useThisMonth'
import { apiKeys, useApi } from '@/lib/hooks/useApi'
import { getPaymentExtras } from '@/lib/api'
import { useCurrency } from '@/lib/context/currency'
import { formatCurrency } from '@/lib/utils/currency'
import { formatCategory } from '@/lib/utils/categories'
import { BrandLogo } from '@/components/shared/BrandLogo'
import { isActiveTrial } from '@/lib/utils/trials'
import {
  cadenceLabel,
  isTerminalStatus,
  paymentStatusLabel,
  yearlyEquivalentNative,
} from '@/lib/utils/recurrence'
import { toast } from 'sonner'
import { formatStoredDate, storedDateKey, todayUtcDateKey } from '@/lib/utils/dates'

// Just the date it next goes out. Pocketday isn't tracking whether payments landed,
// so anything framed as overdue/due-soon would be claiming knowledge it doesn't have.
function formatNextDate(dateStr: string): string {
  return formatStoredDate(dateStr, { day: 'numeric', month: 'short' })
}

interface Props {
  subscription: Subscription
  onDelete: (id: string) => Promise<void>
  onEdit: (subscription: Subscription) => void
  onReminders: (subscription: Subscription) => void
  onAskAssistant?: (subscription: Subscription) => void
}

export function SubscriptionCard({
  subscription,
  onDelete,
  onEdit,
  onReminders,
  onAskAssistant,
}: Props) {
  const [confirming, setConfirming] = useState(false)
  const [deleting, setDeleting]     = useState(false)
  const { baseCurrency, canConvert, convertAmount, ratesLoading } = useCurrency()

  const nextDate = subscription.next_expected_at
    ? formatNextDate(subscription.next_expected_at) : null
  const trialEnd = subscription.trial_ends_at
    ? formatNextDate(subscription.trial_ends_at)
    : null
  const terminal = isTerminalStatus(subscription.status)
  const remindersAvailable = subscription.status === 'active'
    || subscription.status === 'cancelling'
  const trialActive = !terminal && isActiveTrial(subscription)
  const introActive = !terminal && subscription.intro_amount != null && Boolean(subscription.trial_ends_at)
    && storedDateKey(subscription.trial_ends_at) >= todayUtcDateKey()
  const canShowConversion = canConvert(subscription.currency)
  const yearlyNative = yearlyEquivalentNative(subscription)
  const { costOf, monthShort } = useThisMonth()
  const extrasQuery = useApi<PaymentExtrasSummary[]>(apiKeys.extras(90), token => getPaymentExtras(token, 90))
  const extras = extrasQuery.data?.find(row => row.subscription_id === subscription.id)
  const monthlyBase = costOf(subscription)
  const yearlyBase = canShowConversion
    ? convertAmount(yearlyNative, subscription.currency)
    : null
  const lifecycleDate = subscription.status === 'paused'
    ? subscription.paused_until
    : subscription.status === 'cancelling'
      ? subscription.cancellation_effective_at
      : subscription.recurrence_end_at

  async function handleDelete() {
    setDeleting(true)
    try {
      await onDelete(subscription.id)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not delete this payment.')
    } finally {
      setDeleting(false)
      setConfirming(false)
    }
  }

  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 px-4 py-5 transition-colors hover:bg-muted/30 sm:px-5">

      {/* Left — logo + name + subtitle */}
      <div className="flex items-center gap-3 flex-1 min-w-0">
        <BrandLogo name={subscription.name} category={subscription.category} />
        <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <p className="line-clamp-2 text-sm font-semibold tracking-tight leading-5 sm:text-[15px]">{subscription.name}</p>
            {trialActive ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary">
                <Clock3 className="h-3 w-3" />
                Free trial
              </span>
            ) : null}
            {subscription.status !== 'active' ? (
              <span className="inline-flex rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
                {paymentStatusLabel(subscription.status)}
              </span>
            ) : null}
            {subscription.amount_type === 'variable' ? (
              <span className="inline-flex rounded-full bg-muted px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
                Estimated
              </span>
            ) : null}
          </div>
          <p className="truncate text-xs text-muted-foreground mt-1.5">
            {formatCategory(subscription.category)}
            {trialActive && trialEnd
              ? <span className="ml-1.5">· trial ends {trialEnd}</span>
              : nextDate && remindersAvailable
                ? <span className="ml-1.5">· next {nextDate}</span>
                : null}
            {lifecycleDate ? (
              <span className="ml-1.5">
                · {subscription.status === 'paused' ? 'resumes' : subscription.status === 'cancelling' ? 'ends' : 'final date'}{' '}
                {formatNextDate(lifecycleDate)}
              </span>
            ) : null}
            {subscription.full_amount != null && (
              <span className="ml-1.5">
                · your share of{' '}
                {formatCurrency(subscription.full_amount, subscription.currency)}
              </span>
            )}
          </p>
        </div>
      </div>

      {/* Right — amount + actions */}
      <div className="flex shrink-0 items-center gap-1 sm:gap-4">
        <div className="text-right">
          <p className="font-semibold text-sm tabular-nums leading-tight">
            {subscription.amount_type === 'variable' ? '≈ ' : ''}
            {formatCurrency(subscription.amount, subscription.currency)}
            <span className="mt-1 block text-[11px] font-normal text-muted-foreground sm:ml-1 sm:mt-0 sm:inline sm:text-xs">
              <span className="hidden sm:inline">· </span>{cadenceLabel(subscription).toLowerCase()}
            </span>
          </p>
          {trialActive ? (
            <p className="mt-0.5 text-[10px] font-medium text-primary">after trial</p>
          ) : null}
          {extras && extras.count > 0 ? (
            <p className="mt-0.5 text-xs font-medium text-amber-700 tabular-nums dark:text-amber-300">
              +{formatCurrency(extras.total_in_base, extras.base_currency)} in extras · 3 months
            </p>
          ) : null}
          {introActive && trialEnd ? (
            <p className="mt-0.5 text-xs font-medium text-primary tabular-nums">
              {formatCurrency(subscription.intro_amount ?? 0, subscription.currency)} until {trialEnd}
            </p>
          ) : null}

        </div>

        {!confirming ? (
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <Button variant="ghost" size="icon" className="text-muted-foreground" aria-label={`Options for ${subscription.name}`}><Ellipsis className="h-5 w-5" /></Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content align="end" sideOffset={6} className="z-50 w-64 max-w-[calc(100vw-2rem)] rounded-2xl border border-border bg-popover p-2 text-popover-foreground shadow-lg">
                {!trialActive && monthlyBase !== null && yearlyBase !== null ? (
                  <DropdownMenu.Label className="px-3 py-3 text-xs leading-5 text-muted-foreground">{subscription.amount_type === 'variable' ? '≈ ' : ''}{formatCurrency(monthlyBase, baseCurrency)} in {monthShort}<br />{formatCurrency(yearlyBase, baseCurrency)} per year</DropdownMenu.Label>
                ) : null}
                {!trialActive && !canShowConversion && subscription.currency !== baseCurrency ? <DropdownMenu.Label className="px-3 py-2 text-xs text-muted-foreground">{ratesLoading ? 'Loading exchange rate…' : `${subscription.currency} conversion unavailable`}</DropdownMenu.Label> : null}
                <DropdownMenu.Item onSelect={() => onEdit(subscription)} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl px-3 text-sm outline-none focus:bg-muted"><Pencil className="h-4 w-4" />Edit payment</DropdownMenu.Item>
                {remindersAvailable ? <DropdownMenu.Item onSelect={() => onReminders(subscription)} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl px-3 text-sm outline-none focus:bg-muted"><Bell className="h-4 w-4" />Manage reminders</DropdownMenu.Item> : null}
                {onAskAssistant && !terminal ? <DropdownMenu.Item onSelect={() => onAskAssistant(subscription)} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl px-3 text-sm outline-none focus:bg-muted"><Sparkles className="h-4 w-4" />Explore alternatives</DropdownMenu.Item> : null}
                <DropdownMenu.Separator className="my-1 h-px bg-border" />
                <DropdownMenu.Item onSelect={() => setConfirming(true)} className="flex min-h-11 cursor-pointer items-center gap-3 rounded-xl px-3 text-sm text-destructive outline-none focus:bg-destructive/10"><Trash2 className="h-4 w-4" />Remove from Pocketday</DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        ) : null}

      </div>

      {confirming ? (
        <div className="col-span-2 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-destructive/5 p-3">
          <p className="text-xs text-muted-foreground">Remove this record? This won&apos;t cancel the service.</p>
          <div className="flex gap-2"><Button variant="ghost" size="sm" onClick={() => setConfirming(false)} disabled={deleting}>Keep it</Button><Button variant="destructive" size="sm" onClick={handleDelete} disabled={deleting}>{deleting ? 'Removing…' : 'Remove'}</Button></div>
        </div>
      ) : null}

    </div>
  )
}
