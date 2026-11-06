import Navbar from '@/components/layout/Navbar'
import { CurrencyProvider } from '@/lib/context/currency'
import { Toaster } from '@/components/ui/sonner'
import { AgentChat } from '@/components/agent/AgentChat'
import { AgentPageContextProvider } from '@/lib/agent/page-context'
import { ApiCacheProvider } from '@/components/providers/ApiCacheProvider'
import { OnboardingTour } from '@/components/onboarding/OnboardingTour'
import { PaymentEditorProvider } from '@/components/subscriptions/PaymentEditor'
import { DemoBanner } from '@/components/demo/DemoBanner'

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <CurrencyProvider>
      <ApiCacheProvider>
      <AgentPageContextProvider>
        <PaymentEditorProvider>
        <div className="flex min-h-screen flex-col">
          <Navbar />
          <main className="min-w-0 flex-1 bg-background pb-20 pt-14 md:pb-0 md:pt-0">
            <DemoBanner />
            {children}
          </main>
          <AgentChat />
          <OnboardingTour />
        </div>
        </PaymentEditorProvider>
      </AgentPageContextProvider>
      </ApiCacheProvider>
      <Toaster />
    </CurrencyProvider>
  )
}
