import { afterEach, expect, it, vi } from 'vitest'
import { api, type Source } from './api'
import { source } from './test/backend'

afterEach(() => vi.unstubAllGlobals())

it('parses SSE events split across network chunks', async () => {
  const a: Source[] = [source({ state: 'processing' })]
  const b: Source[] = [source({ state: 'ready' })]
  const text = `data: ${JSON.stringify(a)}\n\ndata: ${JSON.stringify(b)}\n\n`
  const cut = 20
  const enc = new TextEncoder()
  const body = new ReadableStream({
    start(c) {
      c.enqueue(enc.encode(text.slice(0, cut)))
      c.enqueue(enc.encode(text.slice(cut)))
      c.close()
    },
  })
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(body, { status: 200 })),
  )
  const seen: Source[][] = []
  await api.streamSources('n1', (s) => seen.push(s), new AbortController().signal)
  expect(seen.map((s) => s[0].state)).toEqual(['processing', 'ready'])
})

it('turns error responses into ApiError with the server message', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(JSON.stringify({ error: { code: 'source_limit', message: 'Too many.' } }), {
          status: 400,
        }),
    ),
  )
  await expect(api.listSources('n1')).rejects.toMatchObject({
    code: 'source_limit',
    message: 'Too many.',
  })
})
