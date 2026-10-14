import { useEffect, useRef, useState } from 'react'
import { api, type Source, type SourceContent } from '../api'

export interface Highlight {
  start: number
  end: number
}

interface SourceViewerProps {
  notebookId: string
  source: Source
  highlight?: Highlight
  onClose: () => void
}

/** Extracted text with page markers (FR-2.8). With `highlight`, scrolls to and marks that range. */
export function SourceViewer({ notebookId, source, highlight, onClose }: SourceViewerProps) {
  const [content, setContent] = useState<SourceContent | null>(null)
  const [error, setError] = useState<string | null>(null)
  const markRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .getSourceContent(notebookId, source.id)
      .then((c) => !cancelled && setContent(c))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
    return () => {
      cancelled = true
    }
  }, [notebookId, source.id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    if (content && highlight) markRef.current?.scrollIntoView?.({ block: 'center' })
  }, [content, highlight])

  let lastPage: number | null = null
  return (
    <div
      role="dialog"
      aria-label={`Source: ${source.name}`}
      className="absolute inset-0 z-10 flex flex-col bg-white dark:bg-neutral-950"
    >
      <header className="flex items-center justify-between gap-2 border-b border-neutral-200 px-3 py-2 dark:border-neutral-800">
        <h2 className="truncate text-sm font-semibold">{source.name}</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close source viewer"
          className="rounded px-2 py-0.5 hover:bg-neutral-100 dark:hover:bg-neutral-800"
        >
          ✕
        </button>
      </header>
      <div className="flex-1 overflow-auto p-4 text-sm">
        {source.guide && (
          <section
            aria-label="Source guide"
            className="mb-4 rounded bg-neutral-100 p-3 dark:bg-neutral-900"
          >
            <p>{source.guide.summary}</p>
            <ul className="mt-2 flex flex-wrap gap-1">
              {source.guide.topics.map((t) => (
                <li
                  key={t}
                  className="rounded-full bg-neutral-200 px-2 py-0.5 text-xs dark:bg-neutral-800"
                >
                  {t}
                </li>
              ))}
            </ul>
          </section>
        )}
        {error && (
          <p role="alert" className="text-red-600">
            {error}
          </p>
        )}
        {!content && !error && <p>Loading…</p>}
        {content?.segments.map((seg, i) => {
          const marker = seg.page !== null && seg.page !== lastPage ? seg.page : null
          lastPage = seg.page ?? lastPage
          const text = content.text.slice(seg.start, seg.end)
          const hl =
            highlight && highlight.start < seg.end && highlight.end > seg.start
              ? {
                  from: Math.max(highlight.start, seg.start) - seg.start,
                  to: Math.min(highlight.end, seg.end) - seg.start,
                }
              : null
          return (
            <div key={i}>
              {marker !== null && (
                <div className="my-3 border-t border-neutral-300 pt-1 text-xs text-neutral-500 dark:border-neutral-700">
                  Page {marker}
                </div>
              )}
              <p className="mb-3 whitespace-pre-wrap">
                {hl ? (
                  <>
                    {text.slice(0, hl.from)}
                    <mark ref={markRef} className="bg-yellow-200 text-inherit dark:bg-yellow-700">
                      {text.slice(hl.from, hl.to)}
                    </mark>
                    {text.slice(hl.to)}
                  </>
                ) : (
                  text
                )}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
