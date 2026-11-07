import type { Subscription } from '@/types'
import { storedDateKey, todayUtcDateKey } from '@/lib/utils/dates'

/** A free trial that hasn't ended. Intro-price offers are paid, so they don't count. */
export function isActiveTrial(
  subscription: Pick<Subscription, 'trial_ends_at'> & { intro_amount?: number | null },
) {
  if (!subscription.trial_ends_at || subscription.intro_amount != null) return false
  return storedDateKey(subscription.trial_ends_at) >= todayUtcDateKey()
}
