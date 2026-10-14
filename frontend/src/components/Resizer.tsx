import { useRef } from 'react'

interface ResizerProps {
  label: string
  value: number
  min: number
  max: number
  /** +1 if dragging right grows the pane, -1 if dragging right shrinks it. */
  direction: 1 | -1
  onChange: (value: number) => void
}

export function Resizer({ label, value, min, max, direction, onChange }: ResizerProps) {
  const start = useRef<{ x: number; value: number } | null>(null)
  const clamp = (v: number) => Math.min(max, Math.max(min, v))

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={value}
      aria-valuemin={min}
      aria-valuemax={max}
      tabIndex={0}
      className="w-1 shrink-0 cursor-col-resize bg-neutral-200 hover:bg-blue-400 dark:bg-neutral-800"
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId)
        start.current = { x: e.clientX, value }
      }}
      onPointerMove={(e) => {
        if (start.current)
          onChange(clamp(start.current.value + direction * (e.clientX - start.current.x)))
      }}
      onPointerUp={() => (start.current = null)}
      onKeyDown={(e) => {
        if (e.key === 'ArrowLeft') onChange(clamp(value - direction * 16))
        if (e.key === 'ArrowRight') onChange(clamp(value + direction * 16))
      }}
    />
  )
}
