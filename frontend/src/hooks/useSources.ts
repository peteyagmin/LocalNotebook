import { useCallback, useEffect, useState } from 'react'
import { api, type Source } from '../api'

const isActive = (s: Source) => s.state === 'queued' || s.state === 'processing'

/** Sources of a notebook, kept live over SSE while any source is queued or processing. */
export function useSources(notebookId: string) {
  const [sources, setSources] = useState<Source[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retryTick, setRetryTick] = useState(0)

  const refresh = useCallback(async () => {
    try {
      setSources(await api.listSources(notebookId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [notebookId])

  useEffect(() => {
    api
      .listSources(notebookId)
      .then(setSources)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [notebookId])

  const active = sources?.some(isActive) ?? false

  useEffect(() => {
    if (!active) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    api
      .streamSources(notebookId, setSources, controller.signal)
      .catch(() => {})
      .finally(() => {
        // Reconnect if the stream dropped while work is still running.
        if (!controller.signal.aborted) timer = setTimeout(() => setRetryTick((t) => t + 1), 1000)
      })
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [active, notebookId, retryTick])

  return { sources, setSources, refresh, error, setError }
}
