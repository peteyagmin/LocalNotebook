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
        if (m === method && re.test(path)) {
          const result = typeof value === 'function' ? (value as Handler)(body, path) : value
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
