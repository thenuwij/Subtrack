'use client'

import { Sparkles } from 'lucide-react'
import { endDemo, useIsDemo } from '@/lib/auth/session'

export function DemoBanner() {
  const isDemo = useIsDemo()
  if (!isDemo) return null

  function leave(path: string) {
    endDemo()
    window.location.replace(path)
  }

  return (
    <div className="flex shrink-0 flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-border/60 bg-card/50 px-4 py-2.5 text-center text-[11px] text-muted-foreground">
      <span className="inline-flex items-center gap-1.5">
        <Sparkles className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
        Demo workspace · Sample data
      </span>
      <button type="button" onClick={() => leave('/login?mode=signup')} className="font-semibold text-primary underline-offset-2 hover:underline">
        Create a free account
      </button>
      <button type="button" onClick={() => leave('/login')} className="text-muted-foreground underline-offset-2 hover:underline">
        Exit demo
      </button>
    </div>
  )
}
