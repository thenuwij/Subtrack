'use client'

import { useState } from 'react'
import { Check } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { ALL_FEATURES, FEATURE_OPTIONS } from '@/lib/features'
import { useFeatures } from '@/lib/hooks/useFeatures'
import type { Feature } from '@/types'

export function FeaturePicker() {
  const { save } = useFeatures()
  const [selected, setSelected] = useState<Feature[]>(ALL_FEATURES)
  const [saving, setSaving] = useState(false)

  function toggle(feature: Feature) {
    setSelected(current =>
      current.includes(feature) ? current.filter(item => item !== feature) : [...current, feature],
    )
  }

  async function handleContinue() {
    setSaving(true)
    try {
      await save(selected, { completeOnboarding: true })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not save your choice.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-12 sm:px-6">
      <h1 className="text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">What do you want Subtrack for?</h1>
      <p className="mt-3 text-base text-muted-foreground">Pick what you need. You can change this any time in Settings.</p>

      <div className="mt-8 grid gap-3" role="group" aria-label="Features">
        {FEATURE_OPTIONS.map(option => {
          const on = selected.includes(option.id)
          return (
            <button
              key={option.id}
              type="button"
              role="checkbox"
              aria-checked={on}
              onClick={() => toggle(option.id)}
              className={`flex min-h-16 items-center gap-4 rounded-2xl border p-4 text-left shadow-sm transition-colors ${on ? 'border-primary/40 bg-primary/5' : 'border-border bg-card hover:border-primary/30'}`}
            >
              <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md border ${on ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-background'}`}>
                {on ? <Check className="h-4 w-4" aria-hidden="true" /> : null}
              </span>
              <span className="min-w-0">
                <span className="block text-sm font-semibold text-foreground">{option.title}</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">{option.description}</span>
              </span>
            </button>
          )
        })}
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Button size="lg" onClick={() => void handleContinue()} disabled={selected.length === 0 || saving}>
          {saving ? 'Saving…' : 'Continue'}
        </Button>
        {selected.length === 0 ? <p role="status" className="text-sm text-muted-foreground">Pick at least one to continue.</p> : null}
      </div>
    </div>
  )
}
