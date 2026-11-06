'use client'

import { useCallback, useMemo } from 'react'
import { getCalendarMonth } from '@/lib/api'
import { apiKeys, useApi } from '@/lib/hooks/useApi'
import { useCurrency } from '@/lib/context/currency'
import { monthlyEquivalentNative } from '@/lib/utils/recurrence'
import type { CalendarMonthCharges, Subscription } from '@/types'

/**
 * What each payment costs in the current calendar month, from the backend's
 * real charge dates (a weekly payment counts 4 or 5 times). Until that loads,
 * or for a payment it couldn't convert, it falls back to the yearly average.
 */
export function useThisMonth() {
  const { canConvert, convertAmount } = useCurrency()
  const query = useApi<CalendarMonthCharges>(apiKeys.calendarMonth, getCalendarMonth)
  const data = query.data

  const totals = useMemo(() => {
    const map = new Map<string, number>()
    for (const charge of data?.charges ?? []) {
      if (charge.charge_amount_in_base === null) continue
      map.set(charge.id, (map.get(charge.id) ?? 0) + charge.charge_amount_in_base)
    }
    // Late fees and other one-off extras charged this month are part of its real cost.
    for (const extra of data?.extras ?? []) {
      if (extra.amount_in_base === null) continue
      map.set(extra.subscription_id, (map.get(extra.subscription_id) ?? 0) + extra.amount_in_base)
    }
    return map
  }, [data])

  const costOf = useCallback((subscription: Subscription): number | null => {
    if (!canConvert(subscription.currency)) return null
    if (data) return totals.get(subscription.id) ?? 0
    return convertAmount(monthlyEquivalentNative(subscription), subscription.currency)
  }, [data, totals, canConvert, convertAmount])

  const month = data ? new Date(data.year, data.month - 1, 1) : null
  return {
    ready: Boolean(data),
    costOf,
    monthName: month ? month.toLocaleDateString('en-AU', { month: 'long' }) : 'this month',
    monthShort: month ? month.toLocaleDateString('en-AU', { month: 'short' }) : 'mo',
  }
}
