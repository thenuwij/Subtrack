'use client'

import { useState, useSyncExternalStore } from 'react'
import { Check, Copy, Download, ExternalLink, Loader2 } from 'lucide-react'
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

const POLL_MS = 5_000
const PROGRESS_KEY = 'pocketday.forwarding.progress'

type Stage = 'add' | 'confirm' | 'filter' | 'test' | 'done'

const STEPS: { stage: Exclude<Stage, 'done'>; title: string }[] = [
  { stage: 'add', title: 'Add Pocketday as a forwarding address' },
  { stage: 'confirm', title: 'Confirm it in Gmail' },
  { stage: 'filter', title: 'Forward only bills' },
  { stage: 'test', title: 'Check it works' },
]

function gmailUrl(section: 'fwdandpop' | 'filters', email: string | null): string {
  const account = email ? `?authuser=${encodeURIComponent(email)}` : ''
  return `https://mail.google.com/mail/${account}#settings/${section}`
}

const progressListeners = new Set<() => void>()

function subscribeProgress(listener: () => void) {
  progressListeners.add(listener)
  return () => {
    progressListeners.delete(listener)
  }
}

function storedProgress(): string | null {
  try {
    return window.localStorage.getItem(PROGRESS_KEY)
  } catch {
    return null
  }
}

function progressFor(stored: string | null, address: string): Stage | null {
  try {
    const saved = JSON.parse(stored ?? 'null')
    return saved?.address === address ? saved.stage : null
  } catch {
    return null
  }
}

function saveProgress(address: string, stage: Stage) {
  try {
    window.localStorage.setItem(PROGRESS_KEY, JSON.stringify({ address, stage }))
  } catch {
    // Progress is a convenience; the server state still drives the guide.
  }
  progressListeners.forEach(listener => listener())
}

function stageFor(data: ForwardingAddress, confirmed: Stage | null): Stage {
  if (data.received_count > 0) return 'done'
  if (!data.gmail_address) return 'add'
  if (confirmed === 'filter' || confirmed === 'test') return confirmed
  if (data.confirmation_code || data.confirmation_url) return 'confirm'
  return 'filter'
}

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

function GmailLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Button variant="outline" size="sm" asChild>
      <a href={href} target="_blank" rel="noopener noreferrer">
        {children} <ExternalLink />
      </a>
    </Button>
  )
}

function Waiting({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-center gap-2 text-xs text-muted-foreground" role="status">
      <Loader2 className="h-3.5 w-3.5 animate-spin" /> {children}
    </p>
  )
}

function Instructions({ items }: { items: React.ReactNode[] }) {
  return (
    <ol className="list-decimal space-y-1 pl-5 text-sm text-foreground marker:text-muted-foreground">
      {items.map((item, index) => <li key={index}>{item}</li>)}
    </ol>
  )
}

function Step({ n, title, state, children }: {
  n: number
  title: string
  state: 'done' | 'current' | 'next'
  children: React.ReactNode
}) {
  return (
    <li className="flex gap-3">
      <span
        className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
          state === 'done'
            ? 'bg-emerald-600 text-white'
            : state === 'current'
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted text-muted-foreground'
        }`}
      >
        {state === 'done' ? <Check className="h-3.5 w-3.5" /> : n}
      </span>
      <div className="min-w-0 flex-1 space-y-3">
        <p className={`text-sm font-medium ${state === 'next' ? 'text-muted-foreground' : 'text-foreground'}`}>{title}</p>
        {state === 'current' && children}
      </div>
    </li>
  )
}

const bold = (text: string) => <strong className="font-medium">{text}</strong>

export function ForwardingSetup({ email }: { email: string | null }) {
  const query = useApi<ForwardingAddress>(apiKeys.forwardingAddress, getForwardingAddress, {
    // Keep checking while we wait for Gmail's code or the first email.
    refreshInterval: latest => (latest && latest.received_count === 0 && latest.status !== 'paused' ? POLL_MS : 0),
  })
  const [busy, setBusy] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const stored = useSyncExternalStore(subscribeProgress, storedProgress, () => null)
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
  const stage = stageFor(data, progressFor(stored, data.address))
  const current = STEPS.findIndex(step => step.stage === stage)
  const forwardingFrom = data.gmail_address ?? email

  function advance(next: Stage) {
    if (data) saveProgress(data.address, next)
  }

  const content: Record<Exclude<Stage, 'done'>, React.ReactNode> = {
    add: (
      <>
        <div className="flex flex-wrap items-center gap-2">
          <code className="min-w-0 flex-1 break-all rounded-lg bg-muted px-3 py-2 text-sm">{data.address}</code>
          <CopyButton text={data.address} what="Address" />
        </div>
        <Instructions
          items={[
            <>Copy your private address above.</>,
            <div key="open" className="space-y-2">
              <p>Open Gmail{email ? <> as {bold(email)}</> : null}, the account your bills go to.</p>
              <GmailLink href={gmailUrl('fwdandpop', email)}>Open Gmail forwarding settings</GmailLink>
            </div>,
            <>Click {bold('Add a forwarding address')}, paste the address, then click {bold('Next')}, {bold('Proceed')} and {bold('OK')}.</>,
          ]}
        />
        <p className="text-xs text-muted-foreground">Gmail mentions a code. Skip that part: the next step appears here by itself.</p>
        <Waiting>Waiting for Gmail…</Waiting>
      </>
    ),
    confirm: (
      <>
        {data.confirmation_url ? (
          <>
            <Button asChild>
              <a href={data.confirmation_url} target="_blank" rel="noopener noreferrer">
                Confirm forwarding <ExternalLink />
              </a>
            </Button>
            <p className="text-sm">Google opens a page for {bold(forwardingFrom ?? 'your Gmail')}. Click {bold('Confirm')} there, then come back.</p>
          </>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-3 rounded-xl bg-primary/10 p-3">
              <p className="text-2xl font-semibold tracking-widest">{data.confirmation_code}</p>
              <CopyButton text={data.confirmation_code ?? ''} what="Code" />
            </div>
            <p className="text-sm">In Gmail forwarding settings, paste this code into the {bold('Verify')} box and click {bold('Verify')}.</p>
          </>
        )}
        <p className="text-xs text-muted-foreground">
          Leave {bold('Disable forwarding')} selected in Gmail. The next step forwards only bills.
        </p>
        <Button variant="outline" size="sm" onClick={() => advance('filter')}>I&apos;ve confirmed it</Button>
      </>
    ),
    filter: (
      <>
        <Instructions
          items={[
            <>
              <Button variant="outline" size="sm" onClick={() => void downloadFilter()}>
                <Download /> Download the bill filter
              </Button>
            </>,
            <div key="import" className="space-y-2">
              <p>In Gmail filter settings, scroll to the bottom and click {bold('Import filters')}.</p>
              <GmailLink href={gmailUrl('filters', forwardingFrom)}>Open Gmail filter settings</GmailLink>
            </div>,
            <>Click {bold('Choose file')}, pick the file you downloaded, then {bold('Open file')} and {bold('Create filters')}.</>,
          ]}
        />
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">Prefer to make the filter yourself?</summary>
          <div className="mt-2 space-y-2">
            <p>Create a Gmail filter with this in {bold('Has the words')}, choose {bold('Forward it to')} your Pocketday address, and save.</p>
            <div className="flex flex-wrap items-start gap-2">
              <code className="min-w-0 flex-1 break-words rounded-lg bg-muted px-3 py-2">{data.filter_query}</code>
              <CopyButton text={data.filter_query} what="Search" />
            </div>
          </div>
        </details>
        <Button variant="outline" size="sm" onClick={() => advance('test')}>I&apos;ve added the filter</Button>
      </>
    ),
    test: (
      <>
        <p className="text-sm">
          From another email account, send {bold(forwardingFrom ?? 'your Gmail')} a message with {bold('receipt')} in the
          subject. It shows up here within a minute.
        </p>
        <Waiting>Waiting for your first bill…</Waiting>
      </>
    ),
  }

  return (
    <div className="space-y-5">
      <p className="text-xs text-muted-foreground">
        Gmail sends us only the bills your filter picks. We never store the email itself.
      </p>
      {paused && (
        <p className="rounded-lg bg-amber-500/10 p-3 text-sm text-amber-700 dark:text-amber-300">
          Forwarding is paused. Mail sent to your address is ignored until you resume.
        </p>
      )}

      {stage === 'done' ? (
        <div className="flex items-start gap-3 rounded-xl bg-emerald-500/10 p-4">
          <Check className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />
          <div className="min-w-0 space-y-1">
            <p className="text-sm font-medium">Forwarding is on for {forwardingFrom}</p>
            <p className="text-xs text-muted-foreground">
              {data.received_count} bill email{data.received_count === 1 ? '' : 's'} received. New bills appear in Review.
            </p>
            <p className="break-all text-xs text-muted-foreground">Your address: {data.address}</p>
          </div>
        </div>
      ) : (
        <ol className="space-y-5">
          {STEPS.map((step, index) => (
            <Step
              key={step.stage}
              n={index + 1}
              title={step.title}
              state={index < current ? 'done' : index === current ? 'current' : 'next'}
            >
              {content[step.stage]}
            </Step>
          ))}
        </ol>
      )}

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
