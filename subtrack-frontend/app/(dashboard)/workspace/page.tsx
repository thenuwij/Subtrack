'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { LayoutGrid, Plus, Sparkles } from 'lucide-react'
import { useSWRConfig } from 'swr'
import { toast } from 'sonner'
import { createWorkspacePage, listWorkspacePages, listWorkspaceTemplates } from '@/lib/api'
import { getAccessToken } from '@/lib/auth/session'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import { formatStoredDate } from '@/lib/utils/dates'
import type { WorkspaceTemplate } from '@/types'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'

const ASSISTANT_PROMPT = 'Build me a workspace page for '

function askAssistant() {
  window.dispatchEvent(new CustomEvent('subtrack:ask-agent', { detail: { prompt: ASSISTANT_PROMPT } }))
}

interface NewPageDialogProps {
  templates: WorkspaceTemplate[]
  onClose: () => void
  onCreate: (templateId: string, title: string) => Promise<void>
}

function NewPageDialog({ templates, onClose, onCreate }: NewPageDialogProps) {
  const [templateId, setTemplateId] = useState(templates[0]?.id ?? '')
  const [title, setTitle] = useState(templates[0]?.name ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  function pick(template: WorkspaceTemplate) {
    const previous = templates.find(item => item.id === templateId)
    if (!title.trim() || title === previous?.name) setTitle(template.name)
    setTemplateId(template.id)
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!title.trim()) return setError('Give this page a title.')
    if (!templateId) return setError('Choose a template.')
    setSaving(true)
    setError('')
    try {
      await onCreate(templateId, title.trim())
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not create this page.')
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={open => { if (!open && !saving) onClose() }}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-md">
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>New page</DialogTitle>
            <DialogDescription>Start from a template. You can change it later with the assistant.</DialogDescription>
          </DialogHeader>

          <div role="radiogroup" aria-label="Template" className="space-y-2">
            {templates.map(template => (
              <button key={template.id} type="button" role="radio" aria-checked={template.id === templateId}
                onClick={() => pick(template)}
                className={`block min-h-14 w-full rounded-xl border p-3 text-left ${template.id === templateId ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/40'}`}>
                <span className="block text-sm font-medium">{template.name}</span>
                <span className="block text-xs text-muted-foreground">{template.description}</span>
              </button>
            ))}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="page-title">Title</Label>
            <Input id="page-title" maxLength={120} value={title} onChange={event => setTitle(event.target.value)} />
          </div>

          {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}

          <DialogFooter className="gap-2">
            <Button type="button" variant="ghost" onClick={onClose} disabled={saving}>Cancel</Button>
            <Button type="submit" disabled={saving}>{saving ? 'Creating…' : 'Create page'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default function WorkspacePage() {
  const router = useRouter()
  const { mutate } = useSWRConfig()
  const [creating, setCreating] = useState(false)

  const pagesQuery = useApi(apiKeys.workspacePages, token => listWorkspacePages(token))
  const templatesQuery = useApi(apiKeys.workspaceTemplates, token => listWorkspaceTemplates(token))
  const pages = pagesQuery.data ?? []
  const templates = templatesQuery.data ?? []
  const templateNames = new Map(templates.map(template => [template.id, template.name]))
  const loadError = errorMessage(pagesQuery.error, 'Could not load your pages.')

  async function createPage(templateId: string, title: string) {
    const token = await getAccessToken()
    if (!token) throw new Error('Your session has expired. Sign in again.')
    const page = await createWorkspacePage(token, { title, template_id: templateId })
    toast.success('Page created')
    await mutate(key => typeof key === 'string' && key.startsWith('workspace:'))
    router.push(`/workspace/${page.id}`)
  }

  const actions = (
    <div className="flex flex-wrap gap-2">
      <Button onClick={askAssistant}><Sparkles className="h-4 w-4" />Ask the assistant to build one</Button>
      <Button variant="outline" disabled={templates.length === 0} onClick={() => setCreating(true)}>
        <Plus className="h-4 w-4" />New page
      </Button>
    </div>
  )

  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-8 sm:px-8 sm:py-10">
      <header>
        <p className="eyebrow mb-2">Workspace</p>
        <h1 className="page-heading">Workspace</h1>
      </header>

      {loadError ? (
        <div className="mt-6 flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">{loadError}</p>
          <Button variant="outline" size="sm" onClick={() => void pagesQuery.mutate()}>Try again</Button>
        </div>
      ) : null}

      {pagesQuery.isLoading ? (
        <div className="mt-6 space-y-2"><Skeleton className="h-16" /><Skeleton className="h-16" /></div>
      ) : pages.length === 0 && !loadError ? (
        <div className="mt-6 rounded-2xl bg-card p-8 text-center shadow-sm">
          <LayoutGrid className="mx-auto h-6 w-6 text-muted-foreground" />
          <p className="mt-3 text-sm text-muted-foreground">Pages are built for your situation, like a trip budget or a shared house.</p>
          <div className="mt-4 flex justify-center">{actions}</div>
        </div>
      ) : pages.length > 0 ? (
        <>
          <div className="mt-6">{actions}</div>
          <ul className="mt-4 divide-y divide-border overflow-hidden rounded-2xl bg-card shadow-sm">
            {pages.map(page => (
              <li key={page.id}>
                <Link href={`/workspace/${page.id}`} className="block min-h-14 px-4 py-3 hover:bg-muted/40">
                  <span className="block truncate text-sm font-medium">{page.title}</span>
                  <span className="block text-xs text-muted-foreground">
                    {(page.template_id && templateNames.get(page.template_id)) || 'Built by the assistant'}
                    {page.updated_at ? ` · Updated ${formatStoredDate(page.updated_at)}` : ''}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {creating ? (
        <NewPageDialog templates={templates} onClose={() => setCreating(false)} onCreate={createPage} />
      ) : null}
    </div>
  )
}
