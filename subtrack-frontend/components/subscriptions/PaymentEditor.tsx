'use client'

import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'
import { useSWRConfig } from 'swr'
import { toast } from 'sonner'
import { getSubscriptions, updateSubscription } from '@/lib/api'
import { apiKeys, useApi } from '@/lib/hooks/useApi'
import { getAccessToken } from '@/lib/auth/session'
import { AddSubscriptionModal } from '@/components/subscriptions/AddSubscriptionModal'
import type { Subscription, SubscriptionInput } from '@/types'

const EditPaymentContext = createContext<(id: string) => void>(() => undefined)

/** Opens the payment edit dialog by id, from anywhere on the dashboard. */
export function useEditPayment() {
  return useContext(EditPaymentContext)
}

export function PaymentEditorProvider({ children }: { children: ReactNode }) {
  const { mutate } = useSWRConfig()
  const subscriptions = useApi<Subscription[]>(
    apiKeys.subscriptions('current'), token => getSubscriptions(token),
  )
  const [editing, setEditing] = useState<Subscription | null>(null)

  const open = useCallback((id: string) => {
    const found = subscriptions.data?.find(subscription => subscription.id === id)
    if (found) setEditing(found)
    else toast.error('That payment could not be found. Try refreshing.')
  }, [subscriptions.data])

  async function handleSubmit(formData: SubscriptionInput) {
    const token = await getAccessToken()
    if (!token || !editing) throw new Error('Your session has expired.')
    await updateSubscription(token, editing.id, formData)
    setEditing(null)
    toast.success('Payment updated')
    // Dates and amounts feed every number on the dashboard, so refresh them all.
    await mutate(key => typeof key === 'string' && key !== apiKeys.preferences)
  }

  return (
    <EditPaymentContext.Provider value={open}>
      {children}
      <AddSubscriptionModal
        open={editing !== null}
        onClose={() => setEditing(null)}
        onSubmit={handleSubmit}
        initialData={editing ?? undefined}
      />
    </EditPaymentContext.Provider>
  )
}
