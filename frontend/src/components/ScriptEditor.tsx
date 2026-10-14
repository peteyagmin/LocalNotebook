import { useState } from 'react'
import { api, type AudioTurn, type Citation } from '../api'
import { SourceChips } from './SourceChips'

interface ScriptEditorProps {
  notebookId: string
  artifactId: string
  turns: AudioTurn[]
  citations: Citation[]
  onOpenCitation: (citation: Citation) => void
  /** Called after the script has been saved. */
  onSaved: () => void
  onClose: () => void
}

interface Row {
  key: number
  speaker: 'A' | 'B'
  text: string
  chunk_ids: string[]
}

const buttonClass =
  'rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800'

/** Edit the script as a list of turns: text, speaker, order, deletion (FR-6.4). */
export function ScriptEditor({
  notebookId,
  artifactId,
  turns,
  citations,
  onOpenCitation,
  onSaved,
  onClose,
}: ScriptEditorProps) {
  const initial = turns.map((t, i) => ({
    key: i,
    speaker: t.speaker,
    text: t.text,
    chunk_ids: t.chunk_ids,
  }))
  const [rows, setRows] = useState<Row[]>(initial)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const byChunk = new Map(citations.map((c) => [c.chunk_id, c]))
  const signature = (list: { speaker: string; text: string; chunk_ids: string[] }[]) =>
    JSON.stringify(list.map((r) => [r.speaker, r.text, r.chunk_ids]))
  const changed = signature(rows) !== signature(initial)

  const update = (index: number, patch: Partial<Row>) =>
    setRows(rows.map((r, i) => (i === index ? { ...r, ...patch } : r)))
  const move = (index: number, by: number) => {
    const target = index + by
    if (target < 0 || target >= rows.length) return
    const next = [...rows]
    ;[next[index], next[target]] = [next[target], next[index]]
    setRows(next)
  }

  async function save() {
    setSaving(true)
    setError(null)
    try {
      await api.saveScript(
        notebookId,
        artifactId,
        rows.map((r) => ({ speaker: r.speaker, text: r.text, chunk_ids: r.chunk_ids })),
      )
      onSaved()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <section aria-label="Script editor" className="space-y-3">
      <ol className="space-y-2">
        {rows.map((row, i) => {
          const labels = row.chunk_ids
            .map((id) => byChunk.get(id)?.label)
            .filter((n): n is number => n !== undefined)
          return (
            <li
              key={row.key}
              className="rounded border border-neutral-200 p-2 dark:border-neutral-800"
            >
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <select
                  aria-label={`Speaker for turn ${i + 1}`}
                  value={row.speaker}
                  onChange={(e) => update(i, { speaker: e.target.value as 'A' | 'B' })}
                  className="rounded border border-neutral-300 bg-transparent px-1 py-0.5 text-xs dark:border-neutral-700 dark:bg-neutral-900"
                >
                  <option value="A">Host A</option>
                  <option value="B">Host B</option>
                </select>
                <span className="text-xs text-neutral-500">Turn {i + 1}</span>
                <span className="ml-auto flex gap-1">
                  <button
                    type="button"
                    className={buttonClass}
                    aria-label={`Move turn ${i + 1} up`}
                    disabled={i === 0}
                    onClick={() => move(i, -1)}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    className={buttonClass}
                    aria-label={`Move turn ${i + 1} down`}
                    disabled={i === rows.length - 1}
                    onClick={() => move(i, 1)}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    className={buttonClass}
                    aria-label={`Delete turn ${i + 1}`}
                    onClick={() => setRows(rows.filter((_, j) => j !== i))}
                  >
                    ✕
                  </button>
                </span>
              </div>
              <textarea
                aria-label={`Text of turn ${i + 1}`}
                rows={3}
                maxLength={2000}
                value={row.text}
                onChange={(e) => update(i, { text: e.target.value })}
                className="w-full rounded border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700"
              />
              {labels.length > 0 && (
                <div>
                  <SourceChips labels={labels} citations={citations} onOpen={onOpenCitation} />
                </div>
              )}
            </li>
          )
        })}
      </ol>
      {rows.length === 0 && (
        <p className="text-neutral-500">The script is empty. Cancel to keep the old one.</p>
      )}
      {error && (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          className={buttonClass}
          disabled={!changed || saving || rows.length === 0}
          onClick={() => void save()}
        >
          Save script
        </button>
        <button type="button" className={buttonClass} onClick={onClose}>
          Cancel
        </button>
      </div>
    </section>
  )
}
