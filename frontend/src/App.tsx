import { useEffect, useState } from 'react'
import { api, type Settings } from './api'
import { Setup } from './pages/Setup'
import { SettingsPage } from './pages/SettingsPage'
import { Home } from './pages/Home'
import { NotebookPage } from './pages/NotebookPage'

const LOOPBACK = new Set(['127.0.0.1', 'localhost', '[::1]'])

/** Host to warn about when AI requests leave this machine (FR-8.4), else null. */
export function remoteHost(baseUrl: string): string | null {
  try {
    const { hostname, host } = new URL(baseUrl)
    return LOOPBACK.has(hostname) ? null : host
  } catch {
    return null
  }
}

function useHash(): string {
  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    const onChange = () => setHash(window.location.hash)
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return hash
}

export function App() {
  const [settings, setSettings] = useState<Settings | null>(null)
  const [error, setError] = useState<string | null>(null)
  const hash = useHash()

  useEffect(() => {
    api
      .getSettings()
      .then(setSettings)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  if (error)
    return (
      <p role="alert" className="p-6 text-red-600">
        {error}
      </p>
    )
  if (!settings) return <p className="p-6">Loading…</p>

  const notebookId = /^#\/notebooks\/([^/?]+)/.exec(hash)?.[1]
  const warnHost = remoteHost(settings.llm_base_url)

  return (
    <div className="flex h-screen flex-col bg-white text-neutral-900 dark:bg-neutral-950 dark:text-neutral-100">
      {warnHost && (
        <div role="status" className="bg-amber-200 px-4 py-1 text-sm text-amber-950">
          AI requests are being sent to {warnHost}.
        </div>
      )}
      {settings.setup_completed && (
        <header className="flex items-center justify-between border-b border-neutral-200 px-4 py-2 dark:border-neutral-800">
          <a href="#/" className="font-semibold">
            LocalNotebook
          </a>
          <a
            href="#/settings"
            className="rounded px-2 py-1 text-sm hover:bg-neutral-100 dark:hover:bg-neutral-800"
          >
            Settings
          </a>
        </header>
      )}
      {!settings.setup_completed ? (
        <div className="flex-1 overflow-auto">
          <Setup
            settings={settings}
            onSettingsChange={setSettings}
            onDone={() => (window.location.hash = '#/')}
          />
        </div>
      ) : hash.startsWith('#/settings') ? (
        <div className="flex-1 overflow-auto">
          <SettingsPage
            settings={settings}
            onSettingsChange={setSettings}
            onClose={() => (window.location.hash = '#/')}
            notice={
              hash.includes('why=discover')
                ? 'Discover needs a search provider. Enter the address of your SearXNG instance under Network, then save.'
                : undefined
            }
          />
        </div>
      ) : notebookId ? (
        <NotebookPage key={notebookId} notebookId={notebookId} />
      ) : (
        <div className="flex-1 overflow-auto">
          <Home />
        </div>
      )}
    </div>
  )
}
