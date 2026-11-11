'use client'

import { useState } from 'react'
import { Check, Copy, Download, ExternalLink } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  deleteForwardingAddress,
  downloadForwardingFilter,
  getForwardingAddress,
  rotateForwardingAddress,
  setForwardingPaused,
} from '@/lib/api'
import { getAccessToken } from '@/lib/auth/session'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import type { ForwardingAddress } from '@/types'

const GMAIL_FORWARDING_URL = 'https://mail.google.com/mail/u/0/#settings/fwdandpop'
const POLL_MS = 5_000

async function copy(text: string, what: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(`${what} copied`)
  } catch {
    toast.error('Could not copy. Select the text and copy it by hand.')
  }
}

function CopyButton({ text, what }: { text: string; what: string }) {
  return (
    <Button variant="outline" size="sm" onClick={() => void copy(text, what)} className="shrink-0">
      <Copy /> Copy
    </Button>
  )
}

function Step({ n, title, done, children }: {
  n: number
  title: string
  done?: boolean
  children: React.ReactNode
}) {
  return (
    <li className="flex gap-3">
      <span
        className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
          done ? 'bg-emerald-600 text-white' : 'bg-primary/10 text-primary'
        }`}
      >
        {done ? <Check className="h-3.5 w-3.5" /> : n}
      </span>
      <div className="min-w-0 flex-1 space-y-2">
        <p className="text-sm font-medium text-foreground">{title}</p>
        {children}
      </div>
    </li>
  )
}

export function ForwardingSetup() {
  const query = useApi<ForwardingAddress>(apiKeys.forwardingAddress, getForwardingAddress, {
    // Keep checking while we wait for Gmail's code or the first email.
    refreshInterval: latest => (latest && latest.received_count === 0 && latest.status !== 'paused' ? POLL_MS : 0),
  })
  const [busy, setBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const data = query.data

  async function act(run: (token: string) => Promise<ForwardingAddress | void>, success: string) {
    setBusy(true)
    try {
      const token = await getAccessToken()
      if (!token) throw new Error('Your session has expired.')
      const next = await run(token)
      await query.mutate(next ?? undefined, { revalidate: true })
      toast.success(success)
    } catch (error) {
      toast.error(errorMessage(error, 'Something went wrong. Please try again.'))
    } finally {
      setBusy(false)
    }
  }

  async function downloadFilter() {
    try {
      const token = await getAccessToken()
      if (!token) throw new Error('Your session has expired.')
      const { blob, filename } = await downloadForwardingFilter(token)
      const href = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = href
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.setTimeout(() => URL.revokeObjectURL(href), 1_000)
    } catch (error) {
      toast.error(errorMessage(error, 'Could not download the filter.'))
    }
  }

  if (!data) {
    return (
      <p className="text-sm text-muted-foreground">
        {query.error ? errorMessage(query.error, 'Could not load your forwarding address.') : 'Loading your address...'}
      </p>
    )
  }

  const paused = data.status === 'paused'
  return (
    <div className="space-y-5">
      <p className="text-xs text-muted-foreground">
        We only read emails your filter forwards. We never store the email itself.
      </p>
      {paused && (
        <p className="rounded-lg bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-300">
          Forwarding is paused. Mail sent to your address is ignored until you resume.
        </p>
      )}

      <ol className="space-y-5">
        <Step n={1} title="Your private address" done>
          <div className="flex flex-wrap items-center gap-2">
            <code className="min-w-0 flex-1 break-all rounded-lg bg-muted px-3 py-2 text-sm">{data.address}</code>
            <CopyButton text={data.address} what="Address" />
          </div>
        </Step>

        <Step
          n={2}
          title="Tell Gmail to forward to it"
          done={Boolean(data.gmail_address) && !data.confirmation_code && !data.confirmation_url}
        >
          <p className="text-xs text-muted-foreground">
            Open Gmail settings, choose Add a forwarding address, and paste the address above.
          </p>
          <Button variant="outline" size="sm" asChild>
            <a href={GMAIL_FORWARDING_URL} target="_blank" rel="noopener noreferrer">
              Open Gmail forwarding settings <ExternalLink />
            </a>
          </Button>
          {data.confirmation_code ? (
            <div className="flex flex-wrap items-center gap-3 rounded-xl bg-primary/10 p-3">
              <div>
                <p className="text-xs text-muted-foreground">Gmail asks for this code</p>
                <p className="text-2xl font-semibold tracking-widest">{data.confirmation_code}</p>
              </div>
              <CopyButton text={data.confirmation_code} what="Code" />
            </div>
          ) : data.confirmation_url ? (
            <div className="space-y-2 rounded-xl bg-primary/10 p-3">
              <p className="text-xs text-muted-foreground">
                Gmail sent a confirm link for {data.gmail_address}. Open it while signed in to that account.
              </p>
              <Button size="sm" asChild>
                <a href={data.confirmation_url} target="_blank" rel="noopener noreferrer">
                  Confirm forwarding in Gmail <ExternalLink />
                </a>
              </Button>
            </div>
          ) : data.gmail_address ? (
            <p className="text-xs text-muted-foreground">Confirmed for {data.gmail_address}.</p>
          ) : (
            <p className="text-xs text-muted-foreground">Waiting for Gmail&apos;s confirmation. It shows up here.</p>
          )}
        </Step>

        <Step n={3} title="Forward only bills and receipts">
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => void downloadFilter()}>
              <Download /> Download filter
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            In Gmail go to Settings, Filters and Blocked Addresses, then Import filters, and choose the file.
            Or create a filter by hand with this search:
          </p>
          <div className="flex flex-wrap items-start gap-2">
            <code className="min-w-0 flex-1 break-words rounded-lg bg-muted px-3 py-2 text-xs">{data.filter_query}</code>
            <CopyButton text={data.filter_query} what="Search" />
          </div>
        </Step>

        <Step n={4} title="Send yourself a test bill" done={data.received_count > 0}>
          <p className="text-xs text-muted-foreground">
            {data.received_count > 0
              ? `Got it. ${data.received_count} bill email${data.received_count === 1 ? '' : 's'} received so far.`
              : 'Email yourself a message with "receipt" in the subject. A tick appears here when it arrives.'}
          </p>
        </Step>
      </ol>

      <div className="flex flex-wrap gap-2 border-t border-border pt-4">
        <Button
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => void act(token => setForwardingPaused(token, !paused), paused ? 'Forwarding resumed' : 'Forwarding paused')}
        >
          {paused ? 'Resume' : 'Pause'}
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => void act(rotateForwardingAddress, 'New address ready. Update Gmail to use it.')}
        >
          Rotate address
        </Button>
        <Button variant="destructive" size="sm" disabled={busy} onClick={() => setConfirmDelete(true)}>
          Delete forwarding
        </Button>
      </div>

      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete forwarding?</DialogTitle>
            <DialogDescription>
              Your address stops working and its history is removed. Bills already found stay. Remove the
              forwarding address in Gmail too. You can set it up again later.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmDelete(false)}>Cancel</Button>
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => {
                setConfirmDelete(false)
                void act(async token => { await deleteForwardingAddress(token) }, 'Forwarding deleted')
              }}
            >
              Delete forwarding
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
