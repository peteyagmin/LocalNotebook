import { useEffect, useRef, useState } from 'react'
import { api, type Notebook } from '../api'
import { SearchBox } from '../components/SearchBox'
import type { ViewTarget } from '../components/SourceViewer'
import type { StudioTarget } from '../components/studio'
import { Workspace } from './Workspace'

export function NotebookPage({ notebookId }: { notebookId: string }) {
  const [notebook, setNotebook] = useState<Notebook | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [viewing, setViewing] = useState<ViewTarget | null>(null)
  const [studio, setStudio] = useState<StudioTarget | null>(null)
  const searchRef = useRef<HTMLInputElement>(null) as React.RefObject<HTMLInputElement>

  useEffect(() => {
    api
      .getNotebook(notebookId)
      .then(setNotebook)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [notebookId])

  // While the index is being rebuilt, keep checking until it is done (FR-8.5).
  const reindexing = notebook?.reindexing ?? false
  useEffect(() => {
    if (!reindexing) return
    const timer = setInterval(() => void api.getNotebook(notebookId).then(setNotebook), 1500)
    return () => clearInterval(timer)
  }, [reindexing, notebookId])

  async function rebuild() {
    try {
      setNotebook(await api.rebuildIndex(notebookId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  // Ctrl/Cmd+K focuses search (spec 5.2).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        searchRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  if (error)
    return (
      <p role="alert" className="p-6 text-red-600">
        {error}
      </p>
    )
  if (!notebook) return <p className="p-6">Loading…</p>

  return (
    <main className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-3 border-b border-neutral-200 px-4 py-1.5 text-sm dark:border-neutral-800">
        <a href="#/" className="rounded px-2 py-0.5 hover:bg-neutral-100 dark:hover:bg-neutral-800">
          ← Notebooks
        </a>
        <h1 className="font-semibold">{notebook.name}</h1>
        <SearchBox
          notebookId={notebookId}
          inputRef={searchRef}
          onOpen={(r) =>
            r.kind === 'note' && r.note_id
              ? setStudio({ type: 'note', id: r.note_id })
              : r.source_id &&
                setViewing({
                  sourceId: r.source_id,
                  highlight: { start: r.char_start, end: r.char_end },
                })
          }
        />
      </div>
      {(notebook.index_stale || notebook.reindexing) && (
        <div
          role="status"
          className="flex items-center gap-3 bg-amber-100 px-4 py-1.5 text-sm text-amber-950"
        >
          {notebook.reindexing ? (
            <span>Rebuilding the search index…</span>
          ) : (
            <>
              <span>
                The embedding model changed. Rebuild the search index so searching and answers use
                it.
              </span>
              <button
                type="button"
                onClick={() => void rebuild()}
                className="rounded border border-amber-900 px-2 py-0.5 hover:bg-amber-200"
              >
                Rebuild index
              </button>
            </>
          )}
        </div>
      )}
      <Workspace
        notebookId={notebookId}
        viewing={viewing}
        onView={setViewing}
        studio={studio}
        onStudio={setStudio}
      />
    </main>
  )
}
