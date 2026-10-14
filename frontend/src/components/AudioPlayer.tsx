import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { formatTimestamp } from '../format'

const SPEEDS = [0.75, 1, 1.25, 1.5, 1.75, 2]
const SKIP_SECONDS = 15

const buttonClass =
  'rounded border border-neutral-300 px-3 py-1 text-sm hover:bg-neutral-100 disabled:opacity-50 dark:border-neutral-700 dark:hover:bg-neutral-800'

interface AudioPlayerProps {
  notebookId: string
  artifactId: string
  /** Changes when the audio file does (after re-synthesis). */
  version: string
  /** Length from the transcript, used until the browser has read the file. */
  knownDuration: number | null
  /** Called as the playback position moves. */
  onTime: (seconds: number) => void
  /** Set to jump to a time and play: { id } makes repeated jumps to the same time work. */
  seekRequest: { id: number; seconds: number } | null
}

/** Play / pause, seek, skip 15 seconds, and speed 0.75x to 2x (FR-6.3). The audio is fetched
 * with the session token and played from memory, so seeking needs no further requests. */
export function AudioPlayer({
  notebookId,
  artifactId,
  version,
  knownDuration,
  onTime,
  seekRequest,
}: AudioPlayerProps) {
  const audio = useRef<HTMLAudioElement>(null)
  const [loaded, setLoaded] = useState<{ key: string; url: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [playing, setPlaying] = useState(false)
  const [current, setCurrent] = useState(0)
  const [duration, setDuration] = useState<number | null>(knownDuration)
  const [speed, setSpeed] = useState(1)

  const key = `${notebookId}/${artifactId}/${version}`
  const url = loaded?.key === key ? loaded.url : null

  useEffect(() => {
    let cancelled = false
    let made: string | null = null
    api
      .getArtifactAudio(notebookId, artifactId)
      .then((blob) => {
        if (cancelled) return
        made = URL.createObjectURL(blob)
        setLoaded({ key, url: made })
        setError(null)
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      cancelled = true
      if (made) URL.revokeObjectURL(made)
    }
  }, [notebookId, artifactId, version, key])

  useEffect(() => {
    if (audio.current) audio.current.playbackRate = speed
  }, [speed, url])

  const lastRequest = useRef<number | null>(null)
  useEffect(() => {
    if (!seekRequest || lastRequest.current === seekRequest.id || !audio.current) return
    lastRequest.current = seekRequest.id
    audio.current.currentTime = seekRequest.seconds
    setCurrent(seekRequest.seconds)
    onTime(seekRequest.seconds)
    void audio.current.play()?.catch?.(() => {})
  }, [seekRequest, onTime])

  const total = duration ?? knownDuration ?? 0
  const move = (seconds: number) => {
    if (!audio.current) return
    const next = Math.min(Math.max(0, seconds), total || seconds)
    audio.current.currentTime = next
    setCurrent(next)
    onTime(next)
  }

  if (error)
    return (
      <p role="alert" className="text-red-600">
        {error}
      </p>
    )

  return (
    <div
      role="group"
      aria-label="Audio player"
      className="space-y-2 rounded border border-neutral-200 p-3 dark:border-neutral-800"
    >
      <audio
        ref={audio}
        src={url ?? undefined}
        preload="metadata"
        onLoadedMetadata={(e) => {
          const d = e.currentTarget.duration
          if (Number.isFinite(d)) setDuration(d)
        }}
        onTimeUpdate={(e) => {
          setCurrent(e.currentTarget.currentTime)
          onTime(e.currentTarget.currentTime)
        }}
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
      />
      <div className="flex items-center gap-2">
        <button
          type="button"
          className={buttonClass}
          disabled={!url}
          aria-label={playing ? 'Pause' : 'Play'}
          onClick={() => {
            if (!audio.current) return
            if (playing) audio.current.pause()
            else void audio.current.play()?.catch?.(() => {})
          }}
        >
          {playing ? '⏸' : '▶'}
        </button>
        <button
          type="button"
          className={buttonClass}
          disabled={!url}
          aria-label={`Back ${SKIP_SECONDS} seconds`}
          onClick={() => move(current - SKIP_SECONDS)}
        >
          −{SKIP_SECONDS}s
        </button>
        <button
          type="button"
          className={buttonClass}
          disabled={!url}
          aria-label={`Forward ${SKIP_SECONDS} seconds`}
          onClick={() => move(current + SKIP_SECONDS)}
        >
          +{SKIP_SECONDS}s
        </button>
        <label className="ml-auto text-xs">
          Speed{' '}
          <select
            aria-label="Speed"
            value={speed}
            onChange={(e) => setSpeed(Number(e.target.value))}
            className="rounded border border-neutral-300 bg-transparent px-1 py-0.5 dark:border-neutral-700 dark:bg-neutral-900"
          >
            {SPEEDS.map((s) => (
              <option key={s} value={s}>
                {s}×
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span>{formatTimestamp(current)}</span>
        <input
          type="range"
          aria-label="Seek"
          className="flex-1"
          min={0}
          max={total || 1}
          step={0.1}
          value={Math.min(current, total || 1)}
          disabled={!url || !total}
          onChange={(e) => move(Number(e.target.value))}
        />
        <span>{formatTimestamp(total)}</span>
      </div>
      {!url && <p className="text-xs text-neutral-500 dark:text-neutral-400">Loading the audio…</p>}
    </div>
  )
}
