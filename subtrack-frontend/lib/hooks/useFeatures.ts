'use client'

import { useCallback } from 'react'
import { useCurrency } from '@/lib/context/currency'
import type { Feature } from '@/types'

export function useFeatures() {
  const { enabledFeatures, onboardingCompleted, saveFeatures } = useCurrency()
  const has = useCallback((feature: Feature) => enabledFeatures.includes(feature), [enabledFeatures])
  const save = useCallback(
    (features: Feature[], options: { completeOnboarding?: boolean } = {}) =>
      saveFeatures(features, options.completeOnboarding),
    [saveFeatures],
  )
  return { features: enabledFeatures, has, onboardingCompleted, save }
}
