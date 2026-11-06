import { AgentWorkspace } from '@/components/agent/AgentWorkspace'

export default function AssistantPage() {
  return (
    <div className="h-[calc(100dvh-3.5rem-env(safe-area-inset-bottom))] md:h-[calc(100dvh-3.5rem)]">
      <AgentWorkspace variant="page" />
    </div>
  )
}
