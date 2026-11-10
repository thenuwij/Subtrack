import { CATEGORY_ORDER, formatCategory } from '@/lib/utils/categories'
import type { Category } from '@/types'

/** Categories offered for an expense. Income has its own single category. */
export const EXPENSE_CATEGORIES: Category[] = [
  ...(CATEGORY_ORDER as readonly Category[]).filter(category => category !== 'other'),
  'shopping', 'health', 'travel', 'personal_care', 'gifts', 'other',
]

/** One-off spending reads differently to recurring bills, so "other" is just "Other". */
export function spendingCategoryLabel(category: string) {
  return category === 'other' ? 'Other' : formatCategory(category)
}

export function currentMonthKey(todayKey: string) {
  return todayKey.slice(0, 7)
}

export function shiftMonth(month: string, delta: number) {
  const [year, number] = month.split('-').map(Number)
  const shifted = new Date(Date.UTC(year, number - 1 + delta, 1))
  return `${shifted.getUTCFullYear()}-${String(shifted.getUTCMonth() + 1).padStart(2, '0')}`
}

export function monthLabel(month: string) {
  return new Intl.DateTimeFormat('en-AU', { month: 'long', year: 'numeric', timeZone: 'UTC' })
    .format(new Date(`${month}-01T12:00:00Z`))
}
