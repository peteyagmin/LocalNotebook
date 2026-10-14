import { useState } from 'react'
import { api, type DiscoverSuggestion } from '../api'

const buttonClass =
  'rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800'
const inputClass =
  'w-full rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-700'

interface DialogProps {
  notebookId: string
  onDone: () => Promise<void>
  onClose: () => void
}

export function PasteDialog({ notebookId, onDone, onClose }: DialogProps) {
  const [name, setName] = useState('')
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  return (
    <form
      aria-label="Paste text"
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault()
        api
          .pasteText(notebookId, name, text)
          .then(onDone)
          .then(onClose)
          .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      }}
    >
      <input
        aria-label="Title (optional)"
        placeholder="Title (optional)"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className={inputClass}
      />
      <textarea
        aria-label="Text"
        rows={6}
        value={text}
        onChange={(e) => setText(e.target.value)}
        className={inputClass}
      />
      {error && (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <button type="submit" className={buttonClass}>
          Add
        </button>
        <button type="button" className={buttonClass} onClick={onClose}>
          Cancel
        </button>
      </div>
    </form>
  )
}

/** One or more web addresses, one per line (FR-2.9). */
export function WebsiteDialog({ notebookId, onDone, onClose }: DialogProps) {
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <form
      aria-label="Add websites"
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault()
        setBusy(true)
        setError(null)
        api
          .importUrls(notebookId, text.split('\n'))
          .then(onDone)
          .then(onClose)
          .catch((err) => setError(err instanceof Error ? err.message : String(err)))
          .finally(() => setBusy(false))
      }}
    >
      <label className="block text-xs">
        Web addresses, one per line
        <textarea
          aria-label="Web addresses"
          rows={4}
          placeholder="https://example.com/article"
          value={text}
          onChange={(e) => setText(e.target.value)}
          className={`${inputClass} mt-1 text-sm`}
        />
      </label>
      {error && (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <button type="submit" className={buttonClass} disabled={busy || !text.trim()}>
          Import
        </button>
        <button type="button" className={buttonClass} onClick={onClose}>
          Cancel
        </button>
      </div>
    </form>
  )
}

export function YouTubeDialog({ notebookId, onDone, onClose }: DialogProps) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  return (
    <form
      aria-label="Add YouTube video"
      className="space-y-2"
      onSubmit={(e) => {
        e.preventDefault()
        setBusy(true)
        setError(null)
        api
          .importUrls(notebookId, [url])
          .then(onDone)
          .then(onClose)
          .catch((err) => setError(err instanceof Error ? err.message : String(err)))
          .finally(() => setBusy(false))
      }}
    >
      <label className="block text-xs">
        YouTube video address
        <input
          aria-label="YouTube address"
          placeholder="https://www.youtube.com/watch?v=…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className={`${inputClass} mt-1 text-sm`}
        />
      </label>
      {error && (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <button type="submit" className={buttonClass} disabled={busy || !url.trim()}>
          Import
        </button>
        <button type="button" className={buttonClass} onClick={onClose}>
          Cancel
        </button>
      </div>
    </form>
  )
}

/** Search for sources on a topic, tick the ones you want, import them (FR-2.11). */
export function DiscoverDialog({ notebookId, onDone, onClose }: DialogProps) {
  const [topic, setTopic] = useState('')
  const [suggestions, setSuggestions] = useState<DiscoverSuggestion[] | null>(null)
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function search() {
    setBusy(true)
    setError(null)
    setSuggestions(null)
    try {
      const result = await api.discover(notebookId, topic)
      setSuggestions(result.suggestions)
      setPicked(new Set())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  async function importPicked() {
    setBusy(true)
    setError(null)
    try {
      await api.importUrls(notebookId, [...picked])
      await onDone()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-label="Discover sources" className="space-y-2">
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          void search()
        }}
      >
        <input
          aria-label="Topic"
          placeholder="Topic to look for"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          className={`${inputClass} text-sm`}
        />
        <button type="submit" className={buttonClass} disabled={busy || !topic.trim()}>
          Search
        </button>
      </form>
      {busy && !suggestions && <p role="status">Searching and reading candidates…</p>}
      {error && (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      )}
      {suggestions?.length === 0 && <p>No readable results. Try a different topic.</p>}
      {suggestions && suggestions.length > 0 && (
        <>
          <ul className="space-y-2">
            {suggestions.map((s) => (
              <li key={s.url} className="flex items-start gap-2">
                <input
                  type="checkbox"
                  aria-label={`Import ${s.title}`}
                  checked={picked.has(s.url)}
                  onChange={(e) => {
                    const next = new Set(picked)
                    if (e.target.checked) next.add(s.url)
                    else next.delete(s.url)
                    setPicked(next)
                  }}
                  className="mt-1"
                />
                <div className="min-w-0 text-xs">
                  <div className="font-medium">
                    <span aria-hidden="true">{s.kind === 'youtube' ? '▶ ' : '🌐 '}</span>
                    {s.title}
                  </div>
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="block truncate text-blue-700 underline dark:text-blue-300"
                  >
                    {s.url}
                  </a>
                  <p className="text-neutral-600 dark:text-neutral-400">{s.note}</p>
                </div>
              </li>
            ))}
          </ul>
          <button
            type="button"
            className={buttonClass}
            disabled={busy || picked.size === 0}
            onClick={() => void importPicked()}
          >
            Import selected ({picked.size})
          </button>
        </>
      )}
      <button type="button" className={buttonClass} onClick={onClose}>
        Close
      </button>
    </section>
  )
}
