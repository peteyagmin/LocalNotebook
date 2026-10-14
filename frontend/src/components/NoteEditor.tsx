import { useEffect, useRef, useState } from 'react'
import { api, type Citation, type Note } from '../api'
import { AnswerText } from './AnswerText'

interface NoteEditorProps {
  notebookId: string
  noteId: string
  expanded: boolean
  onToggleExpand: () => void
  onClose: () => void
  onOpenCitation: (citation: Citation) => void
  onChanged: () => void
}

const buttonClass =
  'rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800'
const AUTOSAVE_MS = 800

/** Markdown editor with a live preview. Saves automatically shortly after you stop typing. */
export function NoteEditor({
  notebookId,
  noteId,
  expanded,
  onToggleExpand,
  onClose,
  onOpenCitation,
  onChanged,
}: NoteEditorProps) {
  const [note, setNote] = useState<Note | null>(null)
  const [title, setTitle] = useState('')
  const [content, setContent] = useState('')
  const [status, setStatus] = useState<'saved' | 'saving' | 'error'>('saved')
  const [error, setError] = useState<string | null>(null)
  const dirty = useRef(false)
  const latest = useRef({ title: '', content: '' })

  useEffect(() => {
    let cancelled = false
    api
      .getNote(notebookId, noteId)
      .then((n) => {
        if (cancelled) return
        setNote(n)
        setTitle(n.title)
        setContent(n.content)
        latest.current = { title: n.title, content: n.content }
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      cancelled = true
    }
  }, [notebookId, noteId])

  async function save() {
    dirty.current = false
    setStatus('saving')
    try {
      const saved = await api.updateNote(notebookId, noteId, latest.current)
      // Take back only what the server decides (citations); keep what is being typed.
      setNote((n) => (n ? { ...n, citations: saved.citations } : n))
      setStatus('saved')
      onChanged()
    } catch (e) {
      setStatus('error')
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    if (!dirty.current) return
    const timer = setTimeout(() => void save(), AUTOSAVE_MS)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, content])

  // Do not lose edits made in the last moments before closing.
  useEffect(
    () => () => {
      if (dirty.current) {
        void api.updateNote(notebookId, noteId, latest.current).then(onChanged, () => {})
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [notebookId, noteId],
  )

  function edit(next: { title?: string; content?: string }) {
    const merged = { ...latest.current, ...next }
    latest.current = merged
    dirty.current = true
    setStatus('saving')
    if (next.title !== undefined) setTitle(next.title)
    if (next.content !== undefined) setContent(next.content)
  }

  if (!note)
    return error ? (
      <p role="alert" className="p-3 text-red-600">
        {error}
      </p>
    ) : (
      <p className="p-3">Loading…</p>
    )

  return (
    <div className="flex h-full min-h-0 flex-col" role="region" aria-label="Note editor">
      <header className="flex items-center gap-2 border-b border-neutral-200 px-3 py-2 dark:border-neutral-800">
        <button type="button" className={buttonClass} onClick={onClose}>
          ← Back
        </button>
        <input
          aria-label="Note title"
          value={title}
          onChange={(e) => edit({ title: e.target.value })}
          className="min-w-0 flex-1 rounded border border-transparent bg-transparent px-1 font-semibold hover:border-neutral-300 dark:hover:border-neutral-700"
        />
        <span role="status" className="text-xs text-neutral-500 dark:text-neutral-400">
          {status === 'saved' ? 'Saved' : status === 'saving' ? 'Saving…' : 'Not saved'}
        </span>
        <button
          type="button"
          className={buttonClass}
          aria-pressed={expanded}
          onClick={onToggleExpand}
        >
          {expanded ? 'Shrink' : 'Expand'}
        </button>
      </header>
      {error && (
        <p role="alert" className="p-2 text-red-600">
          {error}
        </p>
      )}
      <div
        className={`min-h-0 flex-1 gap-4 overflow-auto p-3 text-sm ${
          expanded ? 'grid grid-cols-2' : 'space-y-3'
        }`}
      >
        <label className="block">
          <span className="text-xs text-neutral-500 dark:text-neutral-400">Markdown</span>
          <textarea
            aria-label="Note content"
            value={content}
            onChange={(e) => edit({ content: e.target.value })}
            rows={expanded ? 24 : 10}
            className="mt-1 block w-full rounded border border-neutral-300 bg-transparent px-2 py-1 font-mono dark:border-neutral-700"
          />
        </label>
        <section aria-label="Preview">
          <span className="text-xs text-neutral-500 dark:text-neutral-400">Preview</span>
          <div className="mt-1 rounded border border-neutral-200 p-2 dark:border-neutral-800">
            <AnswerText text={content} citations={note.citations} onOpenCitation={onOpenCitation} />
          </div>
        </section>
      </div>
    </div>
  )
}
