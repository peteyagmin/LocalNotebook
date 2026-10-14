import { useRef, useState } from 'react'
import { api, type Source } from '../api'
import { useCapabilities } from '../hooks/useCapabilities'
import { formatDate } from '../format'
import { DiscoverDialog, PasteDialog, WebsiteDialog, YouTubeDialog } from './AddSourceDialogs'

const TYPE_LABEL: Record<Source['type'], { text: string; icon: string }> = {
  pdf: { text: 'PDF', icon: '' },
  docx: { text: 'DOCX', icon: '' },
  txt: { text: 'TXT', icon: '' },
  md: { text: 'MD', icon: '' },
  text: { text: 'Text', icon: '' },
  html: { text: 'HTML', icon: '' },
  epub: { text: 'EPUB', icon: '' },
  image: { text: 'Image', icon: '' },
  audio: { text: 'Audio', icon: '' },
  web: { text: 'Web', icon: '🌐 ' },
  youtube: { text: 'Video', icon: '▶ ' },
}

type Dialog = 'paste' | 'website' | 'youtube' | 'discover' | null

interface SourcesPaneProps {
  notebookId: string
  sources: Source[] | null
  setSources: (s: Source[]) => void
  refresh: () => Promise<void>
  onOpen: (source: Source) => void
}

const buttonClass =
  'rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800'
const menuItemClass =
  'block w-full px-3 py-2 text-left hover:bg-neutral-100 disabled:cursor-not-allowed disabled:opacity-60 dark:hover:bg-neutral-800'

export function SourcesPane({
  notebookId,
  sources,
  setSources,
  refresh,
  onOpen,
}: SourcesPaneProps) {
  const [error, setError] = useState<string | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [dialog, setDialog] = useState<Dialog>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const { capabilities, refresh: refreshCapabilities } = useCapabilities()

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

  const webOff = capabilities !== null && !capabilities.web_import
  const discoverOff = capabilities !== null && !capabilities.discover.allowed
  const closeDialog = () => setDialog(null)

  function choose(item: Dialog | 'upload') {
    setMenuOpen(false)
    if (item === 'upload') fileInput.current?.click()
    else if (item === 'discover' && capabilities && !capabilities.discover.configured) {
      // No search provider yet: take the user to Settings with an explanation (FR-2.11).
      window.location.hash = '#/settings?why=discover'
    } else setDialog(item)
  }

  const uploadHints = [
    capabilities && !capabilities.ocr ? 'Images and scanned pages need Tesseract (not found).' : '',
    capabilities && !capabilities.stt.installed
      ? 'Audio needs a speech-to-text model (see Settings).'
      : '',
  ].filter(Boolean)

  return (
    <div className="space-y-3">
      <div className="relative">
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          onClick={() => {
            if (!menuOpen) refreshCapabilities()
            setMenuOpen(!menuOpen)
          }}
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
              className={menuItemClass}
              onClick={() => choose('upload')}
            >
              Upload files
              {uploadHints.map((h) => (
                <span key={h} className="block text-xs text-neutral-500">
                  {h}
                </span>
              ))}
            </button>
            <button
              role="menuitem"
              type="button"
              className={menuItemClass}
              onClick={() => choose('paste')}
            >
              Paste text
            </button>
            <button
              role="menuitem"
              type="button"
              className={menuItemClass}
              disabled={webOff}
              onClick={() => choose('website')}
            >
              Website
              {webOff && (
                <span className="block text-xs text-neutral-500">
                  Turned off in Settings (Network).
                </span>
              )}
            </button>
            <button
              role="menuitem"
              type="button"
              className={menuItemClass}
              disabled={webOff}
              onClick={() => choose('youtube')}
            >
              YouTube
              {webOff && (
                <span className="block text-xs text-neutral-500">
                  Turned off in Settings (Network).
                </span>
              )}
            </button>
            <button
              role="menuitem"
              type="button"
              className={menuItemClass}
              disabled={discoverOff}
              onClick={() => choose('discover')}
            >
              Discover
              {discoverOff && (
                <span className="block text-xs text-neutral-500">
                  Turned off in Settings (Network).
                </span>
              )}
              {capabilities?.discover.allowed && !capabilities.discover.configured && (
                <span className="block text-xs text-neutral-500">Needs a search provider.</span>
              )}
            </button>
          </div>
        )}
        <input
          ref={fileInput}
          type="file"
          multiple
          hidden
          aria-label="Choose files"
          accept=".pdf,.docx,.txt,.md,.markdown,.html,.htm,.epub,.png,.jpg,.jpeg,.mp3,.wav,.m4a"
          onChange={(e) => void upload(e.target.files)}
        />
      </div>

      {dialog === 'paste' && (
        <PasteDialog notebookId={notebookId} onDone={refresh} onClose={closeDialog} />
      )}
      {dialog === 'website' && (
        <WebsiteDialog notebookId={notebookId} onDone={refresh} onClose={closeDialog} />
      )}
      {dialog === 'youtube' && (
        <YouTubeDialog notebookId={notebookId} onDone={refresh} onClose={closeDialog} />
      )}
      {dialog === 'discover' && (
        <DiscoverDialog notebookId={notebookId} onDone={refresh} onClose={closeDialog} />
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
        {sources?.map((s) => {
          const type = TYPE_LABEL[s.type]
          return (
            <li
              key={s.id}
              className="rounded border border-neutral-200 p-2 dark:border-neutral-800"
            >
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
                  title="Source type"
                >
                  <span aria-hidden="true">{type.icon}</span>
                  {type.text}
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
              {s.url && (
                <div className="mt-1 text-xs text-neutral-500">
                  <a
                    href={s.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="block truncate underline"
                  >
                    {s.url}
                  </a>
                  {s.fetched_at && <span>Captured {formatDate(s.fetched_at)}</span>}
                  {s.version_count > 0 && (
                    <span>
                      {' '}
                      · {s.version_count} earlier {s.version_count === 1 ? 'version' : 'versions'}
                    </span>
                  )}
                  {s.type === 'web' && s.state !== 'queued' && s.state !== 'processing' && (
                    <button
                      type="button"
                      className={`${buttonClass} ml-2`}
                      aria-label={`Refresh ${s.name} from web`}
                      onClick={() => void run(() => api.refreshSource(notebookId, s.id))}
                    >
                      Refresh from web
                    </button>
                  )}
                </div>
              )}
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
              {s.state === 'ready' && s.error && (
                <p role="status" className="mt-1 rounded bg-amber-100 p-1 text-xs text-amber-950">
                  {s.error} The previous capture is still in use.
                </p>
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
          )
        })}
      </ul>
    </div>
  )
}
