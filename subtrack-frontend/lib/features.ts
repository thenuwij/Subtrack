import type { Feature } from '@/types'

export const ALL_FEATURES: Feature[] = ['spending', 'payments', 'goals', 'workspace']

export const FEATURE_OPTIONS: { id: Feature; title: string; description: string }[] = [
  { id: 'spending', title: 'Expenses and income', description: 'Log day-to-day spending and money in' },
  { id: 'payments', title: 'Monthly payments and subscriptions', description: 'Bills, subscriptions and rent, found from your email' },
  { id: 'goals', title: 'Goals and budgets', description: 'Set limits and save towards something' },
  { id: 'workspace', title: 'Custom workspace', description: 'Ask the AI to build a page for your situation' },
]
