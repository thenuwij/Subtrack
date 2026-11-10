import type { ChecklistItem } from '@/types'
import { BlockFrame, EmptyLine } from './shared'

interface ChecklistBlockProps {
  title: string
  items: ChecklistItem[]
  disabled: boolean
  onToggle: (index: number) => void
}

export function ChecklistBlock({ title, items, disabled, onToggle }: ChecklistBlockProps) {
  return (
    <BlockFrame title={title}>
      {items.length === 0 ? <EmptyLine>Nothing on this list yet. Ask the assistant to add items.</EmptyLine> : (
        <ul>
          {items.map((item, index) => (
            <li key={`${index}-${item.text}`}>
              <label className="flex min-h-11 cursor-pointer items-center gap-3 text-sm">
                <input type="checkbox" className="h-4 w-4 accent-primary" checked={item.done} disabled={disabled}
                  onChange={() => onToggle(index)} />
                <span className={item.done ? 'text-muted-foreground line-through' : ''}>{item.text}</span>
              </label>
            </li>
          ))}
        </ul>
      )}
    </BlockFrame>
  )
}
