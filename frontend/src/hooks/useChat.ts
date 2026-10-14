import { useCallback, useEffect, useRef, useState } from 'react'
import { api, type ChatEvent, type ChatMessage, type Citation } from '../api'

export interface StreamingAnswer {
  text: string
  citations: Citation[]
}

export interface ChatError {
  code: string
  message: string
}

/** Chat history plus the answer currently streaming in (FR-3.4, FR-3.5, FR-3.8). */
export function useChat(notebookId: string, sourcesKey: string) {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null)
  const [streaming, setStreaming] = useState<StreamingAnswer | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ChatError | null>(null)
  const [starters, setStarters] = useState<string[]>([])
  const controller = useRef<AbortController | null>(null)

  const reload = useCallback(async () => {
    setMessages(await api.getChat(notebookId))
  }, [notebookId])

  useEffect(() => {
    api
      .getChat(notebookId)
      .then(setMessages)
      .catch((e) => setError({ code: 'load', message: e instanceof Error ? e.message : String(e) }))
    return () => controller.current?.abort()
  }, [notebookId])

  const empty = messages !== null && messages.length === 0
  useEffect(() => {
    if (!empty) return
    let cancelled = false
    api
      .getStarters(notebookId)
      .then((r) => !cancelled && setStarters(r.questions))
      .catch(() => !cancelled && setStarters([]))
    return () => {
      cancelled = true
    }
  }, [notebookId, empty, sourcesKey])

  const send = useCallback(
    async (question: string) => {
      const text = question.trim()
      if (!text || busy) return
      setError(null)
      setBusy(true)
      setStreaming({ text: '', citations: [] })
      const pending: ChatMessage = {
        id: 'pending-user',
        role: 'user',
        content: text,
        citations: [],
        suggestions: [],
        status: 'complete',
        created_at: new Date().toISOString(),
      }
      setMessages((m) => [...(m ?? []), pending])
      let gotDone = false
      const ctl = new AbortController()
      controller.current = ctl
      const onEvent = (e: ChatEvent) => {
        switch (e.type) {
          case 'user_message':
            setMessages((m) => (m ?? []).map((x) => (x.id === 'pending-user' ? e.message : x)))
            break
          case 'sources':
            setStreaming((s) => (s ? { ...s, citations: e.citations } : s))
            break
          case 'token':
            setStreaming((s) => (s ? { ...s, text: s.text + e.text } : s))
            break
          case 'done':
            gotDone = true
            setMessages((m) => [...(m ?? []), e.message])
            setStreaming(null)
            break
          case 'suggestions':
            setMessages((m) =>
              (m ?? []).map((x) =>
                x.id === e.message_id ? { ...x, suggestions: e.questions } : x,
              ),
            )
            break
          case 'error':
            setError({ code: e.code, message: e.message })
            setStreaming(null)
            break
        }
      }
      try {
        await api.askStream(notebookId, text, onEvent, ctl.signal)
      } catch (e) {
        if (!ctl.signal.aborted)
          setError({
            code: 'request',
            message: e instanceof Error ? e.message : String(e),
          })
      } finally {
        setStreaming(null)
        setBusy(false)
        // No final message arrived (error or dropped connection): show what the server kept.
        if (!gotDone) void reload().catch(() => {})
      }
    },
    [busy, notebookId, reload],
  )

  const stop = useCallback(async () => {
    try {
      await api.stopChat(notebookId)
    } catch {
      controller.current?.abort() // the server will still keep the partial answer
    }
  }, [notebookId])

  const clear = useCallback(async () => {
    await api.clearChat(notebookId)
    setMessages([])
    setError(null)
  }, [notebookId])

  return { messages, streaming, busy, error, starters, send, stop, clear }
}
