'use client'

import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { LogoMark } from '@/components/layout/Logo'
import { Button } from '@/components/ui/button'
import { backendRecentlyAwake, pingBackend } from '@/lib/backend-status'

type Phase = 'checking' | 'waking' | 'ready' | 'failed'

// Show nothing for a moment so an awake server never flashes the screen.
const QUIET_MS = 1200
const RETRY_EVERY_MS = 3000
// Cold starts on the free plan usually take 30–60 seconds.
const GIVE_UP_AFTER_MS = 120_000
const EXPECTED_MS = 50_000

/**
 * Holds the app back until the API answers. On the free hosting plan the
 * server sleeps when idle, and without this every page would sit on empty
 * skeletons or show errors for up to a minute with no explanation.
 */
export function BackendGate({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>('checking')
  const [elapsed, setElapsed] = useState(0)
  const startedAt = useRef(0)

  const run = useCallback(async () => {
    startedAt.current = Date.now()
    // Read here, not in useState, so server and browser render the same first frame.
    if (backendRecentlyAwake()) {
      setPhase('ready')
      return
    }
    setElapsed(0)
    setPhase('checking')
    const quiet = setTimeout(() => setPhase(current => (current === 'checking' ? 'waking' : current)), QUIET_MS)
    try {
      while (Date.now() - startedAt.current < GIVE_UP_AFTER_MS) {
        if (await pingBackend()) {
          setPhase('ready')
          return
        }
        await new Promise(resolve => setTimeout(resolve, RETRY_EVERY_MS))
      }
      setPhase('failed')
    } finally {
      clearTimeout(quiet)
    }
  }, [])

  useEffect(() => {
    if (phase !== 'checking' || startedAt.current) return
    // Deferred so the first check isn't a synchronous state update in an effect.
    const id = setTimeout(() => void run(), 0)
    return () => clearTimeout(id)
  }, [phase, run])

  useEffect(() => {
    if (phase !== 'waking') return
    const id = setInterval(() => setElapsed(Date.now() - startedAt.current), 250)
    return () => clearInterval(id)
  }, [phase])

  if (phase === 'ready') return <>{children}</>
  if (phase === 'checking') return <div className="min-h-screen bg-background" aria-busy="true" />

  // Eases toward 95% so the bar keeps moving but never claims to be done.
  const progress = Math.min(95, (1 - Math.exp(-elapsed / (EXPECTED_MS / 2))) * 100)

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6">
      <div className="w-full max-w-sm text-center" role="status" aria-live="polite">
        <LogoMark className="mx-auto h-12 w-12" />
        {phase === 'failed' ? (
          <>
            <h1 className="mt-6 text-[17px] font-semibold text-foreground">Subtrack is taking too long to start</h1>
            <p className="mt-2 text-[15px] text-muted-foreground">
              The server didn&apos;t answer in time. Check your connection and try again.
            </p>
            <Button className="mt-6" onClick={() => void run()}>Try again</Button>
          </>
        ) : (
          <>
            <h1 className="mt-6 text-[17px] font-semibold text-foreground">Starting Subtrack…</h1>
            <p className="mt-2 text-[15px] text-muted-foreground">
              Getting things ready. This can take up to a minute on your first visit.
            </p>
            <div
              className="mt-6 h-1.5 w-full overflow-hidden rounded-full bg-muted"
              role="progressbar"
              aria-label="Starting Subtrack"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(progress)}
            >
              <div className="h-full rounded-full bg-primary transition-[width] duration-300 ease-out" style={{ width: `${progress}%` }} />
            </div>
            <p className="mt-3 text-[13px] tabular-nums text-muted-foreground">{Math.floor(elapsed / 1000)}s</p>
          </>
        )}
      </div>
    </div>
  )
}
