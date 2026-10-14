import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type ArtifactDetail, type AudioTranscript, type Citation } from '../api'
import { formatTimestamp } from '../format'
import { AudioPlayer } from './AudioPlayer'
import { ScriptEditor } from './ScriptEditor'
import { SourceChips } from './SourceChips'

interface AudioOverviewViewProps {
  notebookId: string
  artifact: ArtifactDetail
  onOpenCitation: (citation: Citation) => void
  onChanged: () => void
}

const buttonClass =
  'rounded border border-neutral-300 px-2 py-1 text-xs hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800'

export function AudioOverviewView({
  notebookId,
  artifact,
  onOpenCitation,
  onChanged,
}: AudioOverviewViewProps) {
  const transcript = artifact.data as AudioTranscript
  const [now, setNow] = useState(0)
  const [seek, setSeek] = useState<{ id: number; seconds: number } | null>(null)
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const current = useRef<HTMLLIElement | null>(null)
  const onTime = useCallback((seconds: number) => setNow(seconds), [])
  const working = artifact.state === 'queued' || artifact.state === 'running'

  // The turn being spoken: the last one that has started.
  let playingIndex = -1
  transcript.turns.forEach((t, i) => {
    if (t.start !== null && now >= t.start) playingIndex = i
  })

  useEffect(() => {
    current.current?.scrollIntoView?.({ block: 'nearest' })
  }, [playingIndex])

  async function resynthesize() {
    setError(null)
    try {
      await api.resynthesize(notebookId, artifact.id)
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="space-y-3">
      <h3 className="text-lg font-semibold">{transcript.title}</h3>
      <AudioPlayer
        notebookId={notebookId}
        artifactId={artifact.id}
        version={artifact.updated_at}
        knownDuration={transcript.duration}
        onTime={onTime}
        seekRequest={seek}
      />
      {error && (
        <p role="alert" className="text-red-600">
          {error}
        </p>
      )}
      {transcript.outdated && (
        <div
          role="status"
          className="flex items-center gap-2 rounded bg-amber-100 p-2 text-amber-950"
        >
          <span>The script changed. Re-synthesize to update the audio.</span>
        </div>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          className={buttonClass}
          disabled={working || editing}
          onClick={() => setEditing(true)}
        >
          Edit script
        </button>
        <button
          type="button"
          className={buttonClass}
          disabled={working || editing}
          onClick={() => void resynthesize()}
        >
          Re-synthesize audio
        </button>
      </div>

      {editing ? (
        <ScriptEditor
          notebookId={notebookId}
          artifactId={artifact.id}
          turns={transcript.turns}
          citations={artifact.citations}
          onOpenCitation={onOpenCitation}
          onSaved={onChanged}
          onClose={() => setEditing(false)}
        />
      ) : (
        <section aria-label="Transcript">
          <ol className="space-y-1">
            {transcript.turns.map((turn, i) => {
              const labels = turn.chunk_ids
                .map((id) => artifact.citations.find((c) => c.chunk_id === id)?.label)
                .filter((n): n is number => n !== undefined)
              const seekable = turn.start !== null
              const active = i === playingIndex
              return (
                <li
                  key={i}
                  ref={active ? current : undefined}
                  aria-current={active ? 'true' : undefined}
                  className={`rounded p-2 ${active ? 'bg-blue-50 dark:bg-blue-950' : ''}`}
                >
                  <button
                    type="button"
                    disabled={!seekable}
                    aria-label={
                      seekable
                        ? `Play from ${formatTimestamp(turn.start ?? 0)}: Host ${turn.speaker}`
                        : `Host ${turn.speaker} (not in the audio yet)`
                    }
                    onClick={() =>
                      seekable && setSeek({ id: Date.now() + i, seconds: turn.start ?? 0 })
                    }
                    className="block w-full text-left disabled:cursor-default"
                  >
                    <span className="mr-2 text-xs font-semibold text-neutral-500 dark:text-neutral-400">
                      Host {turn.speaker}
                      {seekable && (
                        <span className="ml-1 font-normal">{formatTimestamp(turn.start ?? 0)}</span>
                      )}
                    </span>
                    <span>{turn.text}</span>
                  </button>
                  {labels.length > 0 && (
                    <SourceChips
                      labels={labels}
                      citations={artifact.citations}
                      onOpen={onOpenCitation}
                    />
                  )}
                </li>
              )
            })}
          </ol>
        </section>
      )}
    </div>
  )
}
