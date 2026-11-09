import type { WorkspaceBlockResult } from '@/types'
import { BudgetBlock } from '@/components/workspace/blocks/BudgetBlock'
import { ChecklistBlock } from '@/components/workspace/blocks/ChecklistBlock'
import { GoalProgressBlock } from '@/components/workspace/blocks/GoalProgressBlock'
import { NotesBlock } from '@/components/workspace/blocks/NotesBlock'
import { PaymentListBlock } from '@/components/workspace/blocks/PaymentListBlock'
import { SharedCostsBlock } from '@/components/workspace/blocks/SharedCostsBlock'
import { SpendingTrendBlock } from '@/components/workspace/blocks/SpendingTrendBlock'
import { TransactionLogBlock } from '@/components/workspace/blocks/TransactionLogBlock'
import { UpcomingPaymentsBlock } from '@/components/workspace/blocks/UpcomingPaymentsBlock'
import { BlockFrame, EmptyLine } from '@/components/workspace/blocks/shared'
import { formatCategory } from '@/lib/utils/categories'

const DEFAULT_TITLES: Record<string, string> = {
  payment_list: 'Payments',
  transaction_log: 'Spending and income',
  budget: 'Budgets',
  goal_progress: 'Goals',
  upcoming_payments: 'Coming up',
  spending_trend: 'Spending by month',
  checklist: 'Checklist',
  shared_costs: 'Shared costs',
  notes: 'Notes',
}

interface BlockViewProps {
  block: WorkspaceBlockResult
  base: string
  saving: boolean
  onToggleChecklist: (index: number) => void
  onSaveNotes: (text: string) => Promise<void>
}

export function BlockView({ block, base, saving, onToggleChecklist, onSaveNotes }: BlockViewProps) {
  const title = block.title ?? DEFAULT_TITLES[block.type ?? ''] ?? (block.type ? formatCategory(block.type) : 'Block')

  if (block.error !== undefined) {
    return (
      <BlockFrame title={title}>
        <EmptyLine>{block.error}</EmptyLine>
      </BlockFrame>
    )
  }

  switch (block.type) {
    case 'payment_list':
      return <PaymentListBlock title={title} data={block.data} base={base} />
    case 'upcoming_payments':
      return <UpcomingPaymentsBlock title={title} data={block.data} base={base} />
    case 'transaction_log':
      return <TransactionLogBlock title={title} data={block.data} />
    case 'budget':
      return <BudgetBlock title={title} budgets={block.data.budgets} base={block.data.base_currency} />
    case 'goal_progress':
      return <GoalProgressBlock title={title} goals={block.data.goals} missingCount={block.data.missing_count} />
    case 'spending_trend':
      return <SpendingTrendBlock title={title} data={block.data} />
    case 'shared_costs':
      return <SharedCostsBlock title={title} data={block.data} />
    case 'checklist':
      return <ChecklistBlock title={title} items={block.data.items} disabled={saving} onToggle={onToggleChecklist} />
    case 'notes':
      return <NotesBlock title={title} text={block.data.text} onSave={onSaveNotes} />
  }
}
