import type { Category } from '@/types'

export const HOW_OFTEN = {
  weekly: { label: 'Weekly', interval_unit: 'week', interval_count: 1 },
  fortnightly: { label: 'Fortnightly', interval_unit: 'week', interval_count: 2 },
  monthly: { label: 'Monthly', interval_unit: 'month', interval_count: 1 },
  quarterly: { label: 'Quarterly', interval_unit: 'month', interval_count: 3 },
  yearly: { label: 'Yearly', interval_unit: 'year', interval_count: 1 },
} as const

export type HowOften = keyof typeof HOW_OFTEN

export function howOftenOf(unit: string, count: number): HowOften {
  const match = (Object.keys(HOW_OFTEN) as HowOften[]).find(
    key => HOW_OFTEN[key].interval_unit === unit && HOW_OFTEN[key].interval_count === count,
  )
  return match ?? 'monthly'
}

/**
 * Common Australian bills for the setup pick list. Amounts are left for the
 * user to fill in: prices change and plans differ, and a wrong guess would
 * make the first number wrong.
 */
export const COMMON_BILLS: { name: string; category: Category; howOften: HowOften }[] = [
  { name: 'Rent', category: 'housing', howOften: 'weekly' },
  { name: 'Mortgage', category: 'housing', howOften: 'monthly' },
  { name: 'Electricity', category: 'utilities', howOften: 'quarterly' },
  { name: 'Gas', category: 'utilities', howOften: 'quarterly' },
  { name: 'Water', category: 'utilities', howOften: 'quarterly' },
  { name: 'Phone plan', category: 'phone_internet', howOften: 'monthly' },
  { name: 'Internet', category: 'phone_internet', howOften: 'monthly' },
  { name: 'Car insurance', category: 'insurance', howOften: 'monthly' },
  { name: 'Health insurance', category: 'insurance', howOften: 'monthly' },
  { name: 'Car rego', category: 'transport', howOften: 'yearly' },
  { name: 'Car loan', category: 'debt', howOften: 'monthly' },
  { name: 'Afterpay', category: 'debt', howOften: 'fortnightly' },
  { name: 'Gym', category: 'fitness', howOften: 'weekly' },
  { name: 'Netflix', category: 'streaming', howOften: 'monthly' },
  { name: 'Spotify', category: 'streaming', howOften: 'monthly' },
  { name: 'Disney+', category: 'streaming', howOften: 'monthly' },
  { name: 'Stan', category: 'streaming', howOften: 'monthly' },
  { name: 'Binge', category: 'streaming', howOften: 'monthly' },
  { name: 'Kayo', category: 'streaming', howOften: 'monthly' },
  { name: 'Amazon Prime', category: 'streaming', howOften: 'monthly' },
  { name: 'YouTube Premium', category: 'streaming', howOften: 'monthly' },
  { name: 'Apple Music', category: 'streaming', howOften: 'monthly' },
  { name: 'Paramount+', category: 'streaming', howOften: 'monthly' },
  { name: 'iCloud+', category: 'cloud', howOften: 'monthly' },
  { name: 'Google One', category: 'cloud', howOften: 'monthly' },
  { name: 'Microsoft 365', category: 'software', howOften: 'yearly' },
  { name: 'ChatGPT Plus', category: 'software', howOften: 'monthly' },
  { name: 'Adobe', category: 'software', howOften: 'monthly' },
  { name: 'Uber One', category: 'memberships', howOften: 'monthly' },
  { name: 'Childcare', category: 'childcare', howOften: 'weekly' },
]
