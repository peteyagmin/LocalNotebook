import { useEffect } from 'react'
import type { Settings } from './api'

type Appearance = Pick<Settings, 'theme' | 'font_size'>

function osPrefersDark(): boolean {
  return (
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  )
}

/** Set the theme (light/dark, following the OS for "system") and base font size on the page. */
export function applyAppearance({ theme, font_size }: Appearance) {
  const dark = theme === 'dark' || (theme === 'system' && osPrefersDark())
  const root = document.documentElement
  root.dataset.theme = dark ? 'dark' : 'light'
  root.style.fontSize = `${font_size}px`
}

/** Keep the page in step with the settings, and with the OS while the theme is "system". */
export function useAppearance(appearance: Appearance) {
  const { theme, font_size } = appearance
  useEffect(() => {
    applyAppearance({ theme, font_size })
    if (theme !== 'system' || typeof window.matchMedia !== 'function') return
    const query = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => applyAppearance({ theme, font_size })
    query.addEventListener?.('change', onChange)
    return () => query.removeEventListener?.('change', onChange)
  }, [theme, font_size])
}
