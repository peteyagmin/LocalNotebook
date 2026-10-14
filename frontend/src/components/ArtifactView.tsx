import { useEffect, useState } from 'react'
import { api, type ArtifactDetail, type Citation } from '../api'
import { AnswerText } from './AnswerText'

interface ArtifactViewProps {
  notebookId: string
  artifactId: string
  /** Bumps when the list changes, so a regenerated artifact reloads. */
  version: string
  expanded: boolean
  onToggleExpand: () => void
  onClose: () => void
  onOpenCitation: (citation: Citation) => void
  onChanged: () => void
}

const buttonClass =
  'rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800'

export function ArtifactView({
  notebookId,
  artifactId,
  version,
  expanded,
  onToggleExpand,
  onClose,
  onOpenCitation,
  onChanged,
}: ArtifactViewProps) {
  const [artifact, setArtifact] = useState<ArtifactDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [focus, setFocus] = useState('')
  const [exportOpen, setExportOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .getArtifact(notebookId, artifactId)
      .then((a) => {
        if (cancelled) return
        setArtifact(a)
        setFocus(a.focus)
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      cancelled = true
    }
  }, [notebookId, artifactId, version])

  async function run(action: () => Promise<unknown>) {
    setError(null)
    try {
      await action()
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  async function download(format: 'md' | 'docx' | 'pdf') {
    setExportOpen(false)
    await run(async () => {
      const { blob, filename } = await api.exportArtifact(notebookId, artifactId, format)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      link.click()
      URL.revokeObjectURL(url)
    })
  }

  if (!artifact)
    return error ? (
      <p role="alert" className="p-3 text-red-600">
        {error}
      </p>
    ) : (
      <p className="p-3">Loading…</p>
    )

  const working = artifact.state === 'queued' || artifact.state === 'running'

  return (
    <div
      className="flex h-full min-h-0 flex-col"
      aria-label={`Artifact: ${artifact.title}`}
      role="region"
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-neutral-200 px-3 py-2 dark:border-neutral-800">
        <button type="button" className={buttonClass} onClick={onClose}>
          ← Back
        </button>
        <h2 className="min-w-0 flex-1 truncate font-semibold">{artifact.title}</h2>
        <button
          type="button"
          className={buttonClass}
          aria-pressed={expanded}
          onClick={onToggleExpand}
        >
          {expanded ? 'Shrink' : 'Expand'}
        </button>
        <div className="relative">
          <button
            type="button"
            className={buttonClass}
            aria-haspopup="menu"
            aria-expanded={exportOpen}
            disabled={!artifact.has_content}
            onClick={() => setExportOpen(!exportOpen)}
          >
            Export
          </button>
          {exportOpen && (
            <div
              role="menu"
              className="absolute right-0 z-30 mt-1 w-40 rounded border border-neutral-300 bg-white shadow dark:border-neutral-700 dark:bg-neutral-900"
            >
              {(
                [
                  ['md', 'Markdown (.md)'],
                  ['docx', 'Word (.docx)'],
                  ['pdf', 'PDF (.pdf)'],
                ] as const
              ).map(([format, label]) => (
                <button
                  key={format}
                  role="menuitem"
                  type="button"
                  onClick={() => void download(format)}
                  className="block w-full px-3 py-2 text-left hover:bg-neutral-100 dark:hover:bg-neutral-800"
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
      </header>

      <div className="flex-1 overflow-auto p-4 text-sm">
        {artifact.stale && (
          <div
            role="status"
            className="mb-3 flex items-center gap-2 rounded bg-amber-100 p-2 text-amber-950"
          >
            <span>Sources changed — regenerate?</span>
            <button
              type="button"
              className={buttonClass}
              onClick={() => void run(() => api.regenerateArtifact(notebookId, artifactId))}
            >
              Regenerate
            </button>
          </div>
        )}
        {artifact.error && (
          <p role="alert" className="mb-3 text-red-600">
            {artifact.state === 'ready'
              ? `Last regeneration failed: ${artifact.error}`
              : artifact.error}
          </p>
        )}
        {error && (
          <p role="alert" className="mb-3 text-red-600">
            {error}
          </p>
        )}
        {working && (
          <div className="mb-3">
            <progress
              aria-label="Generating"
              value={artifact.progress}
              max={1}
              className="w-full"
            />
            <p className="text-xs text-neutral-500">{artifact.stage ?? 'Waiting…'}</p>
          </div>
        )}
        {artifact.has_content && (
          <AnswerText
            text={artifact.content}
            citations={artifact.citations}
            onOpenCitation={onOpenCitation}
          />
        )}
        {!artifact.has_content && !working && !artifact.error && (
          <p className="text-neutral-500">Nothing generated yet.</p>
        )}
      </div>

      <footer className="space-y-2 border-t border-neutral-200 p-3 dark:border-neutral-800">
        <label className="block text-xs">
          Focus (optional)
          <textarea
            rows={2}
            maxLength={500}
            value={focus}
            onChange={(e) => setFocus(e.target.value)}
            className="mt-1 block w-full rounded border border-neutral-300 bg-transparent px-2 py-1 text-sm dark:border-neutral-700"
          />
        </label>
        <div className="flex gap-2">
          <button
            type="button"
            className={buttonClass}
            disabled={working}
            onClick={() => void run(() => api.regenerateArtifact(notebookId, artifactId, focus))}
          >
            Regenerate
          </button>
          {working && (
            <button
              type="button"
              className={buttonClass}
              onClick={() => void run(() => api.cancelArtifact(notebookId, artifactId))}
            >
              Cancel
            </button>
          )}
        </div>
      </footer>
    </div>
  )
}
