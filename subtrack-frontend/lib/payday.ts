export const PAY_SCHEDULES = {
  weekly: { pay_interval_unit: 'week', pay_interval_count: 1, label: 'Weekly' },
  fortnightly: { pay_interval_unit: 'week', pay_interval_count: 2, label: 'Fortnightly' },
  monthly: { pay_interval_unit: 'month', pay_interval_count: 1, label: 'Monthly' },
} as const

export type PaySchedule = keyof typeof PAY_SCHEDULES
