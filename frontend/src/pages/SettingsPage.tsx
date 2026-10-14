import { useEffect, useState, type ReactNode } from 'react'
import { api, type ConnectionResult, type Settings, type SttStatus } from '../api'

interface SettingsPageProps {
  settings: Settings
  onSettingsChange: (s: Settings) => void
  onClose: () => void
  /** Why the user was sent here (for example from Discover without a search provider). */
  notice?: string
}

type EditableKey = Exclude<keyof Settings, 'setup_completed'>
type TextKey =
  | 'llm_base_url'
  | 'llm_api_key'
  | 'chat_model'
  | 'embedding_model'
  | 'stt_model'
  | 'tts_voice_a'
  | 'tts_voice_b'
  | 'searxng_url'
type NumberKey =
  'max_sources_per_notebook' | 'max_upload_mb' | 'retrieval_top_k' | 'context_window_tokens'
type BoolKey =
  'allow_web_import' | 'allow_discover' | 'allow_model_downloads' | 'transcribe_uncaptioned_videos'

const EDITABLE: EditableKey[] = [
  'llm_base_url',
  'llm_api_key',
  'chat_model',
  'embedding_model',
  'stt_model',
  'tts_voice_a',
  'tts_voice_b',
  'max_sources_per_notebook',
  'max_upload_mb',
  'retrieval_top_k',
  'context_window_tokens',
  'allow_web_import',
  'allow_discover',
  'allow_model_downloads',
  'transcribe_uncaptioned_videos',
  'searxng_url',
]

const inputClass =
  'w-full rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-700'

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section
      aria-label={title}
      className="space-y-3 rounded border border-neutral-200 p-4 dark:border-neutral-800"
    >
      <h2 className="font-semibold">{title}</h2>
      {children}
    </section>
  )
}

export function SettingsPage({ settings, onSettingsChange, onClose, notice }: SettingsPageProps) {
  const [draft, setDraft] = useState<Settings>(settings)
  const [message, setMessage] = useState<string | null>(null)
  const [connection, setConnection] = useState<ConnectionResult | null>(null)

  const text = (key: TextKey, label: string, type = 'text', help?: string) => (
    <label key={key} className="block text-sm">
      {label}
      <input
        type={type}
        className={inputClass}
        value={draft[key]}
        onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
      />
      {help && <span className="block text-xs text-neutral-500">{help}</span>}
    </label>
  )
  const number = (key: NumberKey, label: string) => (
    <label key={key} className="block text-sm">
      {label}
      <input
        type="number"
        min={1}
        className={inputClass}
        value={draft[key]}
        onChange={(e) =>
          setDraft({ ...draft, [key]: Math.max(1, parseInt(e.target.value, 10) || 1) })
        }
      />
    </label>
  )
  const check = (key: BoolKey, label: string, help: string) => (
    <label key={key} className="flex items-start gap-2 text-sm">
      <input
        type="checkbox"
        className="mt-1"
        checked={draft[key]}
        onChange={(e) => setDraft({ ...draft, [key]: e.target.checked })}
      />
      <span>
        {label}
        <span className="block text-xs text-neutral-500">{help}</span>
      </span>
    </label>
  )

  async function save() {
    try {
      const editable = Object.fromEntries(EDITABLE.map((key) => [key, draft[key]]))
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
      {notice && (
        <p role="status" className="rounded bg-amber-100 p-3 text-sm text-amber-950">
          {notice}
        </p>
      )}

      <Section title="Model server">
        {text('llm_base_url', 'Model server URL')}
        {text('llm_api_key', 'API key (optional)', 'password')}
      </Section>

      <Section title="Models">
        {text('chat_model', 'Chat model')}
        {text('embedding_model', 'Embedding model')}
        {text('tts_voice_a', 'Voice for Host A')}
        {text('tts_voice_b', 'Voice for Host B')}
        {number('context_window_tokens', 'Model context window (tokens)')}
        {number('retrieval_top_k', 'Passages used per answer')}
      </Section>

      <Section title="Speech to text">
        {text('stt_model', 'Speech-to-text model')}
        <SpeechModel saved={settings.stt_model} />
        {check(
          'transcribe_uncaptioned_videos',
          'Transcribe videos without captions',
          'When a YouTube video has no captions, its audio is downloaded, transcribed on this computer, and then deleted. You are responsible for complying with the platform’s terms of service.',
        )}
      </Section>

      <Section title="Limits">
        {number('max_sources_per_notebook', 'Maximum sources per notebook')}
        {number('max_upload_mb', 'Maximum file size (MB)')}
      </Section>

      <Section title="Network">
        <p className="text-xs text-neutral-500">
          The app contacts the internet only for the actions you start, and only if allowed here.
        </p>
        {check(
          'allow_web_import',
          'Import web pages and videos',
          'Fetches the addresses you give it. Pages are saved, so they work offline afterwards.',
        )}
        {check(
          'allow_discover',
          'Discover sources',
          'Searches with your search provider and reads the pages it finds.',
        )}
        {text(
          'searxng_url',
          'Search provider address (SearXNG)',
          'text',
          'The address of your own SearXNG instance, with JSON output enabled. Discover needs this.',
        )}
        {check(
          'allow_model_downloads',
          'Download speech models',
          'Models are downloaded only after you confirm.',
        )}
      </Section>

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

/** Install state of the speech-to-text model, with a confirmed download and progress (FR-8.2). */
function SpeechModel({ saved }: { saved: string }) {
  const [status, setStatus] = useState<SttStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const downloading = status?.state === 'downloading'

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = () =>
      api
        .getSttStatus()
        .then((s) => {
          if (cancelled) return
          setStatus(s)
          if (s.state === 'downloading') timer = setTimeout(poll, 1000)
        })
        .catch(() => {})
    void poll()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [saved, downloading])

  async function download() {
    if (
      !window.confirm(
        `Download the speech-to-text model "${saved}" from the internet? It can be large.`,
      )
    )
      return
    setError(null)
    try {
      setStatus(await api.startSttDownload())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  if (!status) return null
  return (
    <div className="space-y-1 text-sm" aria-label="Speech model status" role="group">
      {!status.configured && (
        <p className="text-neutral-500">
          Enter a model name and save to use audio and video transcription.
        </p>
      )}
      {status.configured && status.installed && <p>The model “{status.model}” is installed.</p>}
      {status.configured && !status.installed && status.state !== 'downloading' && (
        <div className="space-y-1">
          <p>The model “{status.model}” is not installed.</p>
          <button
            type="button"
            className="rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800"
            disabled={!status.downloads_allowed}
            onClick={() => void download()}
          >
            Download model
          </button>
          {!status.downloads_allowed && (
            <p className="text-xs text-neutral-500">Model downloads are turned off (Network).</p>
          )}
        </div>
      )}
      {status.state === 'downloading' && (
        <div>
          <progress
            aria-label="Downloading model"
            value={status.progress ?? undefined}
            max={1}
            className="w-full"
          />
          <p className="text-xs text-neutral-500">
            Downloading… {status.progress != null ? `${Math.round(status.progress * 100)}%` : ''}
          </p>
        </div>
      )}
      {(error ?? status.error) && (
        <p role="alert" className="text-red-600">
          {error ?? status.error}
        </p>
      )}
    </div>
  )
}
