import { useEffect, useRef, useState } from 'react'
import { api, type Notebook } from '../api'
import { SearchBox } from '../components/SearchBox'
import type { ViewTarget } from '../components/SourceViewer'
import { Workspace } from './Workspace'

export function NotebookPage({ notebookId }: { notebookId: string }) {
  const [notebook, setNotebook] = useState<Notebook | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [viewing, setViewing] = useState<ViewTarget | null>(null)
  const searchRef = useRef<HTMLInputElement>(null) as React.RefObject<HTMLInputElement>

  useEffect(() => {
    api
      .getNotebook(notebookId)
      .then(setNotebook)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [notebookId])

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
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-3 border-b border-neutral-200 px-4 py-1.5 text-sm dark:border-neutral-800">
        <a href="#/" className="rounded px-2 py-0.5 hover:bg-neutral-100 dark:hover:bg-neutral-800">
          ← Notebooks
        </a>
        <h1 className="font-semibold">{notebook.name}</h1>
        <SearchBox
          notebookId={notebookId}
          inputRef={searchRef}
          onOpen={(r) =>
            setViewing({
              sourceId: r.source_id,
              highlight: { start: r.char_start, end: r.char_end },
            })
          }
        />
      </div>
      <Workspace notebookId={notebookId} viewing={viewing} onView={setViewing} />
    </div>
  )
}
