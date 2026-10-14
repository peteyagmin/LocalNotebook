import { useCallback, useEffect, useState } from 'react'
import { api, type Artifact } from '../api'

const isActive = (a: Artifact) => a.state === 'queued' || a.state === 'running'

/** Artifacts of a notebook, kept live over SSE while any generation is queued or running. */
export function useArtifacts(notebookId: string) {
  const [artifacts, setArtifacts] = useState<Artifact[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [retryTick, setRetryTick] = useState(0)

  const refresh = useCallback(async () => {
    try {
      setArtifacts(await api.listArtifacts(notebookId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [notebookId])

  useEffect(() => {
    api
      .listArtifacts(notebookId)
      .then(setArtifacts)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [notebookId])

  const active = artifacts?.some(isActive) ?? false

  useEffect(() => {
    if (!active) return
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout> | undefined
    api
      .streamArtifacts(notebookId, setArtifacts, controller.signal)
      .catch(() => {})
      .finally(() => {
        if (!controller.signal.aborted) timer = setTimeout(() => setRetryTick((t) => t + 1), 1000)
      })
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [active, notebookId, retryTick])

  return { artifacts, refresh, error }
}
