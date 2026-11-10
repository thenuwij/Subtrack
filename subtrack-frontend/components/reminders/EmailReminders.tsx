'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { getEmailReminders, setEmailReminders, type EmailSettings } from '@/lib/api'
import { apiKeys, useApi } from '@/lib/hooks/useApi'
import { getAccessToken, useIsDemo } from '@/lib/auth/session'
import { Button } from '@/components/ui/button'

type Switch = 'payday' | 'enabled'

const SWITCHES: { id: Switch; title: string; description: string }[] = [
  {
    id: 'payday',
    title: 'Payday email',
    description: 'On payday morning: the bills before your next pay and what’s free to spend.',
  },
  {
    id: 'enabled',
    title: 'Payment reminders',
    description: 'Before a payment or trial ends. Add reminders from a payment’s menu.',
  },
]

export function EmailReminders() {
  const query = useApi<EmailSettings>(apiKeys.emailSettings, getEmailReminders)
  const demo = useIsDemo()
  const [busy, setBusy] = useState<Switch | null>(null)
  const settings = query.data

  async function toggle(id: Switch) {
    setBusy(id)
    try {
      const token = await getAccessToken()
      if (!token) throw new Error('Please sign in again.')
      await query.mutate(await setEmailReminders(token, { [id]: !settings?.[id] }), { revalidate: false })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not update your emails.')
    } finally {
      setBusy(null)
    }
  }

  const status = demo
    ? 'Email is unavailable in the demo.'
    : !settings
      ? 'Loading…'
      : !settings.configured
        ? 'Email delivery has not been configured yet.'
        : settings.email
          ? `Sent to ${settings.email}. Turn them off here at any time.`
          : 'Emails go to your account’s address.'

  return (
    <section id="email-reminders" className="scroll-mt-20 rounded-2xl bg-card p-6 shadow-sm">
      <h2 className="text-[17px] font-semibold">Emails</h2>
      {query.error ? (
        <Button variant="outline" className="mt-4" onClick={() => void query.mutate()}>
          Retry loading email settings
        </Button>
      ) : (
        <>
          <p className="mt-2 text-xs text-muted-foreground">{status}</p>
          <div className="mt-2 divide-y divide-border">
            {SWITCHES.map(({ id, title, description }) => {
              const on = Boolean(settings?.[id])
              return (
                <div key={id} className="flex flex-col gap-3 py-4 last:pb-0 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{title}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
                  </div>
                  <Button
                    type="button"
                    variant={on ? 'default' : 'outline'}
                    role="switch"
                    aria-checked={on}
                    aria-label={title}
                    disabled={busy !== null || demo || !settings || (!settings.configured && !on)}
                    onClick={() => void toggle(id)}
                  >
                    {busy === id ? 'Saving…' : on ? 'On' : 'Off'}
                  </Button>
                </div>
              )
            })}
          </div>
        </>
      )}
    </section>
  )
}
