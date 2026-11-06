'use client'

import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import type { ForecastCharge, SubscriptionForecast } from '@/types'
import { Button } from '@/components/ui/button'
import { BrandLogo } from '@/components/shared/BrandLogo'
import { useEditPayment } from '@/components/subscriptions/PaymentEditor'
import { formatCurrency } from '@/lib/utils/currency'
import { formatStoredDate } from '@/lib/utils/dates'

interface Props {
  forecast: SubscriptionForecast | null
  error: string
  retrying: boolean
  onRetry: () => void
}

function amountLabel(charge: ForecastCharge, estimated: boolean) {
  const inBase = charge.charge_amount_in_base
  const approx = charge.charge_amount_is_estimate || (estimated && charge.currency !== charge.base_currency)
  return `${approx ? '≈ ' : ''}${formatCurrency(inBase ?? charge.amount, inBase === null ? charge.currency : charge.base_currency)}`
}

function ChargeRow({ charge, estimated, showDate, onSelect }: { charge: ForecastCharge; estimated: boolean; showDate: boolean; onSelect?: () => void }) {
  const edit = useEditPayment()
  return (
    <li>
      <button
        type="button"
        onClick={() => { onSelect?.(); edit(charge.id) }}
        title="Edit this payment"
        className="group flex min-h-11 w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left transition-colors hover:bg-muted"
      >
        <BrandLogo name={charge.name} category={charge.category} className="h-8 w-8" />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[15px] font-medium text-foreground">{charge.name}</span>
          {showDate || charge.charge_kind === 'trial_conversion' ? (
            <span className="block truncate text-[13px] text-muted-foreground">
              {showDate ? formatStoredDate(charge.due_at, { weekday: 'short', day: 'numeric', month: 'short' }) : ''}
              {showDate && charge.charge_kind === 'trial_conversion' ? ' · ' : ''}
              {charge.charge_kind === 'trial_conversion' ? 'First charge after trial' : ''}
            </span>
          ) : null}
        </span>
        <span className="shrink-0 text-[15px] font-semibold tabular-nums text-foreground">{amountLabel(charge, estimated)}</span>
        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/50" aria-hidden="true" />
      </button>
    </li>
  )
}

function Group({ title, charges, estimated, empty, showDate = false, onSelect }: {
  onSelect?: () => void
  title: string
  charges: ForecastCharge[]
  estimated: boolean
  empty: string
  showDate?: boolean
}) {
  return (
    <div className="border-t border-border pt-4 first:border-t-0 first:pt-0">
      <h3 className="px-2 text-[13px] font-medium text-muted-foreground">{title}</h3>
      {charges.length === 0 ? (
        <p className="px-2 py-2 text-sm text-muted-foreground/80">{empty}</p>
      ) : (
        <ul className="mt-1 divide-y divide-border/60">
          {charges.map((charge, index) => (
            <ChargeRow key={`${charge.id}-${charge.due_at}-${index}`} charge={charge} estimated={estimated} showDate={showDate} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </div>
  )
}

/** The first thing on the dashboard: what is being paid today, tomorrow, and next. */
export function ComingUp({ forecast, error, retrying, onRetry }: Props) {
  const [showLater, setShowLater] = useState(false)

  if (!forecast) {
    if (!error) return null
    return (
      <section className="flex items-center justify-between gap-3 rounded-2xl bg-card p-5 shadow-sm sm:p-6">
        <p className="text-sm text-muted-foreground">We couldn&apos;t load your upcoming payments.</p>
        <Button size="sm" variant="outline" disabled={retrying} onClick={onRetry}>
          {retrying ? 'Trying again…' : 'Try again'}
        </Button>
      </section>
    )
  }

  const estimated = forecast.currency_conversion.status === 'estimated'
  const today = forecast.charges.filter(charge => charge.days_until_due <= 0)
  const tomorrow = forecast.charges.filter(charge => charge.days_until_due === 1)
  const later = forecast.charges.filter(charge => charge.days_until_due > 1)
  const next = later[0]
  const todayTotal = today.reduce((sum, charge) => sum + (charge.charge_amount_in_base ?? 0), 0)

  return (
    <section className="h-full rounded-2xl bg-card p-5 shadow-sm sm:p-6" aria-labelledby="coming-up-heading">
      <div className="flex items-baseline justify-between gap-4">
        <h2 id="coming-up-heading" className="text-[17px] font-semibold text-foreground">Coming up</h2>
        {today.length > 0 ? (
          <p className="text-sm text-muted-foreground">
            <span className="font-semibold tabular-nums text-foreground">
              {formatCurrency(todayTotal, forecast.currency_conversion.base_currency)}
            </span>{' '}
            due today
          </p>
        ) : null}
      </div>

      <div className="mt-5 space-y-4">
        <Group title="Today" charges={today} estimated={estimated} empty="Nothing due today." />
        <Group title="Tomorrow" charges={tomorrow} estimated={estimated} empty="Nothing due tomorrow." />
        {later.length > 0 ? (
          <Group
            title="Next payment"
            charges={[next]}
            estimated={estimated}
            empty=""
            showDate
          />
        ) : today.length === 0 && tomorrow.length === 0 ? (
          <p className="px-2 text-sm text-muted-foreground">Nothing else is due in the next 2 weeks.</p>
        ) : null}
      </div>

      {later.length > 1 ? (
        <button
          type="button"
          onClick={() => setShowLater(true)}
          className="mt-3 flex min-h-11 items-center gap-1 px-2 text-sm font-medium text-primary hover:underline"
        >
          See all {later.length} in the next 2 weeks
          <ChevronRight className="h-4 w-4" aria-hidden="true" />
        </button>
      ) : null}

      <Dialog open={showLater} onOpenChange={setShowLater}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Next 2 weeks</DialogTitle>
          </DialogHeader>
          <Group
            title={`${later.length} payments`}
            charges={later}
            estimated={estimated}
            empty=""
            showDate
            onSelect={() => setShowLater(false)}
          />
        </DialogContent>
      </Dialog>

    </section>
  )
}
