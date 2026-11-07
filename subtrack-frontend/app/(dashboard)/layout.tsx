import Navbar from '@/components/layout/Navbar'
import { BackendGate } from '@/components/layout/BackendGate'
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
    <BackendGate>
    <CurrencyProvider>
      <ApiCacheProvider>
      <AgentPageContextProvider>
        <PaymentEditorProvider>
        <div className="flex min-h-screen flex-col">
          <Navbar />
          <main id="main-content" className="app-main min-w-0 flex-1 bg-background pb-[calc(5rem+env(safe-area-inset-bottom))] pt-16 md:pb-8 md:pt-0 md:pl-56 lg:pl-60">
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
    </BackendGate>
  )
}
