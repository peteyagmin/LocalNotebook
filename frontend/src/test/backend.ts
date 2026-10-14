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
  context_window_tokens: 8000,
  allow_web_import: true,
  allow_discover: true,
  allow_model_downloads: true,
  transcribe_uncaptioned_videos: false,
  searxng_url: '',
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
    url: null,
    fetched_at: null,
    version_count: 0,
    meta: {},
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

export function artifact(over: Partial<import('../api').Artifact> = {}): import('../api').Artifact {
  return {
    id: 'a1',
    kind: 'summary',
    title: 'Notebook summary',
    state: 'ready',
    stage: null,
    progress: 1,
    error: null,
    focus: '',
    has_content: true,
    stale: false,
    created_at: '2026-10-14T00:00:00Z',
    updated_at: '2026-10-14T00:00:00Z',
    ...over,
  }
}

export function artifactDetail(
  over: Partial<import('../api').ArtifactDetail> = {},
): import('../api').ArtifactDetail {
  return {
    ...artifact(),
    format: 'markdown',
    data: null,
    content: '# Notebook summary\n\nZebras graze [1].\n\n## Key points\n\n- Herds',
    citations: chatMessage().citations,
    ...over,
  }
}

export function note(over: Partial<import('../api').Note> = {}): import('../api').Note {
  return {
    id: 'n-1',
    title: 'My note',
    content: 'Hello **world** [1]',
    citations: chatMessage().citations,
    created_at: '2026-10-14T00:00:00Z',
    updated_at: '2026-10-14T00:00:00Z',
    ...over,
  }
}

export const timelineData = {
  events: [
    {
      date: '1874',
      iso_date: '1874',
      title: 'Port founded',
      description: 'By Aldane.',
      sources: [1],
    },
    {
      date: 'March 1902',
      iso_date: '1902-03',
      title: 'Lighthouse built',
      description: '',
      sources: [1],
    },
  ],
  cast: [{ name: 'Henrik Aldane', role: 'founder', sources: [1] }],
}

export const mindMapData = {
  root: {
    label: 'Zebras',
    sources: [],
    children: [
      { label: 'Diet', sources: [1], children: [{ label: 'Grass', sources: [1], children: [] }] },
      { label: 'Habitat', sources: [], children: [] },
    ],
  },
}

export const flashcardsData = {
  flashcards: [
    { front: 'What do zebras eat?', back: 'Grass', sources: [1] },
    { front: 'Where do they live?', back: 'Savanna', sources: [1] },
    { front: 'How do they travel?', back: 'In herds', sources: [] },
  ],
  quiz: [
    {
      question: 'Q1?',
      options: ['A1', 'B1', 'C1', 'D1'],
      correct_index: 1,
      explanation: 'Because one.',
      sources: [1],
    },
    {
      question: 'Q2?',
      options: ['A2', 'B2', 'C2', 'D2'],
      correct_index: 0,
      explanation: 'Because two.',
      sources: [1],
    },
    {
      question: 'Q3?',
      options: ['A3', 'B3', 'C3', 'D3'],
      correct_index: 3,
      explanation: 'Because three.',
      sources: [],
    },
  ],
}
