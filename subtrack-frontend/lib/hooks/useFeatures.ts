'use client'

import { useCallback } from 'react'
import { useCurrency } from '@/lib/context/currency'
import type { Feature } from '@/types'

export function useFeatures() {
  const { enabledFeatures, saveFeatures } = useCurrency()
  const has = useCallback((feature: Feature) => enabledFeatures.includes(feature), [enabledFeatures])
  return { features: enabledFeatures, has, save: saveFeatures }
}
