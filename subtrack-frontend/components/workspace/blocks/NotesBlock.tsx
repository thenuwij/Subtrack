'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { BlockFrame, EmptyLine } from './shared'

interface NotesBlockProps {
  title: string
  text: string
  onSave: (text: string) => Promise<void>
}

export function NotesBlock({ title, text, onSave }: NotesBlockProps) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(text)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function save() {
    setSaving(true)
    setError('')
    try {
      await onSave(draft)
      setEditing(false)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not save your notes.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <BlockFrame title={title}>
      {editing ? (
        <div className="space-y-2">
          <textarea aria-label={title} rows={6} maxLength={5000} value={draft} onChange={event => setDraft(event.target.value)}
            className="w-full rounded-lg border border-input bg-background p-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" />
          {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
          <div className="flex gap-1">
            <Button size="sm" disabled={saving} onClick={() => void save()}>{saving ? 'Saving…' : 'Save'}</Button>
            <Button size="sm" variant="ghost" disabled={saving} onClick={() => { setDraft(text); setError(''); setEditing(false) }}>Cancel</Button>
          </div>
        </div>
      ) : (
        <>
          {text ? <p className="whitespace-pre-wrap text-sm">{text}</p> : <EmptyLine>No notes yet.</EmptyLine>}
          <Button className="mt-2" size="sm" variant="ghost" onClick={() => { setDraft(text); setEditing(true) }}>Edit</Button>
        </>
      )}
    </BlockFrame>
  )
}
