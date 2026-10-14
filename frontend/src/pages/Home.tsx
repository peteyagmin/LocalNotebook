import { useEffect, useState } from 'react'
import { api, type Notebook } from '../api'
import { formatBytes, formatDate } from '../format'

const buttonClass =
  'rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800'

export function Home() {
  const [notebooks, setNotebooks] = useState<Notebook[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null)

  async function reload() {
    setNotebooks(await api.listNotebooks())
  }

  useEffect(() => {
    api
      .listNotebooks()
      .then(setNotebooks)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [])

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <main className="mx-auto w-full max-w-5xl space-y-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Notebooks</h1>
        <button
          type="button"
          onClick={() => setCreating(true)}
          className="rounded bg-blue-600 px-4 py-1.5 text-sm text-white"
        >
          New notebook
        </button>
      </div>

      {creating && (
        <form
          aria-label="New notebook"
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            void run(async () => {
              const nb = await api.createNotebook(newName)
              setCreating(false)
              setNewName('')
              window.location.hash = `#/notebooks/${nb.id}`
            })
          }}
        >
          <input
            autoFocus
            aria-label="Notebook name"
            placeholder="Notebook name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            className="flex-1 rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-700"
          />
          <button type="submit" className={buttonClass}>
            Create
          </button>
          <button type="button" className={buttonClass} onClick={() => setCreating(false)}>
            Cancel
          </button>
        </form>
      )}

      {error && (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      )}
      {notebooks === null && !error && <p>Loading…</p>}
      {notebooks?.length === 0 && (
        <p className="text-neutral-500">No notebooks yet. Create one to get started.</p>
      )}

      <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {notebooks?.map((nb) => (
          <li
            key={nb.id}
            className="flex flex-col gap-2 rounded border border-neutral-200 p-4 dark:border-neutral-800"
          >
            {renaming?.id === nb.id ? (
              <form
                aria-label={`Rename ${nb.name}`}
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  void run(async () => {
                    await api.renameNotebook(nb.id, renaming.name)
                    setRenaming(null)
                  })
                }}
              >
                <input
                  autoFocus
                  aria-label="New name"
                  value={renaming.name}
                  onChange={(e) => setRenaming({ id: nb.id, name: e.target.value })}
                  className="min-w-0 flex-1 rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-700"
                />
                <button type="submit" className={buttonClass}>
                  Save
                </button>
              </form>
            ) : (
              <a href={`#/notebooks/${nb.id}`} className="text-lg font-semibold hover:underline">
                {nb.name}
              </a>
            )}
            <dl className="text-xs text-neutral-500">
              <div>
                {nb.source_count} {nb.source_count === 1 ? 'source' : 'sources'} ·{' '}
                {formatBytes(nb.size_bytes)}
              </div>
              <div>Created {formatDate(nb.created_at)}</div>
              <div>Modified {formatDate(nb.updated_at)}</div>
            </dl>
            <div className="flex gap-2">
              <button
                type="button"
                className={buttonClass}
                aria-label={`Rename ${nb.name}`}
                onClick={() => setRenaming({ id: nb.id, name: nb.name })}
              >
                Rename
              </button>
              <button
                type="button"
                className={buttonClass}
                aria-label={`Duplicate ${nb.name}`}
                onClick={() => void run(() => api.duplicateNotebook(nb.id))}
              >
                Duplicate
              </button>
              <button
                type="button"
                className={buttonClass}
                aria-label={`Delete ${nb.name}`}
                onClick={() => {
                  if (
                    window.confirm(
                      `Delete "${nb.name}" and all its sources? This cannot be undone.`,
                    )
                  )
                    void run(() => api.deleteNotebook(nb.id))
                }}
              >
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
    </main>
  )
}
