import type { Feature } from '@/types'

/** Bills and safe to spend: the core product, always on. */
export const DEFAULT_FEATURES: Feature[] = ['payments']

/** Parked features a user can turn on in Settings. Their data is kept either way. */
export const EXTRA_FEATURE_OPTIONS: { id: Feature; title: string; description: string }[] = [
  { id: 'spending', title: 'Expenses and income', description: 'Log day-to-day spending and money in' },
  { id: 'goals', title: 'Goals and budgets', description: 'Set limits and save towards something' },
  { id: 'workspace', title: 'Custom workspace', description: 'Ask the AI to build a page for your situation' },
]
