import { useCallback, useEffect, useState } from 'react'
import { api, type NoteSummary } from '../api'

export function useNotes(notebookId: string) {
  const [notes, setNotes] = useState<NoteSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      setNotes(await api.listNotes(notebookId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [notebookId])

  useEffect(() => {
    api
      .listNotes(notebookId)
      .then(setNotes)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }, [notebookId])

  return { notes, refresh, error }
}
