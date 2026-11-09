'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { ChevronLeft, Pencil } from 'lucide-react'
import { useSWRConfig } from 'swr'
import { toast } from 'sonner'
import {
  deleteWorkspacePage, getWorkspacePage, getWorkspacePageData, updateWorkspacePage,
} from '@/lib/api'
import { getAccessToken } from '@/lib/auth/session'
import { useCurrency } from '@/lib/context/currency'
import { apiKeys, errorMessage, useApi } from '@/lib/hooks/useApi'
import type { WorkspaceBlockConfig } from '@/types'
import { BlockView } from '@/components/workspace/BlockView'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'

export default function WorkspacePageView() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { mutate } = useSWRConfig()
  const { baseCurrency } = useCurrency()
  const [renaming, setRenaming] = useState(false)
  const [titleDraft, setTitleDraft] = useState('')
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [saving, setSaving] = useState(false)

  const pageQuery = useApi(apiKeys.workspacePage(id), token => getWorkspacePage(token, id))
  const dataQuery = useApi(apiKeys.workspacePageData(id), token => getWorkspacePageData(token, id))
  const page = pageQuery.data
  const blocks = dataQuery.data?.blocks ?? []
  const loadError = errorMessage(pageQuery.error ?? dataQuery.error, 'Could not load this page.')

  async function authToken() {
    const token = await getAccessToken()
    if (!token) throw new Error('Your session has expired. Sign in again.')
    return token
  }

  async function refresh() {
    await mutate(key => typeof key === 'string' && key.startsWith('workspace:'))
  }

  async function patch(update: { title?: string; blocks?: WorkspaceBlockConfig[] }) {
    await updateWorkspacePage(await authToken(), id, update)
    await refresh()
  }

  async function saveTitle() {
    const next = titleDraft.trim()
    if (!next || next === page?.title) return setRenaming(false)
    try {
      await patch({ title: next })
      toast.success('Page renamed')
      setRenaming(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not rename this page.')
    }
  }

  async function toggleChecklist(blockIndex: number, itemIndex: number) {
    if (!page) return
    const next = page.blocks.map((block, index) => (
      index === blockIndex && block.type === 'checklist'
        ? { ...block, items: block.items.map((item, i) => (i === itemIndex ? { ...item, done: !item.done } : item)) }
        : block
    ))
    setSaving(true)
    try {
      await patch({ blocks: next })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not update this list.')
    } finally {
      setSaving(false)
    }
  }

  async function saveNotes(blockIndex: number, text: string) {
    if (!page) return
    const next = page.blocks.map((block, index) => (
      index === blockIndex && block.type === 'notes' ? { ...block, text } : block
    ))
    await patch({ blocks: next })
  }

  async function removePage() {
    try {
      await deleteWorkspacePage(await authToken(), id)
      toast.success('Page deleted')
      await refresh()
      router.push('/workspace')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not delete this page.')
      setConfirmingDelete(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-5 py-8 sm:px-8 sm:py-10">
      <Link href="/workspace" className="inline-flex min-h-11 items-center gap-1 text-xs font-medium text-primary">
        <ChevronLeft className="h-3.5 w-3.5" />All pages
      </Link>

      {loadError ? (
        <div className="mt-3 flex flex-col gap-3 rounded-xl border border-destructive/20 bg-destructive/5 p-4 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">{loadError}</p>
          <Button variant="outline" size="sm" onClick={() => void refresh()}>Try again</Button>
        </div>
      ) : null}

      {pageQuery.isLoading ? (
        <div className="mt-3 space-y-3"><Skeleton className="h-10" /><Skeleton className="h-32" /><Skeleton className="h-32" /></div>
      ) : page ? (
        <>
          <header className="mt-1 flex flex-wrap items-center justify-between gap-3">
            {renaming ? (
              <form className="flex min-w-0 flex-1 gap-2" onSubmit={event => { event.preventDefault(); void saveTitle() }}>
                <Input aria-label="Page title" autoFocus maxLength={120} value={titleDraft}
                  onChange={event => setTitleDraft(event.target.value)} />
                <Button type="submit" size="sm">Save</Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setRenaming(false)}>Cancel</Button>
              </form>
            ) : (
              <h1 className="page-heading flex min-w-0 items-center gap-2">
                <span className="truncate">{page.title}</span>
                <Button variant="ghost" size="icon" aria-label="Rename page"
                  onClick={() => { setTitleDraft(page.title); setRenaming(true) }}>
                  <Pencil className="h-4 w-4" />
                </Button>
              </h1>
            )}
            {confirmingDelete ? (
              <span className="flex gap-1">
                <Button size="sm" variant="destructive" onClick={() => void removePage()}>Delete page</Button>
                <Button size="sm" variant="ghost" onClick={() => setConfirmingDelete(false)}>Cancel</Button>
              </span>
            ) : (
              <Button size="sm" variant="ghost" onClick={() => setConfirmingDelete(true)}>Delete</Button>
            )}
          </header>

          <div className="mt-6 space-y-4">
            {dataQuery.isLoading ? (
              <><Skeleton className="h-32" /><Skeleton className="h-32" /></>
            ) : blocks.map((block, index) => (
              <BlockView key={index} block={block} base={baseCurrency} saving={saving}
                onToggleChecklist={itemIndex => void toggleChecklist(index, itemIndex)}
                onSaveNotes={text => saveNotes(index, text)} />
            ))}
          </div>
        </>
      ) : null}
    </div>
  )
}
