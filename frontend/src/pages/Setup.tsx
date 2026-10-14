import { useEffect, useState } from 'react'
import { api, type SetupCheck, type Settings } from '../api'

interface SetupProps {
  settings: Settings
  onSettingsChange: (s: Settings) => void
  onDone: () => void
}

const inputClass =
  'w-full rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-700'

export function Setup({ settings, onSettingsChange, onDone }: SetupProps) {
  const [checks, setChecks] = useState<SetupCheck[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [chatModel, setChatModel] = useState(settings.chat_model)
  const [embeddingModel, setEmbeddingModel] = useState(settings.embedding_model)

  async function runChecks() {
    setError(null)
    try {
      setChecks((await api.getSetupChecks()).checks)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    api
      .getSetupChecks()
      .then((r) => setChecks(r.checks))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  async function saveModelsAndRecheck() {
    try {
      onSettingsChange(
        await api.updateSettings({ chat_model: chatModel, embedding_model: embeddingModel }),
      )
      await runChecks()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function finish() {
    try {
      onSettingsChange(await api.updateSettings({ setup_completed: true }))
      onDone()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <main className="mx-auto w-full max-w-2xl space-y-6 p-6">
      <h1 className="text-xl font-semibold">Setup</h1>

      <section aria-label="Models" className="space-y-3">
        <h2 className="font-semibold">Models</h2>
        <label className="block text-sm">
          Chat model
          <input
            className={inputClass}
            value={chatModel}
            onChange={(e) => setChatModel(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          Embedding model
          <input
            className={inputClass}
            value={embeddingModel}
            onChange={(e) => setEmbeddingModel(e.target.value)}
          />
        </label>
        <button
          type="button"
          onClick={saveModelsAndRecheck}
          className="rounded border border-neutral-400 px-3 py-1 text-sm"
        >
          Save and re-check
        </button>
      </section>

      <section aria-label="Checks" className="space-y-2">
        <h2 className="font-semibold">Checks</h2>
        {error && (
          <p role="alert" className="text-red-600">
            {error}
          </p>
        )}
        {checks === null && !error && <p>Checking…</p>}
        <ul className="space-y-2">
          {checks?.map((c) => (
            <li key={c.id} className="text-sm">
              <span aria-hidden="true">{c.ok ? '✓' : '✗'}</span>{' '}
              <span className="font-medium">{c.label}</span>
              <span className="sr-only">{c.ok ? ' (passed)' : ' (failed)'}</span>
              <div className="ml-5 text-neutral-500 dark:text-neutral-400">{c.detail}</div>
              {c.fix && <div className="ml-5">{c.fix}</div>}
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={runChecks}
          className="rounded border border-neutral-400 px-3 py-1 text-sm"
        >
          Re-check
        </button>
      </section>

      <button
        type="button"
        onClick={finish}
        className="rounded bg-blue-600 px-4 py-1.5 text-sm text-white"
      >
        Continue
      </button>
    </main>
  )
}
