import { useRef, useState } from 'react'
import { api, type Source } from '../api'

const TYPE_LABEL: Record<Source['type'], string> = {
  pdf: 'PDF',
  docx: 'DOCX',
  txt: 'TXT',
  md: 'MD',
  text: 'Text',
}

interface SourcesPaneProps {
  notebookId: string
  sources: Source[] | null
  setSources: (s: Source[]) => void
  refresh: () => Promise<void>
  onOpen: (source: Source) => void
}

const buttonClass =
  'rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800'

export function SourcesPane({
  notebookId,
  sources,
  setSources,
  refresh,
  onOpen,
}: SourcesPaneProps) {
  const [error, setError] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [pasting, setPasting] = useState(false)
  const [pasteName, setPasteName] = useState('')
  const [pasteBody, setPasteBody] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function upload(files: FileList | null) {
    if (!files || files.length === 0) return
    await run(() => api.uploadFiles(notebookId, Array.from(files)))
    if (fileInput.current) fileInput.current.value = ''
  }

  async function submitPaste() {
    await run(async () => {
      await api.pasteText(notebookId, pasteName, pasteBody)
      setPasting(false)
      setPasteName('')
      setPasteBody('')
    })
  }

  return (
    <div className="space-y-3">
      <div className="relative">
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen(!menuOpen)}
          className="w-full rounded bg-blue-600 px-3 py-1.5 text-sm text-white"
        >
          Add source
        </button>
        {menuOpen && (
          <div
            role="menu"
            className="absolute left-0 right-0 z-10 mt-1 rounded border border-neutral-300 bg-white shadow dark:border-neutral-700 dark:bg-neutral-900"
          >
            <button
              role="menuitem"
              type="button"
              className="block w-full px-3 py-2 text-left hover:bg-neutral-100 dark:hover:bg-neutral-800"
              onClick={() => {
                setMenuOpen(false)
                fileInput.current?.click()
              }}
            >
              Upload files
            </button>
            <button
              role="menuitem"
              type="button"
              className="block w-full px-3 py-2 text-left hover:bg-neutral-100 dark:hover:bg-neutral-800"
              onClick={() => {
                setMenuOpen(false)
                setPasting(true)
              }}
            >
              Paste text
            </button>
          </div>
        )}
        <input
          ref={fileInput}
          type="file"
          multiple
          hidden
          aria-label="Choose files"
          accept=".pdf,.docx,.txt,.md,.markdown"
          onChange={(e) => void upload(e.target.files)}
        />
      </div>

      {pasting && (
        <form
          aria-label="Paste text"
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault()
            void submitPaste()
          }}
        >
          <input
            aria-label="Title (optional)"
            placeholder="Title (optional)"
            value={pasteName}
            onChange={(e) => setPasteName(e.target.value)}
            className="w-full rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-700"
          />
          <textarea
            aria-label="Text"
            rows={6}
            value={pasteBody}
            onChange={(e) => setPasteBody(e.target.value)}
            className="w-full rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-700"
          />
          <div className="flex gap-2">
            <button type="submit" className={buttonClass}>
              Add
            </button>
            <button type="button" className={buttonClass} onClick={() => setPasting(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {error && (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      )}

      {sources && sources.length > 0 && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-neutral-500">Use:</span>
          <button
            type="button"
            className={buttonClass}
            onClick={() =>
              void run(async () => setSources(await api.setAllSourcesEnabled(notebookId, true)))
            }
          >
            Select all
          </button>
          <button
            type="button"
            className={buttonClass}
            onClick={() =>
              void run(async () => setSources(await api.setAllSourcesEnabled(notebookId, false)))
            }
          >
            Select none
          </button>
        </div>
      )}

      {sources === null && <p className="text-neutral-500">Loading…</p>}
      {sources?.length === 0 && (
        <p className="text-neutral-500">No sources yet. Add one to get started.</p>
      )}

      <ul className="space-y-2">
        {sources?.map((s) => (
          <li key={s.id} className="rounded border border-neutral-200 p-2 dark:border-neutral-800">
            <div className="flex items-start gap-2">
              <input
                type="checkbox"
                checked={s.enabled}
                aria-label={`Use ${s.name}`}
                onChange={(e) =>
                  void run(() => api.setSourceEnabled(notebookId, s.id, e.target.checked))
                }
                className="mt-1"
              />
              <span
                className="rounded bg-neutral-200 px-1 text-xs dark:bg-neutral-800"
                title="File type"
              >
                {TYPE_LABEL[s.type]}
              </span>
              <button
                type="button"
                onClick={() => onOpen(s)}
                disabled={s.state !== 'ready'}
                className="min-w-0 flex-1 truncate text-left hover:underline disabled:no-underline"
              >
                {s.name}
              </button>
              <button
                type="button"
                aria-label={`Remove ${s.name}`}
                className="rounded px-1 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
                onClick={() => {
                  if (window.confirm(`Remove "${s.name}" from this notebook?`))
                    void run(() => api.deleteSource(notebookId, s.id))
                }}
              >
                ✕
              </button>
            </div>
            {(s.state === 'queued' || s.state === 'processing') && (
              <div className="mt-1">
                <progress
                  aria-label={`Processing ${s.name}`}
                  value={s.progress}
                  max={1}
                  className="w-full"
                />
                <div className="text-xs text-neutral-500">
                  {s.state === 'queued' ? 'Waiting…' : (s.stage ?? 'Processing…')}
                </div>
              </div>
            )}
            {s.state === 'failed' && (
              <div className="mt-1 text-xs">
                <p role="alert" className="text-red-600">
                  {s.error}
                </p>
                <button
                  type="button"
                  className={`${buttonClass} mt-1`}
                  onClick={() => void run(() => api.retrySource(notebookId, s.id))}
                >
                  Retry
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
