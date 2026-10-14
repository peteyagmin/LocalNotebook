import { useEffect, useRef } from 'react'

// Overlays can be stacked (a menu over a pane over the page); Esc closes only the newest one.
const stack: { current: () => void }[] = []
let installed = false

function onKeyDown(e: KeyboardEvent) {
  if (e.key !== 'Escape' || e.defaultPrevented || stack.length === 0) return
  e.preventDefault()
  stack[stack.length - 1].current()
}

/** Call `onEscape` when Esc is pressed while `active` and nothing newer is open (spec 5.2). */
export function useEscape(onEscape: () => void, active = true) {
  const handler = useRef(onEscape)
  useEffect(() => {
    handler.current = onEscape
  })
  useEffect(() => {
    if (!active) return
    if (!installed) {
      window.addEventListener('keydown', onKeyDown)
      installed = true
    }
    stack.push(handler)
    return () => {
      stack.splice(stack.indexOf(handler), 1)
    }
  }, [active])
}
