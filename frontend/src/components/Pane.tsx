import type { ReactNode } from 'react'

interface PaneProps {
  title: string
  collapsed: boolean
  onToggle: () => void
  side: 'left' | 'right' | 'center'
  width?: number
  children: ReactNode
}

export function Pane({ title, collapsed, onToggle, side, width, children }: PaneProps) {
  const style = side === 'center' ? undefined : { width: collapsed ? 40 : width }
  const arrow = collapsed ? (side === 'left' ? '»' : '«') : side === 'left' ? '«' : '»'
  return (
    <section
      aria-label={title}
      style={style}
      className={`flex min-h-0 flex-col border-neutral-200 dark:border-neutral-800 ${
        side === 'center' ? 'min-w-0 flex-1' : 'shrink-0'
      }`}
    >
      <header className="flex items-center justify-between gap-2 border-b border-neutral-200 px-3 py-2 dark:border-neutral-800">
        {!collapsed && <h2 className="text-sm font-semibold">{title}</h2>}
        {side !== 'center' && (
          <button
            type="button"
            onClick={onToggle}
            aria-label={`${collapsed ? 'Expand' : 'Collapse'} ${title} pane`}
            aria-expanded={!collapsed}
            className="rounded px-1.5 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
          >
            {arrow}
          </button>
        )}
      </header>
      {!collapsed && <div className="flex-1 overflow-auto p-3 text-sm">{children}</div>}
    </section>
  )
}
