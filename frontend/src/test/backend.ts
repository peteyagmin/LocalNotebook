import { vi } from 'vitest'
import type { Settings } from '../api'

export const baseSettings: Settings = {
  chat_model: 'c',
  embedding_model: 'e',
  stt_model: '',
  tts_voice_a: '',
  tts_voice_b: '',
  llm_base_url: 'http://127.0.0.1:11434/v1',
  llm_api_key: '',
  setup_completed: true,
  max_sources_per_notebook: 50,
  max_upload_mb: 200,
  retrieval_top_k: 8,
}

type Handler = (body: unknown, url: string) => unknown
export type Routes = Record<string, Handler | unknown>

export interface Call {
  method: string
  path: string
  body: unknown
}

/** Stub fetch with `"METHOD /path"` routes (path without /api/v1; `:id` matches a segment). */
export function mockBackend(routes: Routes) {
  const calls: Call[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      const path = url.replace('/api/v1', '')
      let body: unknown = init?.body
      if (typeof body === 'string') body = JSON.parse(body)
      calls.push({ method, path, body })
      for (const [key, value] of Object.entries(routes)) {
        const [m, pattern] = key.split(' ')
        const re = new RegExp('^' + pattern.replace(/:\w+/g, '[^/]+') + '$')
        if (m === method && re.test(path.split('?')[0])) {
          const result = typeof value === 'function' ? (value as Handler)(body, path) : value
          if (result instanceof Response) return result
          if (result === undefined) return new Response(null, { status: 204 })
          return new Response(JSON.stringify(result), { status: 200 })
        }
      }
      return new Response(
        JSON.stringify({ error: { code: 'x', message: `no route ${key(method, path)}` } }),
        {
          status: 404,
        },
      )
    }),
  )
  return calls
}

const key = (m: string, p: string) => `${m} ${p}`

export function source(over: Partial<import('../api').Source> = {}): import('../api').Source {
  return {
    id: 's1',
    name: 'Doc.pdf',
    type: 'pdf',
    size_bytes: 10,
    state: 'ready',
    stage: null,
    progress: 1,
    error: null,
    enabled: true,
    char_count: 20,
    page_count: 2,
    guide: { summary: 'A guide summary.', topics: ['alpha', 'beta'] },
    ...over,
  }
}

export const notebook = (over = {}) => ({
  id: 'n1',
  name: 'My notebook',
  created_at: '2026-10-01T00:00:00Z',
  updated_at: '2026-10-02T00:00:00Z',
  source_count: 2,
  size_bytes: 2048,
  ...over,
})

const encoder = new TextEncoder()

/** A Server-Sent Events response that has already finished. */
export function sseResponse(events: unknown[]): Response {
  const body = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('')
  return new Response(body, { status: 200 })
}

/** An SSE response that stays open until `push`/`close` are called (to test Stop). */
export function openSse() {
  let controller!: ReadableStreamDefaultController<Uint8Array>
  const stream = new ReadableStream<Uint8Array>({
    start(c) {
      controller = c
    },
  })
  return {
    response: new Response(stream, { status: 200 }),
    push: (event: unknown) =>
      controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`)),
    close: () => controller.close(),
  }
}

export function chatMessage(
  over: Partial<import('../api').ChatMessage> = {},
): import('../api').ChatMessage {
  return {
    id: 'm1',
    role: 'assistant',
    content: 'Zebras graze [1].',
    citations: [
      {
        label: 1,
        chunk_id: 'c1',
        source_id: 's1',
        source_name: 'Doc.pdf',
        excerpt: 'Zebras graze on grass in herds.',
        location: { page: 1, heading_path: null, char_start: 0, char_end: 31 },
        removed: false,
      },
    ],
    suggestions: [],
    status: 'complete',
    created_at: '2026-10-14T00:00:00Z',
    ...over,
  }
}
