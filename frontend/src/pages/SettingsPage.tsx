import { useState } from 'react'
import { api, type ConnectionResult, type Settings } from '../api'

interface SettingsPageProps {
  settings: Settings
  onSettingsChange: (s: Settings) => void
  onClose: () => void
}

type EditableKey = Exclude<keyof Settings, 'setup_completed'>

const FIELDS: { key: EditableKey; label: string; type?: 'password' | 'number' }[] = [
  { key: 'llm_base_url', label: 'Model server URL' },
  { key: 'llm_api_key', label: 'API key (optional)', type: 'password' },
  { key: 'chat_model', label: 'Chat model' },
  { key: 'embedding_model', label: 'Embedding model' },
  { key: 'stt_model', label: 'Speech-to-text model' },
  { key: 'tts_voice_a', label: 'Voice for Host A' },
  { key: 'tts_voice_b', label: 'Voice for Host B' },
  { key: 'max_sources_per_notebook', label: 'Maximum sources per notebook', type: 'number' },
  { key: 'max_upload_mb', label: 'Maximum file size (MB)', type: 'number' },
  { key: 'retrieval_top_k', label: 'Passages used per answer', type: 'number' },
  { key: 'context_window_tokens', label: 'Model context window (tokens)', type: 'number' },
]

export function SettingsPage({ settings, onSettingsChange, onClose }: SettingsPageProps) {
  const [draft, setDraft] = useState<Settings>(settings)
  const [message, setMessage] = useState<string | null>(null)
  const [connection, setConnection] = useState<ConnectionResult | null>(null)

  async function save() {
    try {
      const editable = Object.fromEntries(FIELDS.map(({ key }) => [key, draft[key]]))
      onSettingsChange(await api.updateSettings(editable))
      setMessage('Saved.')
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e))
    }
  }

  async function test() {
    try {
      await save()
      setConnection(await api.testConnection())
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <main className="mx-auto w-full max-w-2xl space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Settings</h1>
        <button type="button" onClick={onClose} className="rounded border px-3 py-1 text-sm">
          Back
        </button>
      </div>
      {FIELDS.map(({ key, label, type }) => (
        <label key={key} className="block text-sm">
          {label}
          <input
            type={type ?? 'text'}
            className="w-full rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-700"
            value={draft[key]}
            min={type === 'number' ? 1 : undefined}
            onChange={(e) =>
              setDraft({
                ...draft,
                [key]:
                  type === 'number'
                    ? Math.max(1, parseInt(e.target.value, 10) || 1)
                    : e.target.value,
              })
            }
          />
        </label>
      ))}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={save}
          className="rounded bg-blue-600 px-4 py-1.5 text-sm text-white"
        >
          Save
        </button>
        <button type="button" onClick={test} className="rounded border px-4 py-1.5 text-sm">
          Test connection
        </button>
      </div>
      {message && <p role="status">{message}</p>}
      {connection && (
        <div role="status" className="text-sm">
          <p>{connection.message}</p>
          {connection.ok && connection.models.length > 0 && (
            <ul className="ml-5 list-disc">
              {connection.models.map((m) => (
                <li key={m}>{m}</li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-neutral-500">
            To install a missing model, run: <code>ollama pull &lt;model name&gt;</code>
          </p>
        </div>
      )}
    </main>
  )
}
