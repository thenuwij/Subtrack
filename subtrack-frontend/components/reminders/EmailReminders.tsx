 'use client'
import { useState } from 'react'
import { toast } from 'sonner'
import { getEmailReminders, setEmailReminders } from '@/lib/api'
import { useApi } from '@/lib/hooks/useApi'
import { getAccessToken, useIsDemo } from '@/lib/auth/session'
import { Button } from '@/components/ui/button'
export function EmailReminders() {
  const query = useApi('email-reminders', getEmailReminders)
  const demo = useIsDemo()
  const [busy, setBusy] = useState(false)
  async function toggle() {
    setBusy(true)
    try { const token = await getAccessToken(); if (!token) throw new Error('Please sign in again.'); await setEmailReminders(token, !query.data?.enabled); await query.mutate() }
    catch (error) { toast.error(error instanceof Error ? error.message : 'Could not update email reminders.') }
    finally { setBusy(false) }
  }
  return <section id="email-reminders" className="scroll-mt-20 rounded-2xl bg-card p-6 shadow-sm"><h2 className="text-[17px] font-semibold">Email reminders</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">Get an email before a payment or trial ends. Add reminders from a payment’s menu; choose how many days before. You can turn emails off here at any time.</p>{query.error ? <Button variant="outline" className="mt-4" onClick={() => void query.mutate()}>Retry loading email settings</Button> : <><p className="mt-2 text-xs text-muted-foreground">{demo ? 'Email delivery is unavailable in the demo.' : !query.data ? 'Loading…' : !query.data.configured ? 'Email delivery has not been configured yet.' : query.data.enabled ? `Enabled for ${query.data.email}` : 'Email reminders are off.'}</p><Button variant="outline" className="mt-4" disabled={busy || demo || !query.data || (!query.data.configured && !query.data.enabled)} onClick={() => void toggle()}>{busy ? 'Saving…' : query.data?.enabled ? 'Turn off email reminders' : 'Turn on email reminders'}</Button></>}</section>
}
