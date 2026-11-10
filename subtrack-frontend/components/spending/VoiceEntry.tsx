'use client'

import { useEffect, useRef, useState } from 'react'
import { Loader2, Mic, Square, X } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { parseTransactionText } from '@/lib/api'
import type { TransactionInput } from '@/types'
import { spendingCategoryLabel } from '@/lib/utils/spending'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'

interface SpeechAlternative { transcript: string }
interface SpeechResult { 0: SpeechAlternative }
interface RecognitionErrorEvent { error: string }
export interface Recognition {
  lang: string
  interimResults: boolean
  continuous: boolean
  onresult: ((event: { results: ArrayLike<SpeechResult> }) => void) | null
  onerror: ((event: RecognitionErrorEvent) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
  abort: () => void
}

export function speechRecognitionClass(): (new () => Recognition) | null {
  if (typeof window === 'undefined') return null
  const w = window as unknown as Record<string, new () => Recognition>
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

type Stage = 'recording' | 'review' | 'parsing' | 'approve'

export interface StartedVoice { recognition: Recognition | null; error: string }

/** Create and start recognition synchronously. Safari only allows this inside the tap handler itself. */
export function beginRecognition(): StartedVoice {
  const Recognition = speechRecognitionClass()
  if (!Recognition) return { recognition: null, error: 'unsupported' }
  const recognition = new Recognition()
  recognition.lang = navigator.language || 'en-AU'
  recognition.interimResults = true
  // Single phrase: Safari's continuous mode is unreliable, and the text is editable afterwards.
  recognition.continuous = false
  try {
    recognition.start()
    return { recognition, error: '' }
  } catch (caught) {
    console.warn('Speech recognition failed to start:', caught)
    return { recognition: null, error: caught instanceof Error ? caught.name : 'start' }
  }
}

interface VoiceEntryProps {
  /** Start by recording; false opens the text box so it works without a mic. */
  /** Recognition already started inside the user's tap, or null to open on the review step. */
  started: StartedVoice | null
  /** Saves one entry; `more` is true when further entries follow. */
  onSave: (input: TransactionInput, more: boolean) => Promise<void>
  /** Opens the normal form prefilled with this draft. */
  onEdit: (draft: TransactionInput) => void
  onCancel: () => void
}

const STAGE_ANNOUNCEMENT: Record<Stage, string> = {
  recording: 'Listening',
  review: 'Review what we heard',
  parsing: 'Reading your entry',
  approve: 'Approve your entries',
}

function recognitionMessage(code: string): string {
  if (code === 'not-allowed') return 'Microphone is blocked for this site. Allow it in your browser’s site settings, then reload. (not-allowed)'
  if (code === 'service-not-allowed') return 'This device’s speech service is off. On a Mac, turn on Siri or Dictation in System Settings, or try Chrome. (service-not-allowed)'
  if (code === 'network') return 'Voice isn’t available in this browser. Try Chrome, or type instead.'
  if (code === 'no-speech') return 'Didn’t catch anything. Try again.'
  if (code === 'audio-capture') return 'No microphone found.'
  return `Voice failed (${code}). Try again or type instead.`
}

function parseMessage(caught: unknown): string {
  const text = caught instanceof Error ? caught.message : ''
  if (/429|too many/i.test(text)) return 'Too many tries, wait a minute.'
  if (/422|amount|unprocessable/i.test(text)) return 'Couldn’t find an amount. Edit the text and try again.'
  return text || 'Could not understand that.'
}

export function VoiceEntry({ started, onSave, onEdit, onCancel }: VoiceEntryProps) {
  const [stage, setStage] = useState<Stage>(started ? 'recording' : 'review')
  const mountedRef = useRef(false)
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [drafts, setDrafts] = useState<TransactionInput[]>([])
  const [saving, setSaving] = useState(false)
  const recognitionRef = useRef<Recognition | null>(null)
  const canSpeak = speechRecognitionClass() !== null

  function stopRecognition() {
    const recognition = recognitionRef.current
    recognitionRef.current = null
    if (recognition) {
      recognition.onend = null
      recognition.onerror = null
      recognition.onresult = null
      recognition.abort()
    }
  }

  function attach({ recognition, error: startError }: StartedVoice) {
    if (!recognition) {
      setError(startError === 'unsupported'
        ? 'Voice isn’t available in this browser. Try Chrome, or type instead.'
        : `Voice failed (${startError}). Try again or type instead.`)
      setStage('review')
      return
    }
    let failed = false
    recognition.onresult = event => {
      setText(Array.from(event.results).map(result => result[0].transcript).join(' ').trim())
    }
    recognition.onerror = event => {
      console.warn('Speech recognition error:', event.error)
      failed = true
      setError(recognitionMessage(event.error))
      setStage('review')
    }
    recognition.onend = () => {
      recognitionRef.current = null
      if (!failed) setStage('review')
    }
    recognitionRef.current = recognition
    setError('')
    setStage('recording')
  }

  function startListening() {
    stopRecognition()
    setText('')
    // Called straight from a button tap, so starting here is allowed in Safari.
    attach(beginRecognition())
  }

  useEffect(() => {
    mountedRef.current = true
    if (started && recognitionRef.current !== started.recognition) attach(started)
    return () => {
      mountedRef.current = false
      // Defer so React's dev double-mount doesn't abort the recognition started by the tap.
      setTimeout(() => { if (!mountedRef.current) stopRecognition() }, 0)
    }
    // Attach once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function interpret() {
    setError('')
    setStage('parsing')
    try {
      const { data: { session } } = await createClient().auth.getSession()
      if (!session) throw new Error('Please sign in again.')
      const result = await parseTransactionText(session.access_token, text.trim())
      if (result.drafts.length === 0) throw new Error('422 no amount')
      setDrafts(result.drafts)
      setStage('approve')
    } catch (caught) {
      setError(parseMessage(caught))
      setStage('review')
    }
  }

  async function addAll() {
    setSaving(true)
    setError('')
    const remaining = [...drafts]
    try {
      while (remaining.length > 0) {
        await onSave(remaining[0], remaining.length > 1)
        remaining.shift()
      }
    } catch (caught) {
      setDrafts(remaining)
      setError(caught instanceof Error ? caught.message : 'Could not save these entries.')
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <p className="sr-only" role="status" aria-live="polite">{STAGE_ANNOUNCEMENT[stage]}</p>

      {stage === 'recording' ? (
        <div className="flex flex-col items-center gap-3 py-2 text-center">
          <span className="relative flex h-16 w-16 items-center justify-center">
            <span className="absolute inset-0 animate-ping rounded-full bg-primary/30" aria-hidden />
            <span className="relative flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground">
              <Mic className="h-6 w-6" aria-hidden />
            </span>
          </span>
          <p className="text-sm font-medium">Listening…</p>
          <p className="min-h-10 text-sm text-muted-foreground">{text || 'Say something like “lunch $12 and salary $2000”'}</p>
          <div className="flex gap-2">
            <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
            <Button type="button" onClick={() => recognitionRef.current?.stop()} aria-label="Stop recording">
              <Square className="h-4 w-4" />Stop
            </Button>
          </div>
        </div>
      ) : null}

      {stage === 'review' || stage === 'parsing' ? (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="voice-text">{text ? 'Here’s what we heard' : 'Describe your entries'}</Label>
            <textarea id="voice-text" rows={3} maxLength={1000} value={text} disabled={stage === 'parsing'}
              onChange={event => setText(event.target.value)}
              placeholder="Lunch $12, salary $2000 on Friday"
              className="w-full rounded-xl border border-input bg-transparent px-2.5 py-2 text-base outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 md:text-sm dark:bg-input/30" />
          </div>
          {error ? (
            <div role="alert" className="space-y-1 text-sm">
              <p className="text-destructive">{error}</p>
              <button type="button" className="font-medium text-primary underline-offset-4 hover:underline"
                onClick={() => { setError(''); setText('') }} disabled={stage === 'parsing'}>Type instead</button>
            </div>
          ) : null}
          <div className="flex items-center justify-between gap-2">
            <Button type="button" variant="ghost" onClick={onCancel} disabled={stage === 'parsing'}>Cancel</Button>
            <div className="flex gap-2">
              {canSpeak ? (
                <Button type="button" variant="outline" onClick={startListening} disabled={stage === 'parsing'}>
                  <Mic className="h-4 w-4" />Try again
                </Button>
              ) : null}
              <Button type="button" onClick={() => void interpret()} disabled={!text.trim() || stage === 'parsing'}>
                {stage === 'parsing' ? <><Loader2 className="h-4 w-4 animate-spin" />Reading…</> : 'Continue'}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {stage === 'approve' ? (
        <div className="space-y-3">
          <ul className="space-y-2">
            {drafts.map((item, index) => (
              <li key={`${item.name}-${index}`} className="flex items-start gap-2 rounded-xl border border-border bg-card p-3 text-sm">
                <div className="min-w-0 flex-1 space-y-0.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs font-medium">
                      {item.kind === 'income' ? 'In' : 'Out'}
                    </span>
                    <span className="font-medium">{item.amount.toFixed(2)} {item.currency}</span>
                  </div>
                  <p className="truncate">{item.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {item.kind === 'expense' ? `${spendingCategoryLabel(item.category)} · ` : ''}
                    {item.occurred_on ? item.occurred_on.slice(0, 10) : 'Today'}
                  </p>
                </div>
                <Button type="button" variant="ghost" size="sm" disabled={saving} onClick={() => onEdit(item)}>Edit</Button>
                <Button type="button" variant="ghost" size="icon-sm" disabled={saving} aria-label={`Remove ${item.name}`}
                  onClick={() => setDrafts(drafts.filter((_, i) => i !== index))}>
                  <X className="h-4 w-4" />
                </Button>
              </li>
            ))}
          </ul>
          {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
          <div className="flex justify-between gap-2">
            <Button type="button" variant="ghost" onClick={() => setStage('review')} disabled={saving}>Back</Button>
            <Button type="button" onClick={() => void addAll()} disabled={saving || drafts.length === 0}>
              {saving ? 'Saving…' : `Add ${drafts.length} ${drafts.length === 1 ? 'entry' : 'entries'}`}
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
