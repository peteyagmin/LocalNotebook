import { useState } from 'react'
import {
  api,
  type Artifact,
  type ArtifactKind,
  type AudioOptions,
  type NoteSummary,
  type Source,
} from '../api'
import { useCapabilities } from '../hooks/useCapabilities'
import { AudioOptionsFields } from './AudioOptionsFields'
import type { StudioTarget } from './studio'

const KINDS: { kind: ArtifactKind; label: string }[] = [
  { kind: 'summary', label: 'Summary' },
  { kind: 'briefing', label: 'Briefing' },
  { kind: 'study_guide', label: 'Study guide' },
  { kind: 'faq', label: 'FAQ' },
  { kind: 'timeline', label: 'Timeline' },
  { kind: 'mind_map', label: 'Mind map' },
  { kind: 'flashcards', label: 'Flashcards & quiz' },
]

const buttonClass =
  'rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800'

interface StudioPaneProps {
  notebookId: string
  artifacts: Artifact[] | null
  notes: NoteSummary[] | null
  refreshArtifacts: () => Promise<void>
  refreshNotes: () => Promise<void>
  refreshSources: () => Promise<void>
  onOpen: (target: StudioTarget) => void
}

export function StudioPane({
  notebookId,
  artifacts,
  notes,
  refreshArtifacts,
  refreshNotes,
  refreshSources,
  onOpen,
}: StudioPaneProps) {
  const [focus, setFocus] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [audioOptions, setAudioOptions] = useState<AudioOptions>({
    length: 'default',
    format: 'deep_dive',
  })
  const { capabilities } = useCapabilities()
  const audioProblems =
    capabilities?.audio_overview?.ready === false ? capabilities.audio_overview.problems : []

  async function run(action: () => Promise<void>) {
    setError(null)
    setMessage(null)
    try {
      await action()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  const ids = [...selected].filter((id) => notes?.some((n) => n.id === id))

  async function noteAction(kind: 'summarize' | 'combine' | 'convert') {
    setBusy(true)
    await run(async () => {
      if (kind === 'convert') {
        const created: Source[] = await api.convertNotesToSources(notebookId, ids)
        await refreshSources()
        setMessage(`Added ${created.length} ${created.length === 1 ? 'source' : 'sources'}.`)
      } else {
        const note =
          kind === 'summarize'
            ? await api.summarizeNotes(notebookId, ids)
            : await api.combineNotes(notebookId, ids)
        await refreshNotes()
        setSelected(new Set())
        onOpen({ type: 'note', id: note.id })
      }
    })
    setBusy(false)
  }

  return (
    <div className="space-y-4">
      <section aria-label="Create" className="space-y-2">
        <label className="block text-xs">
          Focus (optional)
          <textarea
            aria-label="Focus (optional)"
            rows={2}
            maxLength={500}
            placeholder="Topic, audience, or length"
            value={focus}
            onChange={(e) => setFocus(e.target.value)}
            className="mt-1 block w-full rounded border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700"
          />
        </label>
        <div className="grid grid-cols-2 gap-2">
          {KINDS.map(({ kind, label }) => (
            <button
              key={kind}
              type="button"
              className="rounded bg-blue-600 px-2 py-1.5 text-sm text-white"
              onClick={() =>
                void run(async () => {
                  const created = await api.createArtifact(notebookId, kind, focus)
                  await refreshArtifacts()
                  onOpen({ type: 'artifact', id: created.id })
                })
              }
            >
              {label}
            </button>
          ))}
        </div>
      </section>

      <section
        aria-label="Audio overview"
        className="space-y-2 rounded border border-neutral-200 p-2 dark:border-neutral-800"
      >
        <h3 className="text-xs font-semibold uppercase text-neutral-500">Audio overview</h3>
        <AudioOptionsFields value={audioOptions} onChange={setAudioOptions} />
        <button
          type="button"
          className="w-full rounded bg-blue-600 px-2 py-1.5 text-sm text-white disabled:opacity-50"
          disabled={audioProblems.length > 0}
          onClick={() =>
            void run(async () => {
              const created = await api.createArtifact(
                notebookId,
                'audio_overview',
                focus,
                audioOptions,
              )
              await refreshArtifacts()
              onOpen({ type: 'artifact', id: created.id })
            })
          }
        >
          Generate audio overview
        </button>
        {audioProblems.length > 0 && (
          <ul
            aria-label="What is missing"
            className="list-disc pl-5 text-xs text-neutral-600 dark:text-neutral-400"
          >
            {audioProblems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        )}
      </section>

      {error && (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}

      <section aria-label="Artifacts" className="space-y-2">
        <h3 className="text-xs font-semibold uppercase text-neutral-500">Generated</h3>
        {artifacts?.length === 0 && <p className="text-neutral-500">Nothing generated yet.</p>}
        <ul className="space-y-2">
          {artifacts?.map((a) => (
            <li
              key={a.id}
              className="rounded border border-neutral-200 p-2 dark:border-neutral-800"
            >
              <div className="flex items-start gap-2">
                <button
                  type="button"
                  className="min-w-0 flex-1 truncate text-left font-medium hover:underline"
                  onClick={() => onOpen({ type: 'artifact', id: a.id })}
                >
                  {a.title}
                </button>
                <button
                  type="button"
                  aria-label={`Delete ${a.title}`}
                  className="rounded px-1 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
                  onClick={() => {
                    if (window.confirm(`Delete "${a.title}"?`))
                      void run(async () => {
                        await api.deleteArtifact(notebookId, a.id)
                        await refreshArtifacts()
                      })
                  }}
                >
                  ✕
                </button>
              </div>
              {(a.state === 'queued' || a.state === 'running') && (
                <div className="mt-1">
                  <progress
                    aria-label={`Generating ${a.title}`}
                    value={a.progress}
                    max={1}
                    className="w-full"
                  />
                  <div className="flex items-center justify-between text-xs text-neutral-500">
                    <span>{a.state === 'queued' ? 'Waiting…' : (a.stage ?? 'Working…')}</span>
                    <button
                      type="button"
                      className={buttonClass}
                      onClick={() =>
                        void run(async () => {
                          await api.cancelArtifact(notebookId, a.id)
                          await refreshArtifacts()
                        })
                      }
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              )}
              {(a.state === 'failed' || a.state === 'cancelled') && (
                <div className="mt-1 text-xs">
                  <p role="alert" className="text-red-600">
                    {a.error}
                  </p>
                  <button
                    type="button"
                    className={`${buttonClass} mt-1`}
                    onClick={() =>
                      void run(async () => {
                        await api.regenerateArtifact(notebookId, a.id)
                        await refreshArtifacts()
                      })
                    }
                  >
                    Retry
                  </button>
                </div>
              )}
              {a.state === 'ready' && a.stale && (
                <button
                  type="button"
                  className="mt-1 rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-950"
                  onClick={() =>
                    void run(async () => {
                      await api.regenerateArtifact(notebookId, a.id)
                      await refreshArtifacts()
                    })
                  }
                >
                  Sources changed — regenerate?
                </button>
              )}
            </li>
          ))}
        </ul>
      </section>

      <section aria-label="Notes" className="space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-semibold uppercase text-neutral-500">Notes</h3>
          <button
            type="button"
            className={buttonClass}
            onClick={() =>
              void run(async () => {
                const note = await api.createNote(notebookId)
                await refreshNotes()
                onOpen({ type: 'note', id: note.id })
              })
            }
          >
            New note
          </button>
        </div>
        {notes?.length === 0 && <p className="text-neutral-500">No notes yet.</p>}
        {ids.length > 0 && (
          <div
            className="flex flex-wrap gap-2"
            role="group"
            aria-label="Actions for selected notes"
          >
            <button
              type="button"
              className={buttonClass}
              disabled={busy}
              onClick={() => void noteAction('summarize')}
            >
              Summarize
            </button>
            <button
              type="button"
              className={buttonClass}
              disabled={busy}
              onClick={() => void noteAction('combine')}
            >
              Combine into one note
            </button>
            <button
              type="button"
              className={buttonClass}
              disabled={busy}
              onClick={() => void noteAction('convert')}
            >
              Convert to source
            </button>
          </div>
        )}
        <ul className="space-y-2">
          {notes?.map((n) => (
            <li
              key={n.id}
              className="flex items-start gap-2 rounded border border-neutral-200 p-2 dark:border-neutral-800"
            >
              <input
                type="checkbox"
                aria-label={`Select note ${n.title}`}
                checked={selected.has(n.id)}
                onChange={(e) => {
                  const next = new Set(selected)
                  if (e.target.checked) next.add(n.id)
                  else next.delete(n.id)
                  setSelected(next)
                }}
                className="mt-1"
              />
              <div className="min-w-0 flex-1">
                <button
                  type="button"
                  className="block w-full truncate text-left font-medium hover:underline"
                  onClick={() => onOpen({ type: 'note', id: n.id })}
                >
                  {n.title}
                </button>
                {n.preview && <p className="truncate text-xs text-neutral-500">{n.preview}</p>}
              </div>
              <button
                type="button"
                aria-label={`Delete note ${n.title}`}
                className="rounded px-1 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
                onClick={() => {
                  if (window.confirm(`Delete the note "${n.title}"?`))
                    void run(async () => {
                      await api.deleteNote(notebookId, n.id)
                      selected.delete(n.id)
                      await refreshNotes()
                    })
                }}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  )
}
